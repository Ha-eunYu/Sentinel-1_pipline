"""
speckle 필터들이 공유하는 저수준 인프라.

각 필터 모듈(lee.py, refined_lee.py, ...)은 "지역 통계를 어떻게 계산하는가"
(stats function)만 다르게 구현하고, 아래의 공통 요소를 재사용한다:

- `integral_image` / `mean_variance_from_sums`  : 적분영상 기반 이동 통계
- `apply_lee_weight`                            : Lee 계열 공통 가중치 공식
- `run_speckle_filter`                          : GeoTIFF 입출력 + 밴드 루프
- `validate_window_size`                        : 윈도우 크기 검증

이렇게 분리해두면 SNAP이 제공하는 다른 필터(Frost, Gamma Map, Lee Sigma,
IDAN 등)를 추가할 때도 stats function 하나만 새로 작성해 `run_speckle_filter`
에 끼워 넣으면 된다 (references.py의 필터 목록 참고).

공통 규약
--------
- stats function 시그니처: `(array, valid_mask, window_size) ->
  (mean, variance, valid_count)`. 세 반환값 모두 입력과 같은 shape이며,
  valid_count가 0인 위치의 mean/variance는 정의되지 않는다(nan). 최종
  마스킹은 apply_lee_weight가 담당한다.
- nodata 픽셀은 윈도우 통계에서 완전히 제외된다 (0으로 채우고 카운트에서도
  뺀 뒤 실제 유효 픽셀 수로 나눔). RCM GRD 영상은 지오코딩 후 사각형
  래스터의 모서리에 nodata 삼각형이 생기는데, 이 규약 덕분에 그 경계
  근처에서도 통계가 왜곡되지 않는다.
- 메모리: 밴드 전체를 한 번에 메모리에 올려 처리한다(float64 중간 배열
  여러 개). 수천~1만 픽셀급 장면은 문제없지만, 한 변이 수만 픽셀인 초대형
  장면에서는 부족할 수 있다 (겹침을 둔 블록 처리로 확장 가능, 현재 미구현).
- scipy 의존성을 피하려고 이동 통계는 numpy 적분영상(summed-area table)
  으로만 계산한다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import rasterio

# 지역 통계 함수의 공통 시그니처.
# (array, valid_mask, window_size) -> (mean, variance, valid_count)
StatsFn = Callable[[np.ndarray, np.ndarray, int], tuple[np.ndarray, np.ndarray, np.ndarray]]

# 필터 함수의 공통 시그니처. 한 스트립(array)과 그 유효 마스크를 받아
# 필터링된 배열을 돌려준다. nodata/무효 위치는 run_speckle_filter가 최종적으로
# 다시 마스킹하므로, 여기서 굳이 nodata를 채우지 않아도 된다(채워도 무방).
# (array, valid_mask, window_size, nodata) -> filtered
FilterFn = Callable[[np.ndarray, np.ndarray, int, float], np.ndarray]


def validate_window_size(window_size: int, min_size: int = 3) -> None:
    """window_size가 min_size 이상의 홀수인지 검증한다."""
    if window_size < min_size or window_size % 2 == 0:
        raise ValueError(
            f"window_size는 {min_size} 이상의 홀수여야 합니다: {window_size}"
        )


def integral_image(array: np.ndarray, pad: int) -> np.ndarray:
    """
    array를 사방으로 pad만큼 0-padding한 뒤 2D 누적합(적분영상)을 만든다.

    integral[i, j] = 0-padding된 배열의 [:i, :j] 영역 합. 가장자리에
    0행/0열을 추가해두어서, 임의의 사각형 영역 합을 호출부에서 4항 뺄셈
    만으로 O(1)에 구할 수 있다.
    """
    padded = np.pad(array, pad, mode="constant", constant_values=0.0)
    integral = np.zeros((padded.shape[0] + 1, padded.shape[1] + 1), dtype=np.float64)
    integral[1:, 1:] = np.cumsum(np.cumsum(padded, axis=0), axis=1)
    return integral


def mean_variance_from_sums(
    sum_: np.ndarray, sum_sq: np.ndarray, count: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """합계/제곱합/유효개수 배열로부터 평균/분산을 계산한다 (count=0인 곳은 nan)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = sum_ / count
        mean_sq = sum_sq / count
        # 부동소수점 오차로 분산이 아주 작은 음수가 나올 수 있어 0으로 clip.
        variance = np.maximum(mean_sq - mean * mean, 0.0)
    return mean, variance


def full_window_sums(
    array: np.ndarray, valid_mask: np.ndarray, window_size: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    정사각형 window_size x window_size 윈도우의 (합, 제곱합, 유효개수)를
    적분영상으로 계산한다. lee.full_window_stats와 frost.full_window_ci2가
    공유하는 저수준 계산.
    """
    pad = window_size // 2
    k = window_size
    zeroed = np.where(valid_mask, array, 0.0)

    def box(a: np.ndarray) -> np.ndarray:
        it = integral_image(a, pad)
        return it[k:, k:] - it[:-k, k:] - it[k:, :-k] + it[:-k, :-k]

    return box(zeroed), box(zeroed * zeroed), box(valid_mask.astype(np.float64))


def full_window_ci2(array: np.ndarray, valid_mask: np.ndarray, window_size: int) -> np.ndarray:
    """
    중심 픽셀별 지역 상대분산 Ci^2 = var / mean^2 (Frost 필터용).

    유효 픽셀이 없는 위치는 nan이 되며, 호출부(run_speckle_filter)가 최종적
    으로 nodata로 덮으므로 별도 마스킹은 하지 않는다.
    """
    s, sq, cnt = full_window_sums(array, valid_mask, window_size)
    mean, variance = mean_variance_from_sums(s, sq, cnt)
    with np.errstate(invalid="ignore", divide="ignore"):
        return variance / (mean * mean)


def apply_lee_weight(
    array: np.ndarray,
    valid_mask: np.ndarray,
    mean: np.ndarray,
    variance: np.ndarray,
    valid_count: np.ndarray,
    enl: float,
    nodata: float,
) -> np.ndarray:
    """
    지역 평균/분산이 주어졌을 때 표준 Lee MMSE 가중치를 적용한다
    (Lee/Refined Lee 등 Lee 계열 공통):

        sigma_v^2 = 1 / enl                          (speckle 상대분산)
        var_x     = max(0, (var_y - mean^2 * sigma_v^2) / (1 + sigma_v^2))
                                                     (신호 분산의 불편추정)
        weight    = var_x / var_y
        output    = local_mean + weight * (input - local_mean)

    var_y(관측 분산)에서 speckle이 기여한 몫(mean^2 * sigma_v^2)을 빼서
    신호 자체의 분산 var_x를 추정하고, weight = var_x/var_y 비율만큼만
    원본값을 신뢰한다. 완전히 균질한 영역(var_y ≈ mean^2/enl)에서는
    var_x ≈ 0 → weight ≈ 0이 되어 지역 평균으로 완전히 대체되고, 경계처럼
    실제 신호 변화가 큰 곳(var_y >> speckle 분산)에서는 weight → 1로
    원본값을 유지한다.

    참고 (2026-07-13 코드 리뷰 R-01): 이전 구현은
    weight = var_y / (var_y + mean^2/enl) 형태였는데, 이는 분자에 신호
    분산이 아닌 관측 분산을 쓰는 오류로, 균질 영역에서 weight가 0이 아닌
    0.5로 수렴해 speckle 분산의 25%가 잔존했다 (수치 시뮬레이션으로 검증).
    현재 공식은 Lee (1980) 원 논문 및 SNAP 구현(Lee.java의
    w = 1 - Cu^2/Ci^2, RefinedLee.java의 varX=(varY-meanY^2*sv)/(1+sv),
    b=varX/varY)과 일치한다.
    """
    sigma_v2 = 1.0 / enl
    with np.errstate(invalid="ignore", divide="ignore"):
        signal_variance = np.maximum(
            (variance - (mean**2) * sigma_v2) / (1.0 + sigma_v2), 0.0
        )
        weight = signal_variance / variance
    # variance == 0인 경우(완전히 평평한 영역)나 nan(전부 nodata인 윈도우)은
    # weight를 0으로 두어 지역 평균을 그대로 사용한다.
    weight = np.where(np.isfinite(weight), weight, 0.0)

    # nodata 영역에서는 mean 자체가 nan일 수 있어(0/0), 아래 연산이 nan을
    # 낳을 수 있다. 어차피 다음 줄에서 nodata로 덮어쓸 것이므로 관련 경고만
    # 억제한다.
    with np.errstate(invalid="ignore"):
        filtered = mean + weight * (array - mean)

    # 원래 nodata였던 픽셀이나, 윈도우 내에 유효 픽셀이 하나도 없었던
    # 위치는 결과도 nodata로 유지한다.
    return np.where(valid_mask & (valid_count > 0), filtered, nodata)


def make_mmse_filter_fn(stats_fn: StatsFn, enl: float) -> FilterFn:
    """
    stats_fn(지역 평균/분산/유효개수)과 표준 Lee MMSE 가중치를 합쳐
    FilterFn을 만든다. Lee / Refined Lee가 이걸 쓴다 (Gamma MAP처럼 가중치
    공식이 다른 필터는 자체 FilterFn을 만든다).
    """

    def filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
        mean, variance, valid_count = stats_fn(array, valid_mask, window_size)
        return apply_lee_weight(array, valid_mask, mean, variance, valid_count, enl, nodata)

    return filter_fn


def windowed_reduce(
    array: np.ndarray,
    valid_mask: np.ndarray,
    window_size: int,
    reducer: Callable[[np.ndarray], np.ndarray],
    fill_value: float = np.nan,
    col_block: int = 1024,
) -> np.ndarray:
    """
    적분영상으로 표현할 수 없는 필터(Median, Frost 등)를 위한 범용 이동
    윈도우 리듀서.

    각 픽셀 위치에서 k x k 윈도우의 값들을 마지막 축으로 쌓은 (rows, cols,
    k*k) 뷰를 만들고, reducer(그 뷰)로 (rows, cols) 결과를 낸다. reducer는
    마지막 축(axis=-1)에 대해 동작해야 하며, 무효(nodata) 위치는 fill_value로
    채워져 들어온다 (예: median은 np.nanmedian, fill=nan).

    메모리: 전체를 한 번에 stride하면 (rows*cols*k*k) 크기라 크므로, 열을
    col_block씩 나눠 처리한다. 이미지/스트립 경계는 fill_value로 padding해
    (적분영상 필터의 0-padding과 동일한 취지로) run_speckle_filter의 halo
    모델과 함께 블록-전체로드 동등성을 유지한다.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    k = window_size
    pad = k // 2
    rows, cols = array.shape

    filled = np.where(valid_mask, array, fill_value).astype(np.float64)
    padded = np.pad(filled, pad, mode="constant", constant_values=fill_value)

    result = np.empty((rows, cols), dtype=np.float64)
    for c0 in range(0, cols, col_block):
        c1 = min(c0 + col_block, cols)
        # 이 열 블록의 윈도우를 만들려면 padded의 [:, c0 : c1+2*pad] 가 필요.
        sub = padded[:, c0 : c1 + 2 * pad]
        view = sliding_window_view(sub, (k, k))  # (rows, c1-c0, k, k)
        stacked = view.reshape(view.shape[0], view.shape[1], k * k)
        result[:, c0:c1] = reducer(stacked)

    return result


# 스트립(블록) 처리 시 한 번에 읽는 행 수. 스트립 하나가 (STRIP_ROWS +
# 2*halo) x 전체폭 크기의 float64 중간 배열 여러 개를 만들므로, 512면
# 폭 1만 픽셀급 장면에서도 스트립당 수백 MB 수준으로 유지된다. 테스트에서
# 전체 로드 결과와의 동등성 검증을 위해 monkeypatch 대상이기도 하다.
STRIP_ROWS = 512


def run_speckle_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int,
    nodata: float | None,
    filter_fn: FilterFn,
) -> Path:
    """
    모든 speckle 필터가 공유하는 GeoTIFF 입출력 + 밴드별/스트립별 루프.

    filter_fn만 갈아끼우면 다른 필터가 된다 (Lee 계열은 make_mmse_filter_fn
    으로, Median/Frost 등은 자체 FilterFn으로).

    메모리 (2026-07-13 리뷰 R-07 반영): 밴드 전체를 한 번에 올리는 대신,
    STRIP_ROWS 행씩 halo(= window_size//2 행) 겹침을 두고 스트립 단위로
    처리한다. 출력 행 y의 윈도우는 최대 y±halo 행까지만 참조하므로, 읽기
    범위를 [y0-halo, y1+halo)로 잡으면 스트립 처리 결과가 전체 로드 결과와
    (부동소수점 누적합 순서 차이를 제외하면) 동일하다 — 이 동등성은
    tests의 회귀 테스트로 검증한다. 이미지 상/하단 경계에서는 경계 밖을
    제외(적분영상은 0-padding, windowed_reduce는 fill_value)하는 방식으로
    처리되어 동작이 변하지 않는다.
    """
    input_tif = Path(input_tif)
    output_tif = Path(output_tif)
    output_tif.parent.mkdir(parents=True, exist_ok=True)

    halo = window_size // 2

    with rasterio.open(input_tif) as src:
        profile = src.profile.copy()
        src_nodata = nodata if nodata is not None else src.nodata
        if src_nodata is None:
            raise ValueError(
                "nodata 값을 확인할 수 없습니다. nodata 인자를 명시하거나 "
                "입력 GeoTIFF에 nodata 태그를 설정하세요."
            )

        # 원본이 strip 방식(비-tiled) GeoTIFF였다면 blockxsize/blockysize가
        # 16의 배수가 아닐 수 있어(예: width 그대로), tiled=True와 함께
        # 그대로 쓰면 GDAL이 에러를 낸다. 항상 안전한 256으로 고정한다.
        profile.update(
            dtype="float32",
            nodata=src_nodata,
            tiled=True,
            blockxsize=256,
            blockysize=256,
            compress="deflate",
            predictor=3,
            BIGTIFF="IF_SAFER",
        )

        height = src.height
        width = src.width

        with rasterio.open(output_tif, "w", **profile) as dst:
            for band_index in range(1, src.count + 1):
                for y0 in range(0, height, STRIP_ROWS):
                    y1 = min(y0 + STRIP_ROWS, height)
                    # halo만큼 위아래로 넓혀 읽는다 (이미지 경계에서 클램프).
                    ry0 = max(0, y0 - halo)
                    ry1 = min(height, y1 + halo)

                    window = rasterio.windows.Window(0, ry0, width, ry1 - ry0)
                    array = src.read(band_index, window=window, out_dtype="float64")
                    valid_mask = np.isfinite(array) & (array != src_nodata)

                    filtered = filter_fn(array, valid_mask, window_size, src_nodata)
                    # 원래 유효했던 픽셀만 필터값을 쓰고, 무효/비유한 결과는
                    # nodata로 강제한다 (모든 필터에 공통 적용되는 안전망).
                    filtered = np.where(
                        valid_mask & np.isfinite(filtered), filtered, src_nodata
                    )

                    # halo를 제외한 "본 스트립" 행만 잘라서 쓴다.
                    out = filtered[y0 - ry0 : y1 - ry0].astype(np.float32)
                    dst.write(
                        out,
                        band_index,
                        window=rasterio.windows.Window(0, y0, width, y1 - y0),
                    )

    return output_tif
