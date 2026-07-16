# -*- coding: utf-8 -*-
"""
신규침수 마스크(detect_flood_grd_v2.py 산출물)에서 위치(경위도) 핫스팟을
청크 단위로 안전하게 추출한다. 파일이 커도(예: 86395x72001, 전체범위 실행)
전체를 한번에 메모리에 올리지 않고, 행 블록 단위로 읽어 2km 격자에 픽셀수를
누적한다.

산출물:
  - 터미널에 상위 핫스팟 표 (면적 큰 순)
  - downloads/water/flood_hotspots_<strict|relaxed>.geojson (유의미한 모든
    셀을 점으로, QGIS에서 바로 열어볼 수 있음)

실행:
    conda run -n s1_snappy python flood_hotspots.py
    conda run -n s1_snappy python flood_hotspots.py --files flood_water_strict_20260714.tif
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
WATER_DIR = PROJECT_DIR / "downloads" / "water"

CELL_DEG_DEFAULT = 0.02  # 약 2km 격자
CHUNK_ROWS = 1024  # 다른 프로세스와 메모리 경쟁 대비 작게
MIN_PIXELS_FOR_GEOJSON = 3  # 노이즈성 단일픽셀 셀은 GeoJSON에서 제외
TOP_N_PRINT = 40

M_PER_DEG = 111_320.0

DEFAULT_FILES = (
    "flood_water_strict_20260713_14.tif",
    "flood_water_relaxed_20260713_14.tif",
)


def process(name: str, cell_deg: float, top_n: int) -> None:
    path = WATER_DIR / name
    if not path.exists():
        print(f"(없음, 건너뜀: {name})")
        return

    cell_counts: dict[tuple[int, int], int] = defaultdict(int)
    total_water_px = 0

    with rasterio.open(path) as src:
        transform = src.transform
        res_deg = abs(transform.a)
        height, width = src.height, src.width

        for row0 in range(0, height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, height - row0)
            arr = src.read(1, window=Window(0, row0, width, nrows))
            water = arr == 1
            n = int(water.sum())
            if n == 0:
                continue
            total_water_px += n

            rows, cols = np.where(water)
            lons = transform.c + (cols + 0.5) * transform.a
            lats = transform.f + (row0 + rows + 0.5) * transform.e

            cell_lon = np.floor(lons / cell_deg).astype(np.int64)
            cell_lat = np.floor(lats / cell_deg).astype(np.int64)
            keys, counts = np.unique(
                np.stack([cell_lon, cell_lat], axis=1), axis=0, return_counts=True
            )
            for (cx, cy), c in zip(keys.tolist(), counts.tolist()):
                cell_counts[(cx, cy)] += c

    if total_water_px == 0:
        print(f"\n=== {name} ===\n침수 픽셀 없음")
        return

    def px_area_km2(lat: float) -> float:
        return (res_deg * M_PER_DEG) * (res_deg * M_PER_DEG * np.cos(np.radians(lat))) / 1e6

    print(f"\n=== {name} ===")
    print(f"전체 침수 픽셀: {total_water_px:,}  |  뚜렷한 {cell_deg}도 셀 개수: {len(cell_counts)}")

    ranked = sorted(cell_counts.items(), key=lambda kv: -kv[1])
    print(f"\n상위 {min(top_n, len(ranked))}개 핫스팟 (침수 픽셀 많은 순):")
    for (cx, cy), count in ranked[:top_n]:
        center_lat = (cy + 0.5) * cell_deg
        center_lon = (cx + 0.5) * cell_deg
        area = count * px_area_km2(center_lat)
        print(f"  ({center_lat:.3f}N, {center_lon:.3f}E) - {count:>7,}px, {area:6.2f} km^2")

    features = []
    for (cx, cy), count in ranked:
        if count < MIN_PIXELS_FOR_GEOJSON:
            continue
        center_lat = (cy + 0.5) * cell_deg
        center_lon = (cx + 0.5) * cell_deg
        area = count * px_area_km2(center_lat)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [center_lon, center_lat]},
            "properties": {"pixel_count": count, "area_km2": round(area, 4)},
        })

    tag = "strict" if "strict" in name else "relaxed" if "relaxed" in name else Path(name).stem
    out_geojson = WATER_DIR / f"flood_hotspots_{tag}.geojson"
    with open(out_geojson, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"GeoJSON 저장 ({len(features)}개 셀, >={MIN_PIXELS_FOR_GEOJSON}px): {out_geojson}")


def main() -> None:
    parser = argparse.ArgumentParser(description="신규침수 마스크에서 위치 핫스팟 추출")
    parser.add_argument("--files", nargs="+", default=list(DEFAULT_FILES),
                        help="downloads/water/ 기준 파일명 목록")
    parser.add_argument("--cell-deg", type=float, default=CELL_DEG_DEFAULT, help="집계 격자 크기(도)")
    parser.add_argument("--top", type=int, default=TOP_N_PRINT, help="출력할 상위 핫스팟 개수")
    args = parser.parse_args()

    for name in args.files:
        process(name, args.cell_deg, args.top)


if __name__ == "__main__":
    main()
