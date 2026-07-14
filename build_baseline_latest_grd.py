# -*- coding: utf-8 -*-
"""
남한 AOI 전체에 대한 GRD 기반 "최신 관측 우선" baseline 수체 지도.

기존 build_baseline_water*.py와의 차이:
  - 대상: Korea_flood_AOI가 아니라 South_Korea.geojson bbox(+0.1도) 전역.
  - 판정: dB 임계값만 사용. **HAND 미사용** (동해안 쪽 HAND 타일 미보유 +
    사용자 요청). 따라서 레이더 그림자·활주로 등 오탐이 포함될 수 있고,
    바다도 수체(1)로 판정된다.
  - 중첩 처리: 여러 날짜 합집합(OR)이 아니라 **픽셀별 가장 최근 촬영이 우선**.
    입력 합성 VRT(s1_rtc_db_composite_latest_pre.vrt)가 날짜 오름차순으로
    쌓여 있어(gdalbuildvrt는 나중 파일이 이김) 최근 유효 관측이 남는다.
    최근 날짜가 NoData(0)인 픽셀은 자동으로 그 이전 날짜 값이 사용된다.
  - 사용 날짜: pre-event 5개 (6/25, 6/26, 7/1, 7/2, 7/3 — 홍수일 7/8 이전).

출력 (downloads/water/):
  baseline_water_latest_grd.tif : 0=비수체, 1=수체(dB<임계값), 255=미관측

실행:
    conda run -n s1_snappy python build_baseline_latest_grd.py
    conda run -n s1_snappy python build_baseline_latest_grd.py --db -18
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
COMPOSITE_VRT = PROJECT_DIR / "downloads" / "rtc_grd" / "s1_rtc_db_composite_latest_pre.vrt"
OUT_PATH = PROJECT_DIR / "downloads" / "water" / "baseline_water_latest_grd.tif"

DB_THRESHOLD_DEFAULT = -16.0
NODATA_U8 = 255
CHUNK_ROWS = 2048  # 블록당 행 수 (약 35,900폭 기준 float32 ~280MB)


def main() -> None:
    parser = argparse.ArgumentParser(description="남한 전역 GRD 최신관측 baseline (dB만, HAND 미사용)")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT,
                        help=f"수체 판정 dB 임계값 (기본 {DB_THRESHOLD_DEFAULT})")
    args = parser.parse_args()

    if not COMPOSITE_VRT.exists():
        raise FileNotFoundError(
            f"{COMPOSITE_VRT} 없음 — gdalbuildvrt로 날짜 오름차순 합성 VRT를 먼저 생성"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(COMPOSITE_VRT) as src:
        profile = {
            "driver": "GTiff",
            "height": src.height,
            "width": src.width,
            "count": 1,
            "dtype": "uint8",
            "crs": src.crs,
            "transform": src.transform,
            "nodata": NODATA_U8,
            "compress": "DEFLATE",
            "tiled": True,
            "bigtiff": "IF_SAFER",
        }

        res_deg = abs(src.transform.a)
        center_lat = (src.bounds.bottom + src.bounds.top) / 2
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * np.cos(np.radians(center_lat))
        px_area_km2 = (res_deg * m_per_deg_lat) * (res_deg * m_per_deg_lon) / 1e6

        n_water = 0
        n_valid = 0

        print(f"격자: {src.width} x {src.height} px (~10m), 임계값 dB < {args.db}, HAND 미사용")

        with rasterio.open(OUT_PATH, "w", **profile) as dst:
            for row0 in range(0, src.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, src.height - row0)
                win = Window(0, row0, src.width, nrows)

                db = src.read(1, window=win).astype("float32")
                valid = np.isfinite(db) & (db != 0)
                water = valid & (db < args.db)

                out = np.where(valid, water.astype("uint8"), NODATA_U8).astype("uint8")
                dst.write(out, 1, window=win)

                n_water += int(water.sum())
                n_valid += int(valid.sum())
                print(f"  행 {row0:>6}~{row0 + nrows:>6} / {src.height} 처리")

    total_px = profile["height"] * profile["width"]
    print(f"\n커버리지: {100 * n_valid / total_px:.1f}% (남한 bbox 기준, 바다 포함)")
    print(f"수체 판정 면적: {n_water * px_area_km2:,.2f} km^2 (바다·오탐 포함 주의)")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
