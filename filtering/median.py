"""
Median speckle filter.

윈도우 내 유효 픽셀들의 중앙값으로 대체하는 순서통계(order-statistic)
필터다. 적응형이 아니라 어디서나 동일한 강도로 동작하지만:
- 강한 outlier(코너 리플렉터 등 비정상적으로 밝은 점 표적)에 매우 강건하고,
- speckle의 곱셈성 잡음 모델 가정이 틀려도 상관없이 동작한다.

단점: 균질/경계 구분 없이 평활화하므로 윈도우보다 좁은 선형 피처(좁은
수로, 도로)가 사라질 수 있다. 그래서 최종 필터보다는 outlier 억제용
전처리로 쓰는 경우가 많다 (references.py의 Median 항목 참고).

구현: 적분영상으로 표현할 수 없어 base.windowed_reduce(열-블록 sliding
window)를 쓰며, 무효 픽셀은 nan으로 채워 np.nanmedian으로 제외한다.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

from .base import run_speckle_filter, validate_window_size, windowed_reduce

MIN_WINDOW_SIZE = 3


def _median_filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
    # nan으로 채운 뒤 nanmedian → 무효(윈도우 밖/ nodata) 픽셀은 자동 제외.
    def reducer(stack: np.ndarray) -> np.ndarray:
        with warnings.catch_warnings():
            # 전부 nan인 윈도우(주변이 온통 nodata)는 nanmedian이 nan +
            # "All-NaN slice" 경고를 내는데, run_speckle_filter가 최종적으로
            # nodata로 덮으므로 이 경고만 억제한다.
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.nanmedian(stack, axis=-1)

    return windowed_reduce(array, valid_mask, window_size, reducer, fill_value=np.nan)


def median_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 5,
    nodata: float | None = None,
) -> Path:
    """
    Median 필터를 GeoTIFF에 적용한다. window_size는 3 이상 홀수.

    ENL 파라미터가 없다 (순서통계 필터라 speckle 통계 모델을 쓰지 않음).
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, _median_filter_fn)
