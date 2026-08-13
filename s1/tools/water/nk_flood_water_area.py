# -*- coding: utf-8 -*-
"""
북한(NK) 홍수 지역별 before/after 수체 면적 산정.

입력:
  - flood_nk_20260725.gpkg : QGIS로 그린 지역(군/댐) 폴리곤 레이어(EPSG:4326, MultiPolygon).
    속성: id, 지역, after_date, after_scen, date_1, scene_1, date_2, scene_2
      after_* = 홍수일(7/25) 관측, date_1/scene_1·date_2/scene_2 = 비교(before) 관측.
  - downloads/water_otsu/flood_water_total_<YYYYMMDD>_o<절대궤도>[_frost].tif
    : build_water_per_date_otsu.py가 만든 궤도·날짜별 수체 지도(0=비수체,1=수체,255=미관측).
  - (선택) downloads/water/scene_water/<씬>_<임계값dB>.tif : 씬 단위 고정임계 수체 지도(override).

방법:
  각 폴리곤을 관측일별 수체 지도에 마스킹(rasterio.mask) → 수체(값 1) 화소 수 ×
  위도 보정 화소 지상면적으로 km² 환산. 관측일에 대응하는 지도는 그 날짜의
  water map(_frost 우선, 없으면 Refined Lee)을 쓰되, OVERRIDES로 특정 지역·관측을
  특정 scene_water 지도(예: 안변군 after → 59A8_-12.tif)로 덮어쓸 수 있다.

  화소 지상면적(EPSG:4326, 10m 격자): (px_w_deg·111320·cos φ) × (px_h_deg·111320).

산출:
  downloads/water_otsu/nk_water_before_after_20260725.csv
  헤더: id, 지역, after_date, after_scen, 수체km², date_1, scen_1, 수체km²_1,
        date_2, scen_2, 수체km²_2  (date_2/scene_2 없는 지역은 date_2 계열 공란)

실행:
  conda run -n gis_clean python nk_flood_water_area.py
"""
from __future__ import annotations

import csv
import glob
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from s1.core.paths import PROJECT_DIR as PROJ  # 저장소 루트
NK_DIR = PROJ / "flood_nk_water_area"          # 문서·데이터 정리 폴더(2026-07-29)
GPKG = NK_DIR / "flood_nk_20260725.gpkg"
WDIR = PROJ / "downloads" / "water_otsu"        # 날짜·궤도별 water map은 여기 유지
SCENE_WATER = PROJ / "downloads" / "water" / "scene_water"
OUT_CSV = NK_DIR / "nk_water_before_after_20260725.csv"

# 지역·관측별 override: (지역, 관측키) -> scene_water 상대경로.
# 관측키: "after" | "date_1" | "date_2".
# 안변군 after는 후보 궤도맵(4303/59A8 모자이크)보다 59A8 단독 −12dB 지도를 쓰기로 지정.
OVERRIDES: dict[tuple[str, str], str] = {
    ("안변군", "after"): "59A8_-12.tif",
}


def find_date_map(date_yyyymmdd: str) -> list[str]:
    """그 날짜의 water map 경로들. _frost(Frost) 우선, 없으면 무접미사(Refined Lee)."""
    fr = sorted(glob.glob(str(WDIR / f"flood_water_total_{date_yyyymmdd}_o*_frost.tif")))
    if fr:
        return fr
    return sorted(glob.glob(str(WDIR / f"flood_water_total_{date_yyyymmdd}_o*.tif")))


def water_km2(maps: list[str], geom) -> tuple[float | None, float | None]:
    """폴리곤 내 수체 면적 km²와 관측 면적 km². 여러 궤도맵 중 관측화소가 가장 많은 것 사용."""
    if not maps:
        return None, None
    lat = geom.centroid.y
    best = (-1, None, None)  # (n_obs, water_km2, obs_km2)
    for m in maps:
        with rasterio.open(m) as ds:
            pw, ph = abs(ds.transform.a), abs(ds.transform.e)
            try:
                arr, _ = rio_mask(ds, [geom.__geo_interface__], crop=True, filled=True, nodata=255)
            except Exception:
                continue
        a = arr[0]
        n_obs = int(np.sum((a == 0) | (a == 1)))
        if n_obs <= best[0]:
            continue
        pxm2 = (pw * 111320.0 * math.cos(math.radians(lat))) * (ph * 111320.0)
        best = (n_obs, int(np.sum(a == 1)) * pxm2 / 1e6, n_obs * pxm2 / 1e6)
    return (round(best[1], 2) if best[1] is not None else None,
            round(best[2], 2) if best[2] is not None else None)


def maps_for(region: str, obs_key: str, date_yyyymmdd: str | None) -> list[str]:
    ov = OVERRIDES.get((region, obs_key))
    if ov:
        p = SCENE_WATER / ov
        return [str(p)] if p.exists() else []
    return find_date_map(date_yyyymmdd) if date_yyyymmdd else []


def ymd(v):
    return None if v is None or str(v) == "NaT" else pd.Timestamp(v).strftime("%Y%m%d")


def disp(v):
    return "" if v is None or str(v) == "NaT" else pd.Timestamp(v).strftime("%Y-%m-%d")


def main() -> None:
    gdf = gpd.read_file(GPKG)
    rows = []
    for _, r in gdf.iterrows():
        region = r["지역"]
        aw, _ = water_km2(maps_for(region, "after", ymd(r["after_date"])), r.geometry)
        w1, _ = water_km2(maps_for(region, "date_1", ymd(r["date_1"])), r.geometry)
        has2 = r["scene_2"] not in (None, "") and str(r["date_2"]) != "NaT"
        w2 = water_km2(maps_for(region, "date_2", ymd(r["date_2"])), r.geometry)[0] if has2 else None
        rows.append({
            "id": int(r["id"]), "지역": region,
            "after_date": disp(r["after_date"]), "after_scen": r["after_scen"], "수체km²": aw,
            "date_1": disp(r["date_1"]), "scen_1": r["scene_1"], "수체km²_1": w1,
            "date_2": disp(r["date_2"]) if has2 else "", "scen_2": r["scene_2"] if has2 else "",
            "수체km²_2": w2 if has2 else "",
        })
    cols = ["id", "지역", "after_date", "after_scen", "수체km²", "date_1", "scen_1",
            "수체km²_1", "date_2", "scen_2", "수체km²_2"]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(" | ".join(f"{c}={r[c]}" for c in cols))
    print(f"\nCSV: {OUT_CSV}")


if __name__ == "__main__":
    main()
