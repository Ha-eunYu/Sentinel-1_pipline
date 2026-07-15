"""
Lee adaptive speckle filter (정사각형 단일 윈도우 버전).

각 픽셀마다 하나의 정사각형(window_size x window_size) 윈도우 전체로 지역
평균/분산을 구한 뒤, base.apply_lee_weight의 가중치 공식으로 필터링한다.
구현이 단순하고 빠르지만, 경계(예: 홍수 지도에서 물/육지 경계) 근처에서는
윈도우 안에 서로 다른 두 클래스 값이 섞여 들어가 경계가 1~2픽셀 정도
흐려질 수 있다 (경계 보존이 더 중요하면 refined_lee.py 참고).

참조문헌 (references.py의 "lee" 항목):
- J.S. Lee, "Digital image enhancement and noise filtering by use of local
  statistics," IEEE TPAMI, PAMI-2(2):165-168, 1980.
- J.S. Lee, "Speckle analysis and smoothing of synthetic aperture radar
  images," Computer Graphics and Image Processing, 17(1):24-32, 1981.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import (
    full_window_sums,
    make_mmse_filter_fn,
    mean_variance_from_sums,
    run_speckle_filter,
    validate_window_size,
)

MIN_WINDOW_SIZE = 3


def full_window_stats(
    array: np.ndarray, valid_mask: np.ndarray, window_size: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """정사각형 window_size x window_size 윈도우 하나로 (평균, 분산, 유효개수)를 낸다."""
    s, sq, count = full_window_sums(array, valid_mask, window_size)
    mean, variance = mean_variance_from_sums(s, sq, count)
    return mean, variance, count


def lee_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 5,
    enl: float = 4.0,
    nodata: float | None = None,
) -> Path:
    """
    plain Lee 필터를 linear power GeoTIFF에 적용한다.

    Parameters
    ----------
    window_size:
        3 이상의 홀수. 클수록 speckle을 더 줄이지만 해상도(디테일)가 희생된다.
    enl:
        Equivalent Number of Looks. 입력 제품의 실제 룩 수에 맞춰야 한다
        (product.xml의 numberOfAzimuthLooks * numberOfRangeLooks). 값이
        클수록 필터 강도가 약해진다(= speckle이 덜 지워짐).
    nodata:
        생략하면 입력 GeoTIFF의 nodata 태그를 쓴다. 둘 다 없으면 에러.
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    filter_fn = make_mmse_filter_fn(full_window_stats, enl)
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, filter_fn)
