"""
Refined Lee speckle filter (방향성 서브윈도우 버전, 단순화 구현).

정사각형 윈도우 하나 대신, 픽셀을 기준으로 한 5개의 후보 영역
(전체/상/하/좌/우 절반)의 평균/분산을 모두 계산해두고, 그중 "가장
균질한(분산이 가장 작은)" 후보를 골라 그 통계로 필터링한다. 경계에 걸친
픽셀이라면 경계를 가로지르지 않는 방향의 절반 윈도우가 선택되므로, plain
Lee(lee.py)보다 경계 보존이 좋다.

참조문헌 및 이 구현의 단순화 (references.py의 "refined_lee" 항목도 참고)
--------------------------------------------------------------------
방향성(edge-aligned) 윈도우로 경계를 보존한다는 핵심 아이디어의 원 논문은
J.S. Lee, "Refined filtering of image noise using local statistics,"
Computer Graphics and Image Processing, 15(4):380-389, 1981. SNAP이 구현한
"Refined Lee" 연산자는 고정 7x7 윈도우 안에서 3x3 서브영역 평균으로 gradient를
구해 대각선 포함 8방향 edge-aligned 마스크 중 하나를 고르며(참고: SNAP 소스
RefinedLee.java, 그리고 Lee & Pottier, "Polarimetric Radar Imaging," CRC
Press, 2009; 방향 판정용 compass gradient는 G.S. Robinson, "Edge detection by
compass gradient masks," CGIP 6(5):492-502, 1977). 균질/이질/점 표적
(point target) 3단계 분류와 그 임계값(국소 변동계수 Cu/Cmax)은 별개 논문인
Lopes, Touzi, Nezry, "Adaptive speckle filters and scene heterogeneity,"
IEEE TGRS 28(6):992-1000, 1990 (및 Lopes, Nezry, Touzi, Laur, 1993)에서 나온
것이다.

이 구현이 SNAP 전체 구현과 다른(단순화한) 점:
(a) 사각형 적분영상(integral image)으로 O(픽셀 수)에 계산 가능한 상하좌우
    4방향 + 전체, 총 5개 후보만 쓴다. 대각선 4방향은 사각형이 아니라
    적분영상으로 계산이 안 돼 생략했다.
(b) Lopes 등의 Cu/Cmax 기반 점 표적(코너 리플렉터 등) 분류·건너뛰기 로직은
    포함하지 않는다.
따라서 대각선 방향 경계나 강한 점 표적 근처에서는 SNAP 등의 전체 구현보다
개선 폭이 작을 수 있다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import (
    integral_image,
    make_mmse_filter_fn,
    mean_variance_from_sums,
    run_speckle_filter,
    validate_window_size,
)

MIN_WINDOW_SIZE = 5


def _directional_rect_sums(
    integral: np.ndarray, rows: int, cols: int, window_size: int
) -> dict[str, np.ndarray]:
    """
    integral_image()로 만든 적분영상 하나에서, 5가지 후보 사각형 영역
    (전체 윈도우 / 상반 / 하반 / 좌반 / 우반)의 이동합을 한 번에 계산한다.

    "절반" 윈도우는 대칭이 아니라, 현재 픽셀이 그 사각형의 가장자리 행/열이
    되도록 잡는다 (예: "상반"은 현재 픽셀을 포함해 그 위쪽으로 뻗은
    영역이다). 이렇게 해야 "픽셀을 기준으로 특정 방향에 균질한 영역이
    있는지"를 검사하는 것이 된다.

    반환되는 각 배열의 shape는 (rows, cols)이며, 각 formula는 브루트포스
    슬라이딩 윈도우 합과 대조해 수치적으로 검증했다.
    """
    k = window_size
    p = k // 2

    full = integral[k:, k:] - integral[:-k, k:] - integral[k:, :-k] + integral[:-k, :-k]
    top = (
        integral[p + 1 : p + 1 + rows, k:]
        - integral[0:rows, k:]
        - integral[p + 1 : p + 1 + rows, :-k]
        + integral[0:rows, :-k]
    )
    bottom = (
        integral[k:, k:] - integral[p : p + rows, k:] - integral[k:, :-k] + integral[p : p + rows, :-k]
    )
    left = (
        integral[k:, p + 1 : p + 1 + cols]
        - integral[:-k, p + 1 : p + 1 + cols]
        - integral[k:, 0:cols]
        + integral[:-k, 0:cols]
    )
    right = (
        integral[k:, k:] - integral[:-k, k:] - integral[k:, p : p + cols] + integral[:-k, p : p + cols]
    )

    return {"full": full, "top": top, "bottom": bottom, "left": left, "right": right}


def directional_window_stats(
    array: np.ndarray,
    valid_mask: np.ndarray,
    window_size: int,
    min_valid_fraction: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    전체/상/하/좌/우 5개 후보 중, 유효 픽셀이 충분하면서 분산이 가장
    작은(=가장 균질한) 후보를 픽셀별로 선택해 그 (평균, 분산, 유효개수)를
    반환한다.

    min_valid_fraction: 후보 윈도우의 유효 픽셀 수가 "그 후보의 이론적
    픽셀 수 * min_valid_fraction" 보다 적으면 후보에서 제외한다. 유효
    픽셀이 몇 개 안 남은 후보는 분산 추정이 불안정해서(우연히 아주 작게
    나올 수 있음) 잘못 선택되기 쉽기 때문이다.
    """
    rows, cols = array.shape
    k = window_size
    p = k // 2
    zeroed = np.where(valid_mask, array, 0.0)

    sums = _directional_rect_sums(integral_image(zeroed, p), rows, cols, k)
    sums_sq = _directional_rect_sums(integral_image(zeroed * zeroed, p), rows, cols, k)
    counts = _directional_rect_sums(integral_image(valid_mask.astype(np.float64), p), rows, cols, k)

    nominal_size = {
        "full": k * k,
        "top": (p + 1) * k,
        "bottom": (p + 1) * k,
        "left": k * (p + 1),
        "right": k * (p + 1),
    }

    best_mean: np.ndarray | None = None
    best_variance: np.ndarray | None = None
    best_count: np.ndarray | None = None

    for name, min_size in nominal_size.items():
        count = counts[name]
        mean, variance = mean_variance_from_sums(sums[name], sums_sq[name], count)

        enough_valid = count >= (min_valid_fraction * min_size)
        variance = np.where(enough_valid, variance, np.inf)

        if best_variance is None:
            best_mean, best_variance, best_count = mean, variance, count
        else:
            better = variance < best_variance
            best_mean = np.where(better, mean, best_mean)
            best_count = np.where(better, count, best_count)
            best_variance = np.minimum(best_variance, variance)

    # 후보가 전부 제외된(주변이 온통 nodata인) 픽셀은 분산이 inf로 남는데,
    # 그런 픽셀은 valid_count도 0에 가까워 호출부에서 어차피 nodata로
    # 덮어쓰므로, 여기서는 계산이 끊기지 않도록 0으로만 바꿔둔다.
    best_variance = np.where(np.isfinite(best_variance), best_variance, 0.0)

    return best_mean, best_variance, best_count


def refined_lee_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 7,
    enl: float = 4.0,
    nodata: float | None = None,
    min_valid_fraction: float = 0.5,
) -> Path:
    """
    Refined Lee 필터를 linear power GeoTIFF에 적용한다.

    Parameters
    ----------
    window_size:
        5 이상의 홀수(7 권장). refined_lee는 상하좌우 절반 윈도우 각각에도
        충분한 픽셀 수가 필요해 최소 5가 요구된다.
    enl / nodata:
        lee_filter와 동일한 의미.
    min_valid_fraction:
        각 방향 후보 윈도우가 유효 픽셀로 채워져야 하는 최소 비율
        (0.5 = 이론적 픽셀 수의 절반 이상은 유효해야 후보로 인정).
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)

    def stats_fn(
        array: np.ndarray, valid_mask: np.ndarray, window: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return directional_window_stats(array, valid_mask, window, min_valid_fraction)

    filter_fn = make_mmse_filter_fn(stats_fn, enl)
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, filter_fn)
