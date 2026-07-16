# -*- coding: utf-8 -*-
"""
detect_flood_grd_v2.py의 신규침수 마스크를 위도 기준으로 남/북한 나눠
면적을 재집계한다 (청크 처리, 대형 래스터 안전).

배경: 분석 범위를 baseline 전체(남한+서해+북한 일부)로 넓히면서, 상위
핫스팟 상당수가 휴전선 이북(북한)으로 나타났다. 북한 지역은 pre-event
baseline 반복관측이 부족하고 산악지형 레이더 그림자 위험이 커서(자세한
근거는 FLOOD_DETECTION_KR.md 5절 참고) 신뢰도가 남한보다 낮다. 이 스크립트로
"남한만" 수치를 별도로 확인할 수 있다.

실행:
    conda run -n s1_snappy python split_flood_area_nk_sk.py
    conda run -n s1_snappy python split_flood_area_nk_sk.py --lat-split 38.3 \\
        --files flood_water_strict_20260713_14.tif
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
WATER_DIR = PROJECT_DIR / "downloads" / "water"

LAT_SPLIT_DEFAULT = 38.3  # 대략적 남/북한 경계(휴전선 부근)
CHUNK_ROWS = 1024
M_PER_DEG = 111_320.0

DEFAULT_FILES = (
    "flood_water_strict_20260713_14.tif",
    "flood_water_relaxed_20260713_14.tif",
)


def split_one(name: str, lat_split: float) -> None:
    path = WATER_DIR / name
    if not path.exists():
        print(f"(없음, 건너뜀: {name})")
        return

    with rasterio.open(path) as src:
        transform = src.transform
        res_deg = abs(transform.a)
        height, width = src.height, src.width

        area_south = area_north = 0.0
        px_south = px_north = 0

        for row0 in range(0, height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, height - row0)
            arr = src.read(1, window=Window(0, row0, width, nrows))
            water = arr == 1
            if not water.any():
                continue

            row_lats = transform.f + (row0 + np.arange(nrows) + 0.5) * transform.e
            is_south = row_lats < lat_split

            row_water_counts = water.sum(axis=1)
            row_px_areas = (res_deg * M_PER_DEG) * (res_deg * M_PER_DEG * np.cos(np.radians(row_lats))) / 1e6
            row_areas = row_water_counts * row_px_areas

            area_south += float(row_areas[is_south].sum())
            area_north += float(row_areas[~is_south].sum())
            px_south += int(row_water_counts[is_south].sum())
            px_north += int(row_water_counts[~is_south].sum())

    total = area_south + area_north
    print(f"\n=== {name} (남/북 경계 위도 {lat_split}) ===")
    if total == 0:
        print("침수 픽셀 없음")
        return
    print(f"남한(위도<{lat_split}): {area_south:,.2f} km^2 ({px_south:,}px) - {100*area_south/total:.1f}%")
    print(f"북한(위도>={lat_split}): {area_north:,.2f} km^2 ({px_north:,}px) - {100*area_north/total:.1f}%")
    print(f"합계: {total:,.2f} km^2")


def main() -> None:
    parser = argparse.ArgumentParser(description="신규침수 면적을 위도 기준 남/북한으로 분리 집계")
    parser.add_argument("--files", nargs="+", default=list(DEFAULT_FILES))
    parser.add_argument("--lat-split", type=float, default=LAT_SPLIT_DEFAULT)
    args = parser.parse_args()

    for name in args.files:
        split_one(name, args.lat_split)


if __name__ == "__main__":
    main()
