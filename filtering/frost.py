"""
Frost speckle filter.

각 픽셀을, 윈도우 내 이웃들의 거리+지역 통계 기반 지수 가중 평균으로
대체한다. 가중치는

    w_ij = exp( -damping * Ci^2 * dist_ij )

로, dist_ij는 중심에서 이웃 (i,j)까지의 유클리드 거리, Ci^2 = var/mean^2는
중심 픽셀 윈도우의 관측 상대분산이다. 균질 영역(Ci^2 작음)에서는 가중치가
거의 평평해져 강하게 평활화되고(≈ 이동평균), 경계·텍스처 영역(Ci^2 큼)에서는
가중치가 중심에 급격히 집중되어 원본을 보존한다. 즉 Ci^2가 적응형 손잡이
역할을 한다 (references.py의 Frost 항목: Frost et al., IEEE TPAMI, 1982).

구현 노트:
- Ci^2(중심 픽셀별 지역 상대분산)는 적분영상으로 O(픽셀 수)에 구한다.
- 가중 평균 자체는 픽셀마다 가중치가 달라(중심 Ci^2에 의존) 단일 컨볼루션
  으로 안 되므로, base.windowed_reduce로 (rows, cols, k*k) 이웃 스택을
  만들고, 같은 순서로 만든 거리 스택과 중심별 Ci^2를 결합해 가중 평균을
  낸다. 무효(nodata) 이웃은 nan으로 들어와 가중치 0으로 처리된다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .base import FilterFn, full_window_ci2, run_speckle_filter, validate_window_size

MIN_WINDOW_SIZE = 3
_COL_BLOCK = 1024


def _distance_stack(window_size: int) -> np.ndarray:
    """k x k 윈도우 중심으로부터의 유클리드 거리를 (k*k,)로 편 벡터."""
    k = window_size
    p = k // 2
    yy, xx = np.mgrid[-p : p + 1, -p : p + 1]
    return np.sqrt(yy * yy + xx * xx).reshape(-1)


def _frost_filter_fn(damping: float) -> FilterFn:
    """
    Frost FilterFn. 가중치가 중심 픽셀별 Ci^2에 의존해 단일 컨볼루션으로
    안 되므로, base.windowed_reduce와 같은 열-블록 sliding window를 직접
    돌리되 중심별 Ci^2를 참조한다 (블록/halo 동등성은 그대로 유지).
    """

    def filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
        ci2 = full_window_ci2(array, valid_mask, window_size)  # 중심별 상대분산
        distances = _distance_stack(window_size)[None, None, :]  # (1,1,k*k)

        k = window_size
        pad = k // 2
        rows, cols = array.shape
        filled = np.where(valid_mask, array, np.nan).astype(np.float64)
        padded = np.pad(filled, pad, mode="constant", constant_values=np.nan)

        result = np.empty((rows, cols), dtype=np.float64)
        for c0 in range(0, cols, _COL_BLOCK):
            c1 = min(c0 + _COL_BLOCK, cols)
            sub = padded[:, c0 : c1 + 2 * pad]
            view = sliding_window_view(sub, (k, k))  # (rows, cblk, k, k)
            stack = view.reshape(view.shape[0], view.shape[1], k * k)

            a = ci2[:, c0:c1, None]  # (rows, cblk, 1)
            with np.errstate(invalid="ignore"):
                weights = np.exp(-damping * a * distances)  # (rows, cblk, k*k)
                valid = np.isfinite(stack)
                weights = np.where(valid, weights, 0.0)
                values = np.where(valid, stack, 0.0)
                wsum = weights.sum(axis=-1)
                result[:, c0:c1] = np.where(
                    wsum > 0, (weights * values).sum(axis=-1) / wsum, np.nan
                )

        return result

    return filter_fn


def frost_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 5,
    enl: float = 4.0,
    nodata: float | None = None,
    damping: float = 2.0,
) -> Path:
    """
    Frost 필터를 linear power GeoTIFF에 적용한다.

    Parameters
    ----------
    window_size:
        3 이상의 홀수.
    enl:
        시그니처 일관성을 위해 받지만, Frost는 지역 상대분산 Ci^2를 직접
        쓰므로 현재 구현에서는 사용하지 않는다 (인자 호환용).
    damping:
        지수 가중의 감쇠 계수. 클수록 경계에서 원본을 더 강하게 보존하고
        (평활화 약함), 작을수록 이동평균에 가까워진다. SNAP 기본값과 같은
        2.0을 기본으로 둔다.
    nodata:
        생략 시 입력 GeoTIFF의 nodata 태그 사용.
    """
    del enl  # 인자 호환용 (Frost는 사용하지 않음)
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, _frost_filter_fn(damping))
