# -*- coding: utf-8 -*-
"""
dB 임계값 + HAND 결합으로 홍수 이전(pre-event) 기준 수체 지도를 만든다.

목적: 침수 탐지는 결국 "홍수 이후(post) 영상의 수체 후보 - 이전부터 있던
평상시 수체(baseline)"로 판단한다. 이 스크립트는 그 baseline을 만든다.
아직 post 영상이 없으므로 이번 산출물 자체가 침수 판정은 아니고,
이후 post 영상이 들어오면 detect_flood.py(다음 단계)에서 이 baseline과
비교하게 될 입력이다.

방법 (TERRAIN_AUX_DATA_KR.md 3절 "종합 활용 구도"):
    수체 후보 = (RTC dB < DB_THRESHOLD) AND (HAND < HAND_THRESHOLD_M)

  - dB 임계값: SAR에서 잔잔한 수면은 거울면반사(specular reflection)로 인해
    안테나 쪽으로 되돌아오는 신호가 거의 없어 매우 어둡게(-15~-25dB) 나온다.
    기본값 -16dB은 ASF HydroSAR 등 운영 시스템이 흔히 쓰는 값.
  - HAND 임계값: 하천에서 비슷한 고도(기본 10m)에 있는 저지대만 수체로
    인정해, 레이더 그림자나 매끈한 인공면(활주로 등)으로 인한 오탐을 제거.

여러 pre-event 날짜(6/25, 6/26, 7/1, 7/2)를 각각 판정한 뒤 **합집합(OR)**으로
baseline을 만든다. 저수지 수위 변동, 구름 없는 SAR라도 날짜별로 speckle/파랑
때문에 한 날짜만으로는 놓치는 수체 픽셀이 있을 수 있어, 여러 날짜 중
하나라도 수체로 잡히면 baseline에 포함시켜 "평상시 수체"를 보수적으로(널널하게)
잡는다. 반대로 침수 판정(다음 단계)에서는 post 하나만으로 새로 생긴 수체를 볼
것이므로, baseline은 최대한 실제 평상시 수체를 놓치지 않는 쪽이 유리하다.

입력:
  - downloads/rtc/s1_rtc_db_mosaic_<날짜>.vrt (build_rtc_mosaic.py 산출물)
  - downloads/hand/hand_aoi.vrt (download_hand.py 산출물)

출력 (downloads/water/):
  - baseline_water_union.tif   : 0=비수체, 1=수체(>=1개 날짜), 255=미관측
  - water_frequency.tif        : 관측된 날짜 중 수체로 잡힌 날짜 수 (0~4), QC용
  - observed_count.tif         : 유효 관측(커버) 날짜 수, QC용
  - <날짜>_water_mask.tif       : 날짜별 개별 마스크 (0/1/255)

실행:
    conda run -n s1_snappy python build_baseline_water.py
    conda run -n s1_snappy python build_baseline_water.py --db -18 --hand 15
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
RTC_DIR = PROJECT_DIR / "downloads" / "rtc"
HAND_VRT = PROJECT_DIR / "downloads" / "hand" / "hand_aoi.vrt"
OUT_DIR = PROJECT_DIR / "downloads" / "water"
AOI_GEOJSON = PROJECT_DIR / "Korea_flood_AOI.geojson"

AOI_MARGIN_DEG = 0.1
DB_THRESHOLD_DEFAULT = -16.0
HAND_THRESHOLD_M_DEFAULT = 10.0
NODATA_U8 = 255

# 이 4개 날짜가 현재 확보된 pre-event 시계열 (2026-07-08 홍수 이전 촬영)
PRE_EVENT_DATES = ["20260625", "20260626", "20260701", "20260702"]


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
            dst_crs=src.crs,  # 전부 EPSG:4326이므로 원본 CRS 그대로 사용
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
    parser = argparse.ArgumentParser(description="dB+HAND 기반 pre-event 기준 수체 지도 생성")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT, help=f"수체 판정 dB 임계값 (기본 {DB_THRESHOLD_DEFAULT})")
    parser.add_argument("--hand", type=float, default=HAND_THRESHOLD_M_DEFAULT, help=f"HAND 임계값(m) (기본 {HAND_THRESHOLD_M_DEFAULT})")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mosaics = {d: RTC_DIR / f"s1_rtc_db_mosaic_{d}.vrt" for d in PRE_EVENT_DATES}
    missing = [d for d, p in mosaics.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"모자이크 없음: {missing} (build_rtc_mosaic.py 먼저 실행)")

    # 기준 격자: RTC 해상도(10m급, 첫 모자이크에서 읽음)로 AOI+마진을 덮는 공통 그리드
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
        # RTC dB는 0을 사실상 NoData로 쓰므로 src_nodata=0을 지정해 bilinear
        # 보간에 0이 섞여 씬 가장자리 dB가 밝은 쪽으로 끌리는(수체 과소탐지)
        # 문제를 막는다. (HAND는 0이 유효값이라 별도로 src_nodata를 안 준다)
        db = reproject_to_grid(
            path, transform, width, height, Resampling.bilinear, src_nodata=0.0
        )
        valid = np.isfinite(db) & (db != 0)

        water = valid & (db < args.db) & hand_valid & (hand < args.hand)

        observed_count += valid.astype("uint8")
        water_count += water.astype("uint8")

        mask_u8 = np.where(valid, water.astype("uint8"), NODATA_U8)
        out_path = OUT_DIR / f"{date}_water_mask.tif"
        save_u8(out_path, mask_u8, transform, crs)

        area = water.sum() * px_area_km2
        cover = 100 * valid.mean()
        print(f"[{date}] 커버리지 {cover:5.1f}% | 수체 후보 {area:7.2f} km^2 -> {out_path.name}")

    observed_any = observed_count > 0
    baseline = np.where(observed_any, (water_count > 0).astype("uint8"), NODATA_U8)
    save_u8(OUT_DIR / "baseline_water_union.tif", baseline, transform, crs)
    save_u8(
        OUT_DIR / "water_frequency.tif",
        np.where(observed_any, water_count, NODATA_U8),
        transform,
        crs,
    )
    save_u8(
        OUT_DIR / "observed_count.tif",
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
