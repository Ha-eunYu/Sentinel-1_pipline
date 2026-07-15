"""
SAR speckle 필터 평가 지표.

필터를 고를 때 "speckle이 얼마나 줄었나"만 보면 안 된다. 실데이터에서 확인된
바로는, speckle 억제가 같아도 필터에 따라 **가는 선형 피처(소하천·수로)를
살리느냐 지우느냐가 크게 갈린다**. 그래서 이 모듈은 네 축으로 나눠 측정한다:

1. `equivalent_number_of_looks` — speckle 억제도 (균질부가 얼마나 매끈해졌나)
2. `thin_line_retention`        — **가는 어두운 선(소하천) 보존도**
3. `step_edge_retention`        — 계단형 경계(넓은 수체/농지 경계) 보존도
4. `fisher_separability`        — 수면/육지 2클래스 분리도 (분류 난이도)

2번과 3번은 **서로 다른 문제**다. refined_lee는 step edge에는 강하지만
(가장 균질한 서브윈도우를 고르므로) 폭 1~3픽셀 소하천 위에서는 "하천을 배제한
농지-only 서브윈도우"가 가장 균질하다고 판단해 하천을 지운다. lee_sigma도
밝은 점 표적은 보존하지만 어두운 가는 선은 지운다. 이 비대칭을 잡아내려면
2번 지표가 반드시 필요하다.

지표 규약
--------
- 입력은 **linear power**(dB 아님)를 기본으로 한다. speckle 통계 모델이
  linear에서만 성립하기 때문이다. dB가 필요한 지표(Otsu/Fisher)는 내부에서
  변환한다.
- 무효 픽셀은 nan으로 넘긴다 (nodata는 호출부에서 nan으로 바꿔둘 것).
- scipy를 쓰지 않는다 (numpy `sliding_window_view`만 사용).
"""

from __future__ import annotations

import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def _windows(array: np.ndarray, window_size: int) -> np.ndarray:
    """
    (rows, cols, k*k) 이동 윈도우 스택. 경계는 edge 복제로 패딩한다.

    지표 계산용이라 정확한 nodata 처리보다 단순함을 택했다 (필터 구현부의
    base.windowed_reduce와 달리 여기서는 통계 요약만 하므로 충분하다).
    """
    k = window_size
    pad = k // 2
    padded = np.pad(array, pad, mode="edge")
    view = sliding_window_view(padded, (k, k))
    return view.reshape(array.shape[0], array.shape[1], k * k)


def local_cv(linear: np.ndarray, window_size: int = 7) -> np.ndarray:
    """국소 변동계수 CV = std/mean (linear power 기준)."""
    v = _windows(linear, window_size)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mean = np.nanmean(v, axis=-1)
        std = np.nanstd(v, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return std / mean


def equivalent_number_of_looks(linear: np.ndarray, window_size: int = 7) -> float:
    """
    ENL 추정치 = 1 / median(국소 CV)^2. **클수록 speckle이 잘 억제된 것.**

    균질 영역에서 speckle의 CV는 1/sqrt(ENL)이므로 ENL = 1/CV^2가 된다.
    영상 전체의 국소 CV **중앙값**을 쓰는 이유: 장면의 대부분은 균질부라
    중앙값이 균질부 speckle 수준을 대표하고, 경계·점 표적 같은 소수의 고CV
    픽셀에 휘둘리지 않기 때문이다.
    """
    cv = local_cv(linear, window_size)
    med = np.nanmedian(cv)
    if not np.isfinite(med) or med <= 0:
        return float("nan")
    return float(1.0 / med**2)


def line_depth(linear: np.ndarray, window_size: int = 9) -> np.ndarray:
    """
    각 픽셀의 "어두운 선 깊이" = 국소 배경(윈도우 최댓값) − 픽셀값.

    소하천처럼 주변 농지보다 어두운 가는 선 위에서 큰 값이 된다. window_size는
    선 폭보다 넉넉히 커야(기본 9) 배경이 선에 오염되지 않는다. 형태학의
    black top-hat과 같은 취지지만 numpy만으로 계산한다.
    """
    v = _windows(linear, window_size)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        background = np.nanmax(v, axis=-1)
    return background - linear


def detect_thin_dark_lines(
    linear: np.ndarray,
    valid_mask: np.ndarray,
    window_size: int = 9,
    percentile: float = 99.0,
    presmooth: int = 3,
) -> np.ndarray:
    """
    미필터링 영상에서 소하천 후보(가는 어두운 선) 픽셀 마스크를 만든다.

    이 마스크는 **미필터링 영상에서 한 번만** 만들고, 모든 필터 결과를 이
    동일한 위치에서 평가해야 공정한 비교가 된다 (필터마다 다른 마스크를 쓰면
    비교가 무의미해진다).

    presmooth (중요): 검출 **전에** presmooth×presmooth 이동평균을 건다.
    speckle이 심한 원본(ENL≈1~4)에서 곧바로 line_depth 상위를 고르면, 실제
    하천이 아니라 **speckle로 우연히 어두워진 농지 픽셀**이 대거 섞인다
    (합성 테스트에서 검출 정확도 23%까지 떨어지는 것을 확인). 그러면 이후의
    "소하천 유지율"이 사실상 "speckle 보존율"을 재게 되어 지표가 무의미해진다.
    폭 2~3픽셀인 하천은 3×3 평균에도 충분히 살아남지만 단일 픽셀 speckle은
    사라지므로, 약한 사전 평활화만으로 검출이 크게 안정된다.
    presmooth<=1이면 사전 평활화를 하지 않는다.
    """
    src = linear
    if presmooth and presmooth > 1:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            src = np.nanmean(_windows(linear, presmooth), axis=-1)

    depth = line_depth(src, window_size)
    depth = np.where(valid_mask, depth, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        threshold = np.nanpercentile(depth, percentile)
    return (depth >= threshold) & valid_mask


def thin_line_retention(
    filtered: np.ndarray,
    reference: np.ndarray,
    line_mask: np.ndarray,
    window_size: int = 9,
) -> float:
    """
    소하천 유지율(%) = 필터 후 선 깊이 평균 / 미필터 선 깊이 평균 × 100.

    **클수록 가는 선이 잘 보존된 것.** 100%면 선의 대비가 그대로, 0%에
    가까우면 선이 배경에 녹아 사라졌다는 뜻이다.

    filtered/reference 모두 linear power이고 같은 격자여야 한다.
    """
    d_ref = line_depth(reference, window_size)
    d_out = line_depth(filtered, window_size)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        base = np.nanmean(d_ref[line_mask])
        got = np.nanmean(d_out[line_mask])
    if not np.isfinite(base) or base == 0:
        return float("nan")
    return float(got / base * 100.0)


def detect_strong_edges(
    linear: np.ndarray, valid_mask: np.ndarray, percentile: float = 98.0
) -> np.ndarray:
    """미필터링 영상의 gradient 상위 `percentile`% 위치 = 강한 계단형 경계."""
    db = to_db(linear)
    gy, gx = np.gradient(db)
    g = np.hypot(gy, gx)
    g = np.where(valid_mask, g, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        threshold = np.nanpercentile(g, percentile)
    return (g >= threshold) & valid_mask


def step_edge_retention(
    filtered: np.ndarray, reference: np.ndarray, edge_mask: np.ndarray
) -> float:
    """
    계단형 경계 보존율(%) = 필터 후 경계 gradient 평균 / 미필터 대비 × 100.

    **클수록 경계가 선명하게 남은 것.** dB 영역에서 gradient를 재는 이유는
    linear에서는 밝은 영역의 gradient가 과대평가되기 때문이다.
    """
    def mean_grad(x: np.ndarray) -> float:
        gy, gx = np.gradient(to_db(x))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return float(np.nanmean(np.hypot(gy, gx)[edge_mask]))

    base = mean_grad(reference)
    if not np.isfinite(base) or base == 0:
        return float("nan")
    return float(mean_grad(filtered) / base * 100.0)


def to_db(linear: np.ndarray) -> np.ndarray:
    """linear power → dB. 0 이하는 nan (log 미정의)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return 10.0 * np.log10(np.where(linear > 0, linear, np.nan))


def otsu_threshold(db: np.ndarray, bins: int = 256) -> float:
    """dB 히스토그램의 Otsu 임계값 (클래스간 분산 최대화)."""
    v = db[np.isfinite(db)]
    if v.size < 10:
        return float("nan")
    hist, edges = np.histogram(v, bins=bins)
    p = hist / hist.sum()
    centers = (edges[:-1] + edges[1:]) / 2.0

    w0 = np.cumsum(p)
    w1 = 1.0 - w0
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = np.cumsum(p * centers) / np.maximum(w0, 1e-12)
        m1 = np.cumsum((p * centers)[::-1])[::-1] / np.maximum(w1, 1e-12)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.nanargmax(between))])


def fisher_separability(linear: np.ndarray) -> tuple[float, float]:
    """
    Otsu로 저/고 후방산란 2클래스(수면/육지)로 나눈 뒤의 Fisher 분리도.

        분리도 = (클래스 평균차)^2 / (클래스 내 분산 합)

    **클수록 임계값 분류가 쉬움** = 홍수 수면 추출이 잘 된다는 뜻.

    Returns (임계값 dB, 분리도).
    """
    db = to_db(linear)
    thr = otsu_threshold(db)
    v = db[np.isfinite(db)]
    lo, hi = v[v <= thr], v[v > thr]
    if lo.size < 10 or hi.size < 10:
        return thr, float("nan")
    denom = lo.var() + hi.var()
    if denom == 0:
        return thr, float("nan")
    return thr, float((hi.mean() - lo.mean()) ** 2 / denom)
