"""
SAR speckle 잡음 제거 필터 패키지.

SAR 영상은 coherent imaging 특성상 곱셈성 잡음(speckle)을 가진다. 일반적인
평균/가우시안 필터는 speckle을 줄이는 대신 경계(edge)도 뭉개버리는 반면,
여기 구현된 적응형 필터들은 지역 통계를 이용해 "균일한 영역은 평활화하고,
변화가 큰 영역(경계)은 원본을 유지"한다.

이 필터들은 반드시 linear power 영상(dB 변환 전)에 적용해야 한다.
speckle의 곱셈성 잡음 모델(관측값 = 실제값 * 잡음)이 dB 영역에서는
성립하지 않기 때문이다. 그래서 pipeline.py에서 conversion.linear_to_db()
보다 먼저 호출된다.

패키지 구성
----------
    base.py          적분영상/이동통계, Lee 가중치, sliding-window 리듀서,
                     블록/halo GeoTIFF I/O 루프(run_speckle_filter) 등 공통 인프라
    lee.py           Lee (정사각형 단일 윈도우 MMSE)
    refined_lee.py   Refined Lee (방향성 서브윈도우, 단순화 구현)
    gamma_map.py     Gamma MAP (Gamma 분포 반사도 가정 MAP)
    frost.py         Frost (지역 분산 적응 지수 가중 커널)
    lee_sigma.py     Improved Lee Sigma (sigma 구간 내 이웃만 평균)
    median.py        Median (순서통계, outlier 강건)
    references.py    SNAP의 모든 speckle 필터 목록 + 참조문헌 카탈로그
    __init__.py      FilterMethod enum + apply_speckle_filter 디스패처 (이 파일)

새 필터를 추가하려면: base.FilterFn 시그니처의 함수를 새 모듈에 구현해
base.run_speckle_filter에 넘기고(적분영상 통계는 make_mmse_filter_fn,
윈도우 스택이 필요하면 windowed_reduce 활용), FilterMethod에 항목을 추가한
뒤 apply_speckle_filter 디스패처에 분기를 넣으면 된다. 각 필터의 근거
논문은 references.py에 정리되어 있다.

필터 선택 가이드 (요약)
----------------------
- lee: 가장 단순/빠름. 경계가 다소 흐려질 수 있음.
- refined_lee: 경계 보존이 좋음(홍수 물/육지 경계 등). 계산량 약 5배.
- gamma_map: 텍스처 있는 지표(숲/도심)에 자연스러움 (Gamma 분포 가정).
- frost: damping으로 평활화 강도 조절. 점 표적 보존 양호.
- lee_sigma: SNAP 기본 필터. sigma 구간 밖 이웃을 배제해 점 표적을 보존.
- median: 적응형 아님. 강한 outlier(코너 리플렉터) 제거에 강건. 주로
  전처리용.
모든 필터는 base.run_speckle_filter의 블록/halo 처리를 공유하며, 블록 처리
결과가 전체 로드와 비트 단위로 동일함을 테스트로 검증한다.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from . import frost as _frost
from . import gamma_map as _gamma_map
from . import lee as _lee
from . import lee_sigma as _lee_sigma
from . import median as _median
from . import refined_lee as _refined_lee
from .base import (
    FilterFn,
    apply_lee_weight,
    integral_image,
    make_mmse_filter_fn,
    mean_variance_from_sums,
    run_speckle_filter,
    validate_window_size,
)
from .frost import frost_filter
from .gamma_map import gamma_map_filter
from .lee import lee_filter
from .lee_sigma import lee_sigma_filter
from .median import median_filter
from .references import SNAP_SPECKLE_FILTERS, FilterReference, format_references
from .refined_lee import refined_lee_filter


class FilterMethod(str, Enum):
    """apply_speckle_filter()가 지원하는 speckle 필터 종류."""

    LEE = "lee"
    REFINED_LEE = "refined_lee"
    GAMMA_MAP = "gamma_map"
    FROST = "frost"
    LEE_SIGMA = "lee_sigma"
    MEDIAN = "median"


# 필터별 최소 윈도우 크기 (각 모듈의 MIN_WINDOW_SIZE와 동기화)
_MIN_WINDOW = {
    FilterMethod.LEE: _lee.MIN_WINDOW_SIZE,
    FilterMethod.REFINED_LEE: _refined_lee.MIN_WINDOW_SIZE,
    FilterMethod.GAMMA_MAP: _gamma_map.MIN_WINDOW_SIZE,
    FilterMethod.FROST: _frost.MIN_WINDOW_SIZE,
    FilterMethod.LEE_SIGMA: _lee_sigma.MIN_WINDOW_SIZE,
    FilterMethod.MEDIAN: _median.MIN_WINDOW_SIZE,
}


def make_filter_fn(
    method: FilterMethod | str,
    window_size: int = 5,
    enl: float = 4.0,
    min_valid_fraction: float = 0.5,
    damping: float = 2.0,
    sigma: float = 0.9,
) -> FilterFn:
    """
    method/하이퍼파라미터로부터 `FilterFn`(배열 → 필터링된 배열)을 만든다.

    파일 기반 경로(apply_speckle_filter)와 메모리 기반 경로(qa 모듈의 필터
    비교)가 **같은 필터 구성 코드**를 공유하도록 하는 단일 진입점이다. 덕분에
    QA에서 측정한 필터 거동이 실제 파이프라인이 쓰는 필터와 정확히 일치한다.

    반환된 FilterFn은 `(array, valid_mask, window_size, nodata) -> filtered`
    시그니처이며, 블록/halo I/O는 base.run_speckle_filter가 담당한다.
    """
    method = FilterMethod(method)
    validate_window_size(window_size, _MIN_WINDOW[method])

    if method is FilterMethod.LEE:
        return make_mmse_filter_fn(_lee.full_window_stats, enl)

    if method is FilterMethod.REFINED_LEE:
        def stats_fn(array, valid_mask, window):
            return _refined_lee.directional_window_stats(
                array, valid_mask, window, min_valid_fraction
            )
        return make_mmse_filter_fn(stats_fn, enl)

    if method is FilterMethod.GAMMA_MAP:
        return _gamma_map._gamma_map_filter_fn(enl)

    if method is FilterMethod.FROST:
        return _frost._frost_filter_fn(damping)

    if method is FilterMethod.LEE_SIGMA:
        if not 0.0 < sigma < 1.0:
            raise ValueError(f"sigma는 (0, 1) 구간이어야 합니다: {sigma}")
        return _lee_sigma._lee_sigma_filter_fn(enl, sigma)

    if method is FilterMethod.MEDIAN:
        return _median._median_filter_fn

    raise ValueError(f"지원하지 않는 필터 방식입니다: {method}")  # pragma: no cover


def apply_speckle_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    method: FilterMethod | str = FilterMethod.LEE,
    window_size: int = 5,
    enl: float = 4.0,
    nodata: float | None = None,
    min_valid_fraction: float = 0.5,
    damping: float = 2.0,
    sigma: float = 0.9,
) -> Path:
    """
    method에 따라 speckle 필터를 적용하는 디스패처.

    Parameters
    ----------
    method:
        FilterMethod 중 하나: lee / refined_lee / gamma_map / frost /
        lee_sigma / median.
    window_size:
        홀수. lee/gamma_map/frost/median은 3 이상, refined_lee/lee_sigma는
        5 이상(7 권장).
    enl:
        Equivalent Number of Looks. lee/refined_lee/gamma_map/lee_sigma에서
        쓰인다 (median/frost는 무시). 값이 클수록 필터 강도가 약해진다.
    nodata:
        생략하면 입력 GeoTIFF의 nodata 태그를 쓴다. 둘 다 없으면 에러.
    min_valid_fraction:
        refined_lee 전용 (refined_lee.py 참고).
    damping:
        frost 전용. 지수 가중 감쇠 계수 (기본 2.0).
    sigma:
        lee_sigma 전용. sigma percentage 0~1 (기본 0.9).
    """
    filter_fn = make_filter_fn(
        method,
        window_size=window_size,
        enl=enl,
        min_valid_fraction=min_valid_fraction,
        damping=damping,
        sigma=sigma,
    )
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, filter_fn)


__all__ = [
    "FilterMethod",
    "apply_speckle_filter",
    "make_filter_fn",
    "FilterFn",
    "lee_filter",
    "refined_lee_filter",
    "gamma_map_filter",
    "frost_filter",
    "lee_sigma_filter",
    "median_filter",
    # 참조문헌 카탈로그
    "SNAP_SPECKLE_FILTERS",
    "FilterReference",
    "format_references",
    # base 재노출(다른 필터를 추가로 구현할 때 쓰라고)
    "run_speckle_filter",
    "apply_lee_weight",
    "integral_image",
    "mean_variance_from_sums",
    "validate_window_size",
]
