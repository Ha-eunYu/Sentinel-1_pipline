# -*- coding: utf-8 -*-
"""
두 RTC/GTC dB GeoTIFF를 공통 격자에서 비교한다.

용도:
  (1) 교차검증 — sarsen RTC vs SNAP RTC(같은 DEM). dB 수준·지오코딩 정합이
      맞는지(같은 지형보정 결과인지) 확인.
  (2) DEM 소스 비교 — SNAP RTC(자동 Copernicus, C:) vs SNAP RTC(외부 COP30, D:).
      DEM 출처만 바뀌었을 때 dB/위치가 얼마나 달라지는지.

방법: B를 A 격자에 bilinear 리샘플(reproject) → 두 영상 모두 유효한 화소에서
  A−B 통계(mean/median/std/RMSE/MAE), Pearson 상관, ±1·±2 dB 이내 비율,
  그리고 정수 픽셀 시프트 탐색(±SHIFT)으로 지오코딩 어긋남(정합) 추정.

실행:
    conda run -n sarsen_clean python compare_rtc.py A.tif B.tif [--shift 3] [--label-a .. --label-b ..]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _read_db(path: str) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as ds:
        arr = ds.read(1, masked=True).filled(np.nan).astype("float32")
        prof = ds.profile
    # nodata 태그가 NaN이 아니면 NaN으로 통일
    return arr, prof


def _resample_b_to_a(b_path: str, a_prof: dict) -> np.ndarray:
    """B를 A 격자(transform/crs/shape)로 bilinear 리샘플."""
    dst = np.full((a_prof["height"], a_prof["width"]), np.nan, dtype="float32")
    with rasterio.open(b_path) as bds:
        src = bds.read(1, masked=True).filled(np.nan).astype("float32")
        reproject(
            source=src,
            destination=dst,
            src_transform=bds.transform,
            src_crs=bds.crs,
            dst_transform=a_prof["transform"],
            dst_crs=a_prof["crs"],
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    return dst


def _best_shift(a: np.ndarray, b: np.ndarray, max_shift: int) -> tuple[int, int, float]:
    """정수 픽셀 시프트(dy,dx)∈[-max,max]로 상관 최대인 지점을 찾아
    (dy, dx, best_r) 반환. 계산량 위해 4배 데시메이션 후 탐색."""
    a_d = a[::4, ::4]
    b_d = b[::4, ::4]
    best = (0, 0, -2.0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            bs = np.roll(np.roll(b_d, dy, axis=0), dx, axis=1)
            m = np.isfinite(a_d) & np.isfinite(bs)
            if m.sum() < 1000:
                continue
            av, bv = a_d[m], bs[m]
            if av.std() < 1e-6 or bv.std() < 1e-6:
                continue
            r = float(np.corrcoef(av, bv)[0, 1])
            if r > best[2]:
                best = (dy, dx, r)
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description="두 dB GeoTIFF 비교(교차검증/ DEM 비교)")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--shift", type=int, default=3, help="정합용 최대 정수 픽셀 시프트 탐색폭")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()

    a, a_prof = _read_db(args.a)
    print(f"[{args.label_a}] {Path(args.a).name}")
    print(f"    {a_prof['width']}x{a_prof['height']}  {a_prof['crs']}  "
          f"px≈{abs(a_prof['transform'].a)*111320:.1f}m")
    with rasterio.open(args.b) as bds:
        print(f"[{args.label_b}] {Path(args.b).name}")
        print(f"    {bds.width}x{bds.height}  {bds.crs}  "
              f"px≈{abs(bds.transform.a)*111320:.1f}m")

    b = _resample_b_to_a(args.b, a_prof)

    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    print(f"\n공통 유효 화소: {n:,} ({100*n/a.size:.1f}% of {args.label_a} 격자)")
    if n < 1000:
        print("겹치는 유효 화소가 너무 적어 비교 불가(격자/범위 확인).")
        return

    av, bv = a[m], b[m]
    diff = av - bv  # A - B
    rmse = float(np.sqrt(np.mean(diff**2)))
    r = float(np.corrcoef(av, bv)[0, 1])
    print(f"  {args.label_a} dB : mean {av.mean():.2f}  median {np.median(av):.2f}")
    print(f"  {args.label_b} dB : mean {bv.mean():.2f}  median {np.median(bv):.2f}")
    print(f"  A−B      : mean {diff.mean():+.3f}  median {np.median(diff):+.3f}  "
          f"std {diff.std():.3f}")
    print(f"  |A−B|    : MAE {np.abs(diff).mean():.3f}  RMSE {rmse:.3f} dB")
    print(f"  Pearson r: {r:.4f}")
    print(f"  |A−B|≤1dB: {100*np.mean(np.abs(diff)<=1):.1f}%   "
          f"≤2dB: {100*np.mean(np.abs(diff)<=2):.1f}%")

    dy, dx, best_r = _best_shift(a, b, args.shift)
    px_m = abs(a_prof["transform"].a) * 111320
    print(f"\n정합(정수 픽셀 시프트 탐색 ±{args.shift}, 4x 데시메이션):")
    print(f"  최적 시프트 dy={dy} dx={dx} (≈{dy*4*px_m:.0f}m, {dx*4*px_m:.0f}m)  r={best_r:.4f}")
    if dy == 0 and dx == 0:
        print("  → 시프트 0에서 상관 최대 = 지오코딩 정합 양호.")
    else:
        print("  → 0이 아닌 시프트에서 상관이 더 큼 = 계통적 위치 어긋남 가능(해상도차/보간 영향일 수도).")


if __name__ == "__main__":
    main()
