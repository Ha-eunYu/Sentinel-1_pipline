# -*- coding: utf-8 -*-
"""
7/13 post-event GRD 영상과 pre-event baseline(최신관측 우선 합성)을 비교해
(1) dB 차분과 (2) 보수적(conservative) 신규 침수 수체를 산출한다.

baseline: build_baseline_composite_grd.py 가 만든
          downloads/rtc_grd/s1_rtc_db_composite_latest_pre.vrt (pre-event, ~7/3까지)
post    : downloads/rtc_grd/s1_rtc_db_mosaic_20260713.vrt (93FC/3C22/1A5A 3프레임)

두 VRT는 프레임 구성이 달라 커버 범위가 서로 다르므로, 홍수 AOI(+여백) 기준의
공통 격자로 각각 리프로젝션한 뒤 비교한다 (build_baseline_water_grd.py와 동일한
grid 구성 방식 재사용).

"보수적" 수체 탐지 = 아래 3개 조건을 모두 만족해야 신규 침수로 판정:
  1) post dB < DB_THRESHOLD      (절대적으로 수체처럼 어두움)
  2) diff  <= DROP_THRESHOLD     (baseline 대비 뚜렷한 하락 - speckle/일시적
                                   변동이 아니라 실제 산란 변화임을 요구)
  3) baseline dB >= DB_THRESHOLD (baseline에서는 수체가 아니었던 곳만 - 상시
                                   수체/바다/레이더 그림자를 신규 침수로 오판하지 않음)
세 조건 모두를 요구하므로 단일 임계값 방식보다 훨씬 보수적(false positive가
적은 대신 일부 실제 침수를 놓칠 수 있음 - false negative 방향으로 치우침).

산출물 (downloads/water/):
  diff_20260713_vs_baseline.tif        post_db - baseline_db (float32, dB)
  flood_water_conservative_20260713.tif 0=비침수, 1=신규침수(보수적), 255=미관측

실행:
    conda run -n s1_snappy python detect_flood_grd.py
    conda run -n s1_snappy python detect_flood_grd.py --db -16 --drop -3 --margin 0.1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

PROJECT_DIR = Path(__file__).resolve().parent
RTC_GRD_DIR = PROJECT_DIR / "downloads" / "rtc_grd"
OUT_DIR = PROJECT_DIR / "downloads" / "water"
AOI_GEOJSON = PROJECT_DIR / "geojson" / "Korea_flood_AOI.geojson"

BASELINE_VRT = RTC_GRD_DIR / "s1_rtc_db_composite_latest_pre.vrt"
POST_VRT = RTC_GRD_DIR / "s1_rtc_db_mosaic_20260713.vrt"

DIFF_OUT = OUT_DIR / "diff_20260713_vs_baseline.tif"
FLOOD_OUT = OUT_DIR / "flood_water_conservative_20260713.tif"

DB_THRESHOLD_DEFAULT = -16.0
DROP_THRESHOLD_DEFAULT = -3.0  # dB (하락폭. 예: -3이면 baseline보다 3dB 이상 어두워져야 함)
AOI_MARGIN_DEG_DEFAULT = 0.1
NODATA_U8 = 255
CHUNK_ROWS = 256  # 동시 실행 중인 gpt 프로세스와 메모리 경쟁 시 작게 유지


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


def reproject_chunk(
    src_path: Path, window_transform, win_width: int, win_height: int, dst_crs,
) -> np.ndarray:
    with rasterio.open(src_path) as src:
        dst = np.full((win_height, win_width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=window_transform, dst_crs=dst_crs,
            resampling=Resampling.bilinear, src_nodata=0.0, dst_nodata=np.nan,
        )
    return dst


def save_u8(path: Path, arr: np.ndarray, transform, crs) -> None:
    profile = {
        "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
        "dtype": "uint8", "crs": crs, "transform": transform, "nodata": NODATA_U8,
        "compress": "DEFLATE", "tiled": True,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="baseline vs 7/13 dB 차분 + 보수적 신규침수 탐지")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT, help="수체 판정 dB 임계값")
    parser.add_argument("--drop", type=float, default=DROP_THRESHOLD_DEFAULT, help="baseline 대비 요구 하락폭(dB, 음수)")
    parser.add_argument("--margin", type=float, default=AOI_MARGIN_DEG_DEFAULT, help="AOI 여백(도)")
    args = parser.parse_args()

    if not BASELINE_VRT.exists():
        raise FileNotFoundError(f"{BASELINE_VRT} 없음 - build_baseline_composite_grd.py 먼저 실행")
    if not POST_VRT.exists():
        raise FileNotFoundError(f"{POST_VRT} 없음")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with rasterio.open(POST_VRT) as ref:
        res_deg = abs(ref.transform.a)
        crs = ref.crs
    transform, width, height = build_target_grid(res_deg, args.margin)
    print(f"공통 격자: {width} x {height} px, 해상도 {res_deg:.7f}도 (~10m)")
    print(f"임계값: post dB < {args.db} AND 하락폭 <= {args.drop} AND baseline dB >= {args.db}")

    min_lon, min_lat, max_lon, max_lat = aoi_bbox(args.margin)
    center_lat = (min_lat + max_lat) / 2
    px_area_km2 = (res_deg * 111_320.0) * (res_deg * 111_320.0 * np.cos(np.radians(center_lat))) / 1e6

    diff_profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": crs, "transform": transform, "nodata": np.nan,
        "compress": "DEFLATE", "tiled": True,
    }

    n_valid_both = n_baseline_water = n_post_water = n_flood_conservative = 0

    with rasterio.open(DIFF_OUT, "w", **diff_profile) as diff_dst, \
         rasterio.open(FLOOD_OUT, "w", **{**diff_profile, "dtype": "uint8", "nodata": NODATA_U8}) as flood_dst:

        for row0 in range(0, height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, height - row0)
            win_transform = rasterio.windows.transform(
                rasterio.windows.Window(0, row0, width, nrows), transform
            )

            base_db = reproject_chunk(BASELINE_VRT, win_transform, width, nrows, crs)
            post_db = reproject_chunk(POST_VRT, win_transform, width, nrows, crs)

            valid = np.isfinite(base_db) & np.isfinite(post_db)
            diff = np.where(valid, post_db - base_db, np.nan).astype("float32")

            baseline_water = valid & (base_db < args.db)
            post_water = valid & (post_db < args.db)
            conservative = valid & post_water & (diff <= args.drop) & (~baseline_water)

            flood_out = np.where(valid, conservative.astype("uint8"), NODATA_U8)

            win = rasterio.windows.Window(0, row0, width, nrows)
            diff_dst.write(diff, 1, window=win)
            flood_dst.write(flood_out, 1, window=win)

            n_valid_both += int(valid.sum())
            n_baseline_water += int(baseline_water.sum())
            n_post_water += int(post_water.sum())
            n_flood_conservative += int(conservative.sum())

    total_px = width * height
    print(f"\n두 시점 모두 유효(교차 커버리지): {100 * n_valid_both / total_px:.1f}%")
    print(f"baseline 수체(비교 범위 내): {n_baseline_water * px_area_km2:,.2f} km^2")
    print(f"7/13 수체(단순 dB 임계값만): {n_post_water * px_area_km2:,.2f} km^2")
    print(f"신규 침수(보수적, 3중 조건): {n_flood_conservative * px_area_km2:,.2f} km^2")
    print(f"\n저장: {DIFF_OUT.name}, {FLOOD_OUT.name}")


if __name__ == "__main__":
    main()
