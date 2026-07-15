"""
Gamma MAP (Maximum A Posteriori) speckle filter.

Lee 계열 필터가 장면 반사도(scene reflectivity)를 가우시안으로 가정하는
것과 달리, Gamma MAP은 반사도가 Gamma 분포를 따른다고 가정한다. 이는
"반사도는 음수가 될 수 없다"는 물리적 제약과 더 잘 맞아, 특히 텍스처가
있는 지표(숲, 도심 등)에서 Lee보다 자연스러운 결과를 낼 수 있다.

수식 (곱셈성 speckle, ENL = L, 지역 평균 mean, 지역 분산 var):

    Cu^2 = 1 / L                      (speckle 상대분산)
    Ci^2 = var / mean^2               (관측 상대분산)
    - Ci <= Cu 이면 (균질) : output = mean
    - Ci 가 매우 크면 (강한 텍스처/점 표적) : output = 관측값(원본) 유지
    - 그 외:
        alpha = (1 + Cu^2) / (Ci^2 - Cu^2)
        b     = alpha - L - 1
        d     = mean^2 * b^2 + 4 * alpha * L * mean * center
        output = (b * mean + sqrt(d)) / (2 * alpha)

이 2차식 해는 Gamma-분포 반사도 사전확률 하의 MAP 추정으로 유도된다
(references.py의 Gamma Map 항목: Lopes, Nezry, Touzi, Laur, IGARSS 1990;
기반 MAP은 Kuan et al. 1985/1987).

이 구현은 적분영상으로 지역 평균/분산을 O(픽셀 수)에 구하므로 Lee와 동일한
비용이며, base.run_speckle_filter의 블록/halo 모델을 그대로 쓴다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import FilterFn, run_speckle_filter, validate_window_size
from .lee import full_window_stats

MIN_WINDOW_SIZE = 3


def _gamma_map_filter_fn(enl: float) -> FilterFn:
    cu2 = 1.0 / enl
    # 점 표적(이질) 컷오프: Ci >= Cmax = sqrt(2)*Cu 이면 원본 유지.
    # SNAP GammaMap 및 Lopes et al. 1990의 3단계(균질/중간/이질) 분류와 동일.
    # (2026-07-14 코드 리뷰 R-2: docstring의 "Ci가 매우 크면 원본 유지" 분기가
    # 구현에 빠져 있어 점 표적까지 MAP 식으로 눌리던 것을 수정.)
    cmax2 = 2.0 * cu2

    def filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
        mean, variance, _ = full_window_stats(array, valid_mask, window_size)

        with np.errstate(invalid="ignore", divide="ignore"):
            ci2 = variance / (mean * mean)

            # 기본값: 원본 유지 (Ci >= Cmax 인 강한 텍스처/점 표적 영역 포함).
            out = array.copy()

            # 균질 영역(Ci <= Cu): 지역 평균으로 대체.
            homogeneous = ci2 <= cu2
            out = np.where(homogeneous, mean, out)

            # 중간 영역(Cu < Ci < Cmax): MAP 2차식 해.
            mixed = (~homogeneous) & (ci2 < cmax2) & np.isfinite(ci2)
            alpha = (1.0 + cu2) / (ci2 - cu2)
            b = alpha - enl - 1.0
            discriminant = mean * mean * b * b + 4.0 * alpha * enl * mean * array
            discriminant = np.maximum(discriminant, 0.0)
            r_hat = (b * mean + np.sqrt(discriminant)) / (2.0 * alpha)
            out = np.where(mixed, r_hat, out)

        return out

    return filter_fn


def gamma_map_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 7,
    enl: float = 4.0,
    nodata: float | None = None,
) -> Path:
    """
    Gamma MAP 필터를 linear power GeoTIFF에 적용한다.

    Parameters는 lee_filter와 동일한 의미(window_size는 3 이상 홀수, enl은
    Equivalent Number of Looks, nodata는 생략 시 입력 태그 사용).
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    return run_speckle_filter(input_tif, output_tif, window_size, nodata, _gamma_map_filter_fn(enl))
