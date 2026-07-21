# -*- coding: utf-8 -*-
"""
단일 GRD RTC 씬(dB GeoTIFF) 하나만의 수체 지도 — baseline·날짜 모자이크와
무관하게, 그 씬 하나의 관측만으로 고정 dB 임계값(기본 -16, 오츠 아님)을
적용한다.

여러 프레임을 날짜 단위로 합치는 build_water_per_date.py와 달리, 아직 같은
날짜의 다른 프레임이 RTC 진행 중이거나, 특정 씬 하나만 먼저 확인하고 싶을
때 쓴다.

실행:
    conda run -n s1_snappy python build_water_single_scene.py \
        --scene downloads/rtc_grd/S1C_..._392D_COG_rtc_db.tif
    conda run -n s1_snappy python build_water_single_scene.py \
        --scene downloads/rtc_grd/S1C_..._392D_COG_rtc_db.tif --db -18
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "downloads" / "water" / "scene_water"

DB_THRESHOLD_DEFAULT = -16.0
NODATA_U8 = 255
CHUNK_ROWS = 512


def scene_output_name(scene_path: Path) -> str:
    # "..._<4자리ID>_COG_rtc_db.tif" -> "<4자리ID>.tif". 매칭 안 되면 stem 그대로.
    m = re.search(r"_([0-9A-Fa-f]{4})_COG_rtc_db$", scene_path.stem)
    tag = m.group(1) if m else scene_path.stem
    return f"{tag}.tif"


def build_single_scene_water(scene_path: Path, db_threshold: float) -> Path:
    # 확장자(.tif) 없이 넣는 흔한 실수를 자동 보완한다.
    if not scene_path.exists() and scene_path.suffix.lower() != ".tif":
        cand = scene_path.with_suffix(".tif")
        if cand.exists():
            scene_path = cand
    if not scene_path.exists():
        raise FileNotFoundError(
            f"씬을 찾을 수 없습니다: {scene_path}\n"
            f"  (확장자 .tif 를 붙였는지 확인하세요. 예: ..._rtc_db.tif)"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / scene_output_name(scene_path)

    with rasterio.open(scene_path) as src:
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width,
            "count": 1, "dtype": "uint8", "crs": src.crs, "transform": src.transform,
            "nodata": NODATA_U8, "compress": "DEFLATE", "tiled": True,
            "bigtiff": "IF_SAFER",
        }
        res_deg = abs(src.transform.a)
        center_lat = (src.bounds.bottom + src.bounds.top) / 2
        px_area_km2 = (res_deg * 111_320.0) * (res_deg * 111_320.0 * np.cos(np.radians(center_lat))) / 1e6

        n_water = n_valid = 0
        with rasterio.open(out_path, "w", **profile) as dst:
            for row0 in range(0, src.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, src.height - row0)
                win = Window(0, row0, src.width, nrows)
                db = src.read(1, window=win).astype("float32")
                valid = np.isfinite(db) & (db != 0)
                water = valid & (db < db_threshold)
                dst.write(np.where(valid, water.astype("uint8"), NODATA_U8), 1, window=win)
                n_water += int(water.sum())
                n_valid += int(valid.sum())

    total_px = profile["height"] * profile["width"]
    print(f"{scene_path.name}: 격자 {profile['width']}x{profile['height']}px, "
          f"커버리지 {100 * n_valid / total_px:.1f}%, "
          f"수체(고정 {db_threshold}dB) {n_water * px_area_km2:,.2f} km^2 -> {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="단일 씬 수체 지도 (고정 dB 임계값, baseline 무관)")
    parser.add_argument("--scene", required=True, help="RTC dB GeoTIFF 경로 (*_rtc_db.tif)")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT, help="수체 판정 dB 임계값")
    args = parser.parse_args()

    build_single_scene_water(Path(args.scene), args.db)


if __name__ == "__main__":
    main()
