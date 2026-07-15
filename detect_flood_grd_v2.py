# -*- coding: utf-8 -*-
"""
7/13+7/14 post-event GRD 전체(93FC/3C22/1A5A/FE43/8EF1/B126, 6프레임, 서로 다른
3개 패스)를 모두 합쳐 baseline과 비교하는 "최대한 많이 잡기" 버전.

detect_flood_grd.py(3프레임, 보수적 3중조건)와의 차이:
  - post 쪽 관측을 latest-wins가 아니라 **여러 관측 중 가장 어두운(dB가 가장
    낮은) 값을 픽셀별로 채택**한다. 관측마다 촬영 기하(승/하강)가 달라 같은
    수체도 각도에 따라 다르게 보일 수 있는데, 최솟값을 쓰면 "어느 한 패스
    에서라도 물처럼 보이면 물"로 간주해 탐지를 극대화한다.
  - 관측 패스가 3개(7/13 하강, 7/14 09:31 상승, 7/14 21:31 하강)로 늘어
    커버리지 자체도 detect_flood_grd.py의 35.1%보다 훨씬 넓어질 것으로 기대.
  - 판정 단계를 3단계로 나눠 함께 출력한다 (느슨한 것부터):
      1) total_post_water   : post_db_min < DB_THRESHOLD (baseline 무관, 그냥
                               post 관측 중 하나라도 물로 보이는 모든 곳)
      2) new_flood_relaxed  : total_post_water AND NOT baseline_water
                               (하락폭 조건 없음 - "최대한 많이")
      3) new_flood_strict   : new_flood_relaxed AND diff <= DROP_THRESHOLD
                               (detect_flood_grd.py와 동일한 보수적 조건,
                               비교용으로 함께 계산)

baseline은 build_baseline_composite_grd.py가 만든 pre-event(~7/3) 최신관측
합성(s1_rtc_db_composite_latest_pre.vrt)을 그대로 쓴다.

산출물 (downloads/water/):
  diff_min_20260713_14_vs_baseline.tif   post_db_min - baseline_db (dB)
  flood_water_total_20260713_14.tif      1) 전체 post 수체 (baseline 무관)
  flood_water_relaxed_20260713_14.tif    2) 신규침수, 느슨(하락폭 조건 없음)
  flood_water_strict_20260713_14.tif     3) 신규침수, 보수적(하락폭 조건 포함)

실행:
    conda run -n s1_snappy python detect_flood_grd_v2.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

PROJECT_DIR = Path(__file__).resolve().parent
RTC_GRD_DIR = PROJECT_DIR / "downloads" / "rtc_grd"
OUT_DIR = PROJECT_DIR / "downloads" / "water"
AOI_GEOJSON = PROJECT_DIR / "Korea_flood_AOI.geojson"

BASELINE_VRT = RTC_GRD_DIR / "s1_rtc_db_composite_latest_pre.vrt"

DIFF_OUT = OUT_DIR / "diff_min_20260713_14_vs_baseline.tif"
TOTAL_OUT = OUT_DIR / "flood_water_total_20260713_14.tif"
RELAXED_OUT = OUT_DIR / "flood_water_relaxed_20260713_14.tif"
STRICT_OUT = OUT_DIR / "flood_water_strict_20260713_14.tif"

POST_DATES = ("20260713", "20260714")
SCENE_DATE_RE = re.compile(r"_(\d{8})T\d{6}_")

DB_THRESHOLD_DEFAULT = -16.0
DROP_THRESHOLD_DEFAULT = -3.0
AOI_MARGIN_DEG_DEFAULT = 0.1
NODATA_U8 = 255
CHUNK_ROWS = 256  # 다른 프로세스와 메모리 경쟁 대비 작게 유지


def post_scenes() -> list[Path]:
    tifs = sorted(RTC_GRD_DIR.glob("*_rtc_db.tif"))
    out = [t for t in tifs if (m := SCENE_DATE_RE.search(t.name)) and m.group(1) in POST_DATES]
    if not out:
        raise FileNotFoundError(f"{POST_DATES} 날짜의 _rtc_db.tif가 없습니다.")
    return out


def aoi_bbox(margin_deg: float) -> tuple[float, float, float, float]:
    with open(AOI_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    geom = gj["features"][0]["geometry"] if "features" in gj else gj.get("geometry", gj)
    coords = geom["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (
        min(lons) - margin_deg, min(lats) - margin_deg,
        max(lons) + margin_deg, max(lats) + margin_deg,
    )


def build_target_grid(res_deg: float, margin_deg: float):
    min_lon, min_lat, max_lon, max_lat = aoi_bbox(margin_deg)
    width = int(round((max_lon - min_lon) / res_deg))
    height = int(round((max_lat - min_lat) / res_deg))
    transform = from_origin(min_lon, max_lat, res_deg, res_deg)
    return transform, width, height


def reproject_chunk(src_path: Path, window_transform, win_width: int, win_height: int, dst_crs) -> np.ndarray:
    with rasterio.open(src_path) as src:
        dst = np.full((win_height, win_width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=window_transform, dst_crs=dst_crs,
            resampling=Resampling.bilinear, src_nodata=0.0, dst_nodata=np.nan,
        )
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="7/13+7/14 전체 프레임 vs baseline, 최대 탐지 버전")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    parser.add_argument("--drop", type=float, default=DROP_THRESHOLD_DEFAULT)
    parser.add_argument("--margin", type=float, default=AOI_MARGIN_DEG_DEFAULT)
    args = parser.parse_args()

    if not BASELINE_VRT.exists():
        raise FileNotFoundError(f"{BASELINE_VRT} 없음 - build_baseline_composite_grd.py 먼저 실행")

    scenes = post_scenes()
    print(f"post-event 프레임 {len(scenes)}개: {[s.name[:35] for s in scenes]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(scenes[0]) as ref:
        res_deg = abs(ref.transform.a)
        crs = ref.crs
    transform, width, height = build_target_grid(res_deg, args.margin)
    print(f"공통 격자: {width} x {height} px, 해상도 {res_deg:.7f}도 (~10m)")
    print(f"임계값: post_min dB < {args.db} | 하락폭(strict) <= {args.drop}")

    min_lon, min_lat, max_lon, max_lat = aoi_bbox(args.margin)
    center_lat = (min_lat + max_lat) / 2
    px_area_km2 = (res_deg * 111_320.0) * (res_deg * 111_320.0 * np.cos(np.radians(center_lat))) / 1e6

    f32_profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": crs, "transform": transform, "nodata": np.nan,
        "compress": "DEFLATE", "tiled": True,
    }
    u8_profile = {**f32_profile, "dtype": "uint8", "nodata": NODATA_U8}

    n_valid = n_total_water = n_relaxed = n_strict = 0

    with rasterio.open(DIFF_OUT, "w", **f32_profile) as diff_dst, \
         rasterio.open(TOTAL_OUT, "w", **u8_profile) as total_dst, \
         rasterio.open(RELAXED_OUT, "w", **u8_profile) as relaxed_dst, \
         rasterio.open(STRICT_OUT, "w", **u8_profile) as strict_dst:

        for row0 in range(0, height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, height - row0)
            win = rasterio.windows.Window(0, row0, width, nrows)
            win_transform = rasterio.windows.transform(win, transform)

            post_min = np.full((nrows, width), np.nan, dtype="float32")
            for scene in scenes:
                chunk = reproject_chunk(scene, win_transform, width, nrows, crs)
                valid = np.isfinite(chunk)
                post_min = np.where(
                    valid & (np.isnan(post_min) | (chunk < post_min)), chunk, post_min
                )

            base_db = reproject_chunk(BASELINE_VRT, win_transform, width, nrows, crs)

            valid = np.isfinite(post_min) & np.isfinite(base_db)
            diff = np.where(valid, post_min - base_db, np.nan).astype("float32")

            baseline_water = valid & (base_db < args.db)
            total_water = valid & (post_min < args.db)
            relaxed = valid & total_water & (~baseline_water)
            strict = relaxed & (diff <= args.drop)

            diff_dst.write(diff, 1, window=win)
            total_dst.write(np.where(valid, total_water.astype("uint8"), NODATA_U8), 1, window=win)
            relaxed_dst.write(np.where(valid, relaxed.astype("uint8"), NODATA_U8), 1, window=win)
            strict_dst.write(np.where(valid, strict.astype("uint8"), NODATA_U8), 1, window=win)

            n_valid += int(valid.sum())
            n_total_water += int(total_water.sum())
            n_relaxed += int(relaxed.sum())
            n_strict += int(strict.sum())

    total_px = width * height
    print(f"\n두 시점 모두 유효(교차 커버리지): {100 * n_valid / total_px:.1f}%")
    print(f"1) 전체 post 수체(baseline 무관): {n_total_water * px_area_km2:,.2f} km^2")
    print(f"2) 신규침수(느슨, 하락폭 조건 없음): {n_relaxed * px_area_km2:,.2f} km^2")
    print(f"3) 신규침수(보수적, 하락폭 조건 포함): {n_strict * px_area_km2:,.2f} km^2")
    print(f"\n저장: {DIFF_OUT.name}, {TOTAL_OUT.name}, {RELAXED_OUT.name}, {STRICT_OUT.name}")


if __name__ == "__main__":
    main()
