# -*- coding: utf-8 -*-
"""시도(광역) 경계를 **가볍게 단순화한 GeoJSON 한 장**으로 굽는다.

왜 필요한가
-----------
대시보드(scene_dashboard.py)가 새 촬영의 "대략적인 위치"를 충남·전남처럼
사람이 읽는 이름으로 찍어야 하는데, 그 판정을 **표준 라이브러리만으로**
해야 한다(대시보드는 회사 PC에서 conda 없이 떠 있어야 한다). 그래서
geopandas가 필요한 일 — 원본 경계 읽기·시도 단위 병합·단순화 — 은 이
스크립트가 **한 번만** 하고, 결과를 `geojson/sido_simplified.geojson`으로
저장한다. 대시보드는 그 파일에 순수 파이썬 point-in-polygon만 돌린다.

원본
----
- 남한 17개 시도: `20260709_flood/ref/korea_emd_boundary.gpkg` (읍면동 레이어,
  raqoon886/Local_HangJeongDong → 행정안전부 행정구역 경계). `sidonm`으로 병합.
- 북한 11개 도·시: WFP COD-AB adm1
  (`20260709_flood/20240717_Flood_Korea/행정구역도_shp/prk_adm_wfp_20190624_shp.zip`).
  영문 이름뿐이라 아래 표로 한글 이름을 붙인다.

정밀도를 일부러 버린다
----------------------
용도가 "충남쯤"이라 500 m 수준이면 충분하다. `--tolerance`(기본 0.005°)로
단순화하고, `--min-area`(기본 0.0005°² ≈ 5 km²)보다 작은 섬은 버린다.
그래야 파일이 수백 KB로 떨어져 git에 넣고 매번 통째로 읽어도 부담이 없다.
제주(1,850 km²)·울릉도(72 km²)는 남고, 독도급 바위섬만 빠진다.

실행(연 1회, 원본이 갱신될 때만):
    conda run -n gis_copy python -m s1.tools.monitor.build_sido_geojson
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon

PROJECT_DIR = Path(__file__).resolve().parents[3]
KR_GPKG = PROJECT_DIR / "20260709_flood" / "ref" / "korea_emd_boundary.gpkg"
NK_ZIP = (PROJECT_DIR / "20260709_flood" / "20240717_Flood_Korea" / "행정구역도_shp"
          / "prk_adm_wfp_20190624_shp.zip")
NK_LAYER = "prk_admbnda_adm1_wfp_20190624.shp"
OUT_PATH = PROJECT_DIR / "geojson" / "sido_simplified.geojson"

# 보고서 표기와 같은 약칭(20260709_flood/scripts/satinv/boundary.py SIDO_SHORT).
KR_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}

# WFP adm1 영문명 → 한글. 도(道)는 "함북"처럼 줄여 쓰지 않는다 — 북한 지명은
# 줄임말이 일반적이지 않아 오히려 못 알아본다.
NK_KOREAN = {
    "Jagang": "자강도", "Kangwon": "강원도(북)", "Nampo": "남포",
    "North Hamgyong": "함경북도", "North Hwanghae": "황해북도",
    "North Pyongan": "평안북도", "Pyongyang": "평양",
    "Ryanggang": "양강도", "South Hamgyong": "함경남도",
    "South Hwanghae": "황해남도", "South Pyongan": "평안남도",
    "Rason": "라선", "Kaesong": "개성",
}


def drop_small(geom, min_area: float):
    """min_area(도²)보다 작은 조각을 버린다. 전부 작으면 원본을 그대로 둔다."""
    if isinstance(geom, Polygon):
        return geom
    parts = [g for g in geom.geoms if g.area >= min_area]
    if not parts:
        return geom
    return MultiPolygon(parts) if len(parts) > 1 else parts[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="시도 경계 단순화 GeoJSON 생성")
    ap.add_argument("--tolerance", type=float, default=0.005,
                    help="Douglas-Peucker 허용오차(도). 기본 0.005 ≈ 500 m")
    ap.add_argument("--min-area", type=float, default=0.0005,
                    help="버릴 섬의 면적 상한(도²). 기본 0.0005 ≈ 5 km²")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    rows = []

    kr = gpd.read_file(KR_GPKG, layer="emd")
    kr = kr.dissolve(by="sidonm").reset_index()
    for _, r in kr.iterrows():
        full = r["sidonm"]
        rows.append({"name": KR_SHORT.get(full, full), "full": full,
                     "region": "KR", "geometry": r.geometry})

    nk = gpd.read_file(f"zip://{NK_ZIP}!{NK_LAYER}").to_crs(4326)
    for _, r in nk.iterrows():
        en = r["ADM1_EN"]
        rows.append({"name": NK_KOREAN.get(en, en), "full": NK_KOREAN.get(en, en),
                     "region": "NK", "geometry": r.geometry})

    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry="geometry", crs=4326)
    gdf["geometry"] = gdf.geometry.simplify(args.tolerance, preserve_topology=True)
    gdf["geometry"] = gdf.geometry.apply(lambda g: drop_small(g, args.min_area))
    gdf = gdf[~gdf.geometry.is_empty]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(gdf.to_json(), encoding="utf-8")

    size_kb = args.out.stat().st_size / 1024
    print(f"{len(gdf)}개 시도 → {args.out} ({size_kb:.0f} KB, "
          f"tolerance {args.tolerance}°, min-area {args.min_area}°²)")
    for _, r in gdf.iterrows():
        print(f"  {r['region']}  {r['name']:<8} {r['full']}")


if __name__ == "__main__":
    main()
