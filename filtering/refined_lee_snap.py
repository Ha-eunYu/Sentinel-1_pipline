"""
Refined Lee speckle filter — **SNAP 충실 재현판** (7x7 고정, 8방향 edge-aligned).

refined_lee.py(단순화판, 5후보·대각선 없음·전체윈도우 포함)와 달리, 이 모듈은
ESA SNAP S1TBX의 `RefinedLee.java` 알고리즘을 그대로 numpy로 옮긴 것이다.
FILTER_COMPARISON_KR.md 3-B절에서 확인된 "단순화판이 SNAP보다 ~2배 세게
평활화한다"는 차이를 없애고, 다음에 SNAP 없이도 SNAP과 (거의) 같은 Refined Lee
결과를 재현하려는 목적이다.

SNAP RefinedLee 알고리즘 (원본 대조)
------------------------------------
7x7 이웃 `w[7][7]`, 중심 픽셀 w[3][3]에 대해:

1. **서브영역 평균** subMean[3][3]: subMean[j][i] = mean(w[2j:2j+3, 2i:2i+3]).
   (9개의 겹치는 3x3 평균)
2. **4방향 gradient**:
   g0=|subMean[1][0]-subMean[1][2]|  (가로)
   g1=|subMean[0][2]-subMean[2][0]|  (반대각)
   g2=|subMean[0][1]-subMean[2][1]|  (세로)
   g3=|subMean[0][0]-subMean[2][2]|  (주대각)
   direction = argmax(g0..g3).
3. **8방향 d 세분**(경계의 어느 쪽이 더 급한지로 반대편 절반 선택):
   dir0 → |m10-m11|<|m11-m12| ? d=4 : d=0
   dir1 → |m02-m11|<|m11-m20| ? d=1 : d=5
   dir2 → |m01-m11|<|m11-m21| ? d=2 : d=6
   dir3 → |m00-m11|<|m11-m22| ? d=3 : d=7   (mJI = subMean[J][I])
4. **edge-aligned 마스크**(d별 28픽셀; 경계를 가로지르지 않는 절반):
   d0 우측절반, d1 우상삼각, d2 상단절반, d3 좌상삼각,
   d4 좌측절반, d5 좌하삼각, d6 하단절반, d7 우하삼각.
   그 28픽셀로 meanY, varY(표본분산, ddof=1) 계산.
5. **국소 잡음분산 sigmaV**(1/ENL이 아니라 데이터에서 추정): 9개 서브영역의
   정규화분산(var/mean², 모두 유효한 것만) 중 **가장 작은 5개의 평균**.
6. **필터값**: varX=max(0, (varY - meanY²·sigmaV)/(1+sigmaV)), b=varX/varY,
   out = meanY + b·(center - meanY).  (varY==0이면 out=meanY)

원본과 다른(의도적) 점
----------------------
- **nodata 처리**: SNAP은 nodata 픽셀을 평균/분산에서 건너뛴다. 여기서는
  무효 픽셀을 nan으로 두고 nan-aware로 계산한다(내부 유효영역에서는 동일,
  지오코딩 모서리 nodata 근처에서만 미세 차이). subMean은 SNAP이 nodata를
  안 거르고 9픽셀 평균하지만, 여기선 nan-aware라 경계에서만 다르다.
- **표본분산 분모**: SNAP `getLocalVarianceValue`가 (k-1)을 쓰므로 varY·서브
  영역 분산 모두 ddof=1로 맞췄다(1D `getVarianceValue`는 원본에 미표기라 동일
  가정).
- **sigmaV 정렬 off-by-one**: SNAP은 `Arrays.sort(...,0,numSubArea-1)`로 마지막
  원소를 빼고 정렬하는 미세 버그가 있으나, 여기선 전부 정렬 후 최소 5개를
  평균한다(결과 차이는 무시할 수준).
- **varY==0 처리**: SNAP은 0.0을 반환(사실상 픽셀을 0으로)하지만, 여기서는
  meanY를 반환한다(완전 균질 영역 → 지역평균이 옳음; 0 반환은 검은 점을 만듦).

메모리: run_speckle_filter의 스트립(halo) 위에서 열 블록 단위로 7x7 이웃을
sliding_window_view로 잡아 처리한다. ENL 인자는 없다(SNAP RefinedLee 미사용).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .base import run_speckle_filter, validate_window_size

WINDOW_SIZE = 7  # SNAP RefinedLee 고정
MIN_WINDOW_SIZE = 7


def _build_direction_masks() -> np.ndarray:
    """d=0..7 각 방향의 7x7 edge-aligned 마스크(28 True). getNonEdgeAreaPixelValues 대응."""
    masks = np.zeros((8, 7, 7), dtype=bool)
    for y in range(7):
        masks[0, y, 3:7] = True            # d0: 우측 절반 (x 3..6)
        masks[1, y, y:7] = True            # d1: 우상 삼각 (x y..6)
        masks[3, y, 0:7 - y] = True        # d3: 좌상 삼각 (x 0..6-y)
        masks[4, y, 0:4] = True            # d4: 좌측 절반 (x 0..3)
        masks[5, y, 0:y + 1] = True        # d5: 좌하 삼각 (x 0..y)
        masks[7, y, 6 - y:7] = True        # d7: 우하 삼각 (x 6-y..6)
    masks[2, 0:4, :] = True                # d2: 상단 절반 (y 0..3)
    masks[6, 3:7, :] = True                # d6: 하단 절반 (y 3..6)
    assert all(int(masks[d].sum()) == 28 for d in range(8)), "각 방향 마스크는 28픽셀"
    return masks


_MASKS = _build_direction_masks()
_MASKS_FLAT = _MASKS.reshape(8, 49)


def _nan_mean_var(vals: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """마지막 축에 대해 (평균, 표본분산 ddof=1, 유효개수). 전부 nan이면 nan."""
    finite = np.isfinite(vals)
    cnt = finite.sum(axis=-1)
    # 경계(halo) 근처엔 전부 nan인 슬라이스가 생겨 nanmean/nanvar가 RuntimeWarning을
    # 내지만(결과는 nan으로 안전), 유효영역 밖이라 최종적으로 마스킹되므로 무시한다.
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        masked = np.where(finite, vals, np.nan)
        mean = np.nanmean(masked, axis=-1)
        var = np.nanvar(masked, axis=-1, ddof=1)
    return mean, var, cnt


def _snap_refined_lee_fn(col_block: int):
    """run_speckle_filter에 넘길 FilterFn 생성 (열 블록 크기 지정)."""

    def filter_fn(array: np.ndarray, valid_mask: np.ndarray, window_size: int, nodata: float) -> np.ndarray:
        if window_size != WINDOW_SIZE:
            raise ValueError("SNAP Refined Lee는 7x7 고정입니다.")
        pad = WINDOW_SIZE // 2
        rows, cols = array.shape
        af = np.where(valid_mask, array.astype(np.float64), np.nan)
        apad = np.pad(af, pad, mode="constant", constant_values=np.nan)

        out = np.full((rows, cols), nodata, dtype=np.float64)
        for c0 in range(0, cols, col_block):
            c1 = min(c0 + col_block, cols)
            sub_pad = apad[:, c0:c1 + 2 * pad]                     # (rows+2p, cb+2p)
            win = sliding_window_view(sub_pad, (WINDOW_SIZE, WINDOW_SIZE))  # (rows, cb, 7,7)
            cb = win.shape[1]
            center = win[:, :, pad, pad]

            # --- 1) 서브영역 평균 subMean[3][3] + 정규화분산(sigmaV용) ---
            sub_mean = np.empty((rows, cb, 3, 3), dtype=np.float64)
            norm_var = np.full((rows, cb, 9), np.nan, dtype=np.float64)
            s = 0
            for j in range(3):
                for i in range(3):
                    block = win[:, :, 2 * j:2 * j + 3, 2 * i:2 * i + 3].reshape(rows, cb, 9)
                    m, v, cnt = _nan_mean_var(block)
                    sub_mean[:, :, j, i] = m
                    with np.errstate(invalid="ignore", divide="ignore"):
                        nv = np.where((cnt == 9) & (m > 0), v / (m * m), np.nan)
                    norm_var[:, :, s] = nv
                    s += 1

            def sm(j, i):
                return sub_mean[:, :, j, i]

            # --- 2) 4방향 gradient, direction=argmax ---
            g = np.stack([
                np.abs(sm(1, 0) - sm(1, 2)),
                np.abs(sm(0, 2) - sm(2, 0)),
                np.abs(sm(0, 1) - sm(2, 1)),
                np.abs(sm(0, 0) - sm(2, 2)),
            ], axis=-1)
            direction = np.argmax(np.nan_to_num(g, nan=-1.0), axis=-1)

            # --- 3) 8방향 d 세분 ---
            m11 = sm(1, 1)
            d = np.zeros((rows, cb), dtype=np.intp)
            c0m = np.abs(sm(1, 0) - m11) < np.abs(m11 - sm(1, 2))
            d = np.where(direction == 0, np.where(c0m, 4, 0), d)
            c1m = np.abs(sm(0, 2) - m11) < np.abs(m11 - sm(2, 0))
            d = np.where(direction == 1, np.where(c1m, 1, 5), d)
            c2m = np.abs(sm(0, 1) - m11) < np.abs(m11 - sm(2, 1))
            d = np.where(direction == 2, np.where(c2m, 2, 6), d)
            c3m = np.abs(sm(0, 0) - m11) < np.abs(m11 - sm(2, 2))
            d = np.where(direction == 3, np.where(c3m, 3, 7), d)

            # --- 4) 방향별 meanY/varY 계산 후 d로 선택 ---
            win_flat = win.reshape(rows, cb, 49)
            mean_y = np.empty((rows, cb), dtype=np.float64)
            var_y = np.empty((rows, cb), dtype=np.float64)
            for dd in range(8):
                vals = win_flat[:, :, _MASKS_FLAT[dd]]         # (rows, cb, 28)
                m, v, _ = _nan_mean_var(vals)
                sel = d == dd
                mean_y = np.where(sel, m, mean_y)
                var_y = np.where(sel, v, var_y)

            # --- 5) sigmaV = 최소 5개 정규화분산의 평균 ---
            nv_sorted = np.sort(norm_var, axis=-1)             # nan은 뒤로
            valid_cnt = np.isfinite(norm_var).sum(axis=-1)
            take = np.minimum(5, valid_cnt)
            first5 = nv_sorted[:, :, :5]
            use = np.arange(5)[None, None, :] < take[:, :, None]
            summed = np.where(use, np.nan_to_num(first5, nan=0.0), 0.0).sum(axis=-1)
            with np.errstate(invalid="ignore", divide="ignore"):
                sigma_v = np.where(take > 0, summed / np.maximum(take, 1), 0.0)

            # --- 6) 필터값 ---
            with np.errstate(invalid="ignore", divide="ignore"):
                var_x = np.maximum((var_y - mean_y * mean_y * sigma_v) / (1.0 + sigma_v), 0.0)
                b = np.where(var_y > 0, var_x / var_y, 0.0)
                filt = mean_y + b * (center - mean_y)
            filt = np.where(var_y > 0, filt, mean_y)           # varY==0 → 지역평균
            out[:, c0:c1] = filt

        return out

    return filter_fn


def refined_lee_snap_filter(
    input_tif: str | Path,
    output_tif: str | Path,
    window_size: int = WINDOW_SIZE,
    nodata: float | None = None,
    col_block: int = 256,
) -> Path:
    """
    SNAP 충실 재현 Refined Lee를 linear power GeoTIFF에 적용한다.

    Parameters
    ----------
    window_size:
        SNAP RefinedLee는 7x7 고정. 7 이외 값은 거부한다.
    nodata:
        미지정 시 입력 GeoTIFF의 nodata 태그를 사용.
    col_block:
        열 블록 크기(메모리 조절). 작을수록 메모리 사용이 준다.

    주의: 이 필터는 ENL을 쓰지 않는다(sigmaV를 데이터에서 국소 추정). 입력은
    반드시 **linear power**여야 한다(dB 아님 — speckle 통계 모델 전제).
    """
    validate_window_size(window_size, MIN_WINDOW_SIZE)
    if window_size != WINDOW_SIZE:
        raise ValueError("SNAP Refined Lee는 7x7 고정입니다 (window_size=7).")
    return run_speckle_filter(input_tif, output_tif, WINDOW_SIZE, nodata,
                              _snap_refined_lee_fn(col_block))
