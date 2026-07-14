# -*- coding: utf-8 -*-
"""
GRD 버전 pre-event 기준 수체 지도. build_baseline_water.py(SLC용)와 동일한
로직(dB < 임계값 AND HAND < 임계값, 여러 날짜 합집합)을 GRD 날짜 모자이크
(downloads/rtc_grd/s1_rtc_db_mosaic_<날짜>.vrt)에 적용한다.

SLC baseline과 다른 점:
  - GRD는 AOI 서브셋 없이 전체 씬을 처리하므로 pre-event 5개 날짜(6/25, 6/26,
    7/1, 7/2, 7/3) 전부 사용 가능 (SLC는 7/3이 AOI 밖이라 4개만 썼음).
  - 산출물 파일명에 _grd 접미사를 붙여 기존 SLC 기준 baseline과 분리.

실행:
    conda run -n s1_snappy python build_baseline_water_grd.py
    conda run -n s1_snappy python build_baseline_water_grd.py --db -18 --hand 15
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
HAND_VRT = PROJECT_DIR / "downloads" / "hand" / "hand_aoi.vrt"
OUT_DIR = PROJECT_DIR / "downloads" / "water"
AOI_GEOJSON = PROJECT_DIR / "Korea_flood_AOI.geojson"

AOI_MARGIN_DEG = 0.1
DB_THRESHOLD_DEFAULT = -16.0
HAND_THRESHOLD_M_DEFAULT = 10.0
NODATA_U8 = 255

# GRD는 전체 씬 처리라 AOI 미교차 문제가 없어 pre-event 5개 날짜 전부 사용
PRE_EVENT_DATES = ["20260625", "20260626", "20260701", "20260702", "20260703"]


def aoi_bbox(margin_deg: float) -> tuple[float, float, float, float]:
    with open(AOI_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    geom = gj["features"][0]["geometry"] if "features" in gj else gj.get("geometry", gj)
    coords = geom["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (
        min(lons) - margin_deg,
        min(lats) - margin_deg,
        max(lons) + margin_deg,
        max(lats) + margin_deg,
    )


def build_target_grid(res_deg: float, margin_deg: float):
    min_lon, min_lat, max_lon, max_lat = aoi_bbox(margin_deg)
    width = int(round((max_lon - min_lon) / res_deg))
    height = int(round((max_lat - min_lat) / res_deg))
    transform = from_origin(min_lon, max_lat, res_deg, res_deg)
    return transform, width, height


def reproject_to_grid(
    src_path: Path,
    transform,
    width: int,
    height: int,
    resampling: Resampling,
    src_nodata: float | None = None,
):
    with rasterio.open(src_path) as src:
        dst = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=src.crs,
            resampling=resampling,
            src_nodata=src_nodata,
            dst_nodata=np.nan,
        )
    return dst


def pixel_area_km2(res_deg: float, center_lat: float) -> float:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(center_lat))
    return (res_deg * m_per_deg_lat) * (res_deg * m_per_deg_lon) / 1e6


def save_u8(path: Path, arr: np.ndarray, transform, crs) -> None:
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": transform,
        "nodata": NODATA_U8,
        "compress": "DEFLATE",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="GRD 기준 dB+HAND pre-event baseline 생성")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    parser.add_argument("--hand", type=float, default=HAND_THRESHOLD_M_DEFAULT)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mosaics = {d: RTC_GRD_DIR / f"s1_rtc_db_mosaic_{d}.vrt" for d in PRE_EVENT_DATES}
    missing = [d for d, p in mosaics.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"GRD 모자이크 없음: {missing}")

    with rasterio.open(next(iter(mosaics.values()))) as ref:
        res_deg = abs(ref.transform.a)
        crs = ref.crs
    transform, width, height = build_target_grid(res_deg, AOI_MARGIN_DEG)
    print(f"기준 격자: {width} x {height} px, 해상도 {res_deg:.7f}도 (~10m)")

    hand = reproject_to_grid(HAND_VRT, transform, width, height, Resampling.bilinear)
    hand_valid = np.isfinite(hand)
    print(f"HAND 유효 픽셀: {100 * hand_valid.mean():.1f}%")

    min_lon, min_lat, max_lon, max_lat = aoi_bbox(AOI_MARGIN_DEG)
    center_lat = (min_lat + max_lat) / 2
    px_area_km2 = pixel_area_km2(res_deg, center_lat)

    observed_count = np.zeros((height, width), dtype="uint8")
    water_count = np.zeros((height, width), dtype="uint8")

    for date, path in mosaics.items():
        db = reproject_to_grid(
            path, transform, width, height, Resampling.bilinear, src_nodata=0.0
        )
        valid = np.isfinite(db) & (db != 0)

        water = valid & (db < args.db) & hand_valid & (hand < args.hand)

        observed_count += valid.astype("uint8")
        water_count += water.astype("uint8")

        mask_u8 = np.where(valid, water.astype("uint8"), NODATA_U8)
        out_path = OUT_DIR / f"{date}_water_mask_grd.tif"
        save_u8(out_path, mask_u8, transform, crs)

        area = water.sum() * px_area_km2
        cover = 100 * valid.mean()
        print(f"[{date}] 커버리지 {cover:5.1f}% | 수체 후보 {area:7.2f} km^2 -> {out_path.name}")

    observed_any = observed_count > 0
    baseline = np.where(observed_any, (water_count > 0).astype("uint8"), NODATA_U8)
    save_u8(OUT_DIR / "baseline_water_union_grd.tif", baseline, transform, crs)
    save_u8(
        OUT_DIR / "water_frequency_grd.tif",
        np.where(observed_any, water_count, NODATA_U8),
        transform,
        crs,
    )
    save_u8(
        OUT_DIR / "observed_count_grd.tif",
        np.where(observed_any, observed_count, NODATA_U8),
        transform,
        crs,
    )

    baseline_area = (baseline == 1).sum() * px_area_km2
    always_water = ((water_count == observed_count) & observed_any & (observed_count > 1)).sum() * px_area_km2
    print(f"\n임계값: dB < {args.db} AND HAND < {args.hand} m")
    print(f"baseline 수체 면적(합집합): {baseline_area:.2f} km^2")
    print(f"모든 관측 날짜에서 수체로 잡힌 면적(상시 수체 후보): {always_water:.2f} km^2")
    print(f"\n저장 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
