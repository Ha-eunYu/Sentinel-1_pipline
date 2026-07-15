"""
Improved Lee Sigma speckle filter.

원 Lee Sigma(1983)는 "중심 픽셀값의 ±sigma 구간에 드는 이웃만 평균"내는
sigma 필터인데, 곱셈성 speckle에서는 sigma 구간을 잡는 방식이 편향을
낳는다. Improved Lee Sigma(Lee et al. 2009)는 이를 개선한다
(references.py의 Lee Sigma 항목).

이 구현(단순화판)의 절차:
  1) MMSE 1차 추정: 정사각형 윈도우로 지역 평균/분산을 구해 Lee MMSE로
     "사전 평균(a priori mean)" xbar을 만든다 (base.apply_lee_weight와 동일
     공식). 이 xbar이 sigma 구간의 중심이 된다.
  2) sigma 구간: 곱셈성 잡음의 sigma 범위 [I1, I2]를 xbar에 비례해 잡는다
     (I1 = A1 * xbar, I2 = A2 * xbar). 계수 (A1, A2)는 원 논문이 ENL과
     "sigma percentage"(0.5~0.9)에 대해 표로 준 값인데, 여기서는 감마
     분포의 해당 백분위수로 근사한다 (scipy 없이: 감마 분위수를 뉴턴법으로).
  3) 구간에 드는 이웃만 골라 그 평균으로 대체한다. 구간에 드는 이웃이 너무
     적으면(예: 강한 점 표적) 원본을 유지한다.

메모리: base.windowed_reduce와 같은 열-블록 sliding window로 이웃 스택을
만들고, 중심별 [I1, I2] 임계로 마스킹해 평균낸다. xbar/임계는 적분영상으로
미리 구한다.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .base import (
    apply_lee_weight,
    full_window_sums,
    mean_variance_from_sums,
    run_speckle_filter,
    validate_window_size,
)

MIN_WINDOW_SIZE = 3
_COL_BLOCK = 1024

# 사용 가능한 sigma 백분위(구간이 담는 확률). 원 논문의 sigma percentage.
SIGMA_CHOICES = (0.5, 0.6, 0.7, 0.8, 0.9)


def _gamma_ppf(prob: float, enl: float) -> float:
    """
    평균 1, shape=ENL 인 감마분포(즉 정규화 speckle)의 prob 분위수.

    scipy 없이 뉴턴-이분 혼합으로 정규화 하한 불완전감마 P(a,x)=prob를 푼다.
    (speckle 세기 I는 shape=L, scale=1/L 감마 → 여기서는 x를 L배 스케일.)
    """
    a = enl
    # P(a, y) = prob 를 y에 대해 풀고, I = y / a (평균 1 정규화).
    lo, hi = 0.0, max(20.0, a * 5.0)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _reg_lower_gamma(a, mid) < prob:
            lo = mid
        else:
            hi = mid
    y = 0.5 * (lo + hi)
    return y / a


def _reg_lower_gamma(a: float, x: float) -> float:
    """정규화 하한 불완전감마 P(a, x). 급수/연분수 표준 구현."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        # 급수 전개
        term = 1.0 / a
        total = term
        n = a
        for _ in range(500):
            n += 1.0
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # 연분수 (Lentz)
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def _lee_sigma_filter_fn(enl: float, sigma: float):
    # 구간 [I1, I2] = [A1, A2] * xbar. A1/A2는 정규화 speckle의 대칭 백분위.
    tail = (1.0 - sigma) / 2.0
    a1 = _gamma_ppf(tail, enl)
    a2 = _gamma_ppf(1.0 - tail, enl)

    def filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
        # 1) MMSE 사전 평균 xbar (적분영상).
        s, sq, cnt = full_window_sums(array, valid_mask, window_size)
        mean, variance = mean_variance_from_sums(s, sq, cnt)
        xbar = apply_lee_weight(array, valid_mask, mean, variance, cnt, enl, np.nan)
        # xbar이 nan(무효)인 곳은 그대로 두고, 유효한 곳만 아래서 처리.

        i1 = a1 * xbar
        i2 = a2 * xbar

        k = window_size
        pad = k // 2
        rows, cols = array.shape
        filled = np.where(valid_mask, array, np.nan).astype(np.float64)
        padded = np.pad(filled, pad, mode="constant", constant_values=np.nan)

        result = np.array(array, dtype=np.float64)  # 기본값: 원본 유지
        for c0 in range(0, cols, _COL_BLOCK):
            c1 = min(c0 + _COL_BLOCK, cols)
            sub = padded[:, c0 : c1 + 2 * pad]
            view = sliding_window_view(sub, (k, k))
            stack = view.reshape(view.shape[0], view.shape[1], k * k)  # (rows, cblk, k*k)

            lo = i1[:, c0:c1, None]
            hi = i2[:, c0:c1, None]
            with np.errstate(invalid="ignore"):
                in_range = np.isfinite(stack) & (stack >= lo) & (stack <= hi)
                count = in_range.sum(axis=-1)
                vals = np.where(in_range, stack, 0.0)
                mean_in = np.where(count > 0, vals.sum(axis=-1) / np.maximum(count, 1), np.nan)

            # 구간에 이웃이 충분히 있으면 그 평균으로, 아니면 원본 유지.
            block = result[:, c0:c1]
            enough = count >= 1
            result[:, c0:c1] = np.where(enough & np.isfinite(mean_in), mean_in, block)

        return result

    return filter_fn


def lee_sigma_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = 7,
    enl: float = 4.0,
    nodata: float | None = None,
    sigma: float = 0.9,
) -> Path:
    """
    Improved Lee Sigma 필터를 linear power GeoTIFF에 적용한다.

    Parameters
    ----------
    window_size:
        3 이상의 홀수 (7 권장).
    enl:
        Equivalent Number of Looks. sigma 구간 계수 계산에 쓰인다.
    sigma:
        sigma percentage (0.5~0.9 중 하나 권장, 기본 0.9). 클수록 더 넓은
        구간을 잡아 더 많은 이웃을 평균낸다(평활화 강함).
    nodata:
        생략 시 입력 GeoTIFF의 nodata 태그 사용.
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    if not 0.0 < sigma < 1.0:
        raise ValueError(f"sigma는 (0, 1) 구간이어야 합니다: {sigma}")
    return run_speckle_filter(
        input_tif, output_tif, window_size, nodata, _lee_sigma_filter_fn(enl, sigma)
    )
