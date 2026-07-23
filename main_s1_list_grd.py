from __future__ import annotations

import json
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date
from stac.download_s1 import choose_download_url, download_odata_cdse_with_retry
# import geopandas as gpd

# def bbox_from_shp(shp_path: str | Path) -> list[float]:
#     shp_path = Path(shp_path)

#     if not shp_path.exists():
#         raise FileNotFoundError(f"Shapefile not found: {shp_path}")

#     gdf = gpd.read_file(shp_path)

#     if gdf.empty:
#         raise ValueError(f"Shapefile is empty: {shp_path}")

#     if gdf.crs is None:
#         raise ValueError(
#             "Shapefile CRS is missing. "
#             "STAC bbox requires EPSG:4326 lon/lat coordinates."
#         )

#     # STAC bbox는 lon/lat 기준이므로 EPSG:4326으로 변환
#     gdf = gdf.to_crs("EPSG:4326")

#     minx, miny, maxx, maxy = gdf.total_bounds

#     return [
#         float(minx),
#         float(miny),
#         float(maxx),
#         float(maxy),
#     ]

def load_geojson_geometry(path: str | Path) -> dict:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    geojson_type = data.get("type")

    geometry_types = {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }

    if geojson_type in geometry_types:
        return data

    if geojson_type == "Feature":
        geom = data.get("geometry")
        if geom is None:
            raise ValueError(f"GeoJSON Feature has no geometry: {path}")
        return geom

    if geojson_type == "FeatureCollection":
        geoms = [
            feature.get("geometry")
            for feature in data.get("features", [])
            if feature.get("geometry") is not None
        ]

        if not geoms:
            raise ValueError(f"GeoJSON FeatureCollection has no geometries: {path}")

        if len(geoms) == 1:
            return geoms[0]

        return {
            "type": "GeometryCollection",
            "geometries": geoms,
        }

    raise ValueError(f"Unsupported GeoJSON type: {geojson_type}")

def main() -> None:
    load_env(".env")  # 현재 사용자 환경 반영

    cdse_cfg = CDSEConfig()
    out_cfg = OutputConfig()
    out_cfg.out_dir.mkdir(parents=True, exist_ok=True)

    # cfg = S1SearchConfig(
    #     bbox = [38.9, 21.2, 39.7, 21.9],   # 예시 AOI
    #     # bbox=[127.2, 36.2, 127.6, 36.5],   # 예시 AOI
    #     # collection="sentinel-1-grd",       # "sentinel-1-slc" 로 바꾸면 SLC 검색
    #     collection="sentinel-1-slc",       # "sentinel-1-slc" 로 바꾸면 SLC 검색
    #     window_days=10,
    #     max_items=200,
    #     instrument_mode="IW",
    #     orbit_state=None,                  # "ascending" / "descending"
    #     product_type=None,
    #     polarization=None,
    # )

    # 검색 AOI: 느슨한 bbox(제주 포함, 여유 있게). 정확한 한반도 판정은
    # list_s1_items_for_date의 footprint 필터(Korea_Peninsula.geojson 실경계
    # 대조)가 한다 — 2026-07-23: 기존 Korea.geojson은 남쪽 경계가 34.57°N이라
    # 제주(33.1~33.6°N)가 빠져 있어, 제주 인근만 겹치는 정당한 프레임(예: 93DD)
    # 이 검색 자체에서 통째로 누락되는 버그가 있었다. bbox를 넓혀 이 문제를
    # 없애고, "중국/일본 전용" 배제는 뒤 단계의 정밀 footprint 필터에 맡긴다.
    KOREA_SEARCH_BBOX = [123.0, 32.5, 131.5, 43.5]

    cfg = S1SearchConfig(
        bbox=KOREA_SEARCH_BBOX,
        intersects_geojson=None,
        collection="sentinel-1-grd",
        window_days=15,
        max_items=200,
        instrument_mode="IW",
        orbit_state=None,
        product_type=None,
        polarization=None,
    )

    # 받고 싶은 날짜만 지정하면 그 날짜에 가까운 촬영일 순으로 내려받는다.
    # (라벨, "YYYY-MM-DD"). 시각은 필요 없다 — 날짜 근접도로 정렬한다.
    # 2026-07-23: 7/1(6프레임)·7/20(7프레임) zip이 RTC 완료 후 삭제 정책으로
    # 지워져 있어 Frost 재처리 대상에서 빠짐 -> 재다운로드.
    targets = [
        ("Korea_flood_0701", "2026-07-01"),
        ("Korea_flood_0720", "2026-07-20"),
    ]

    # 유일한 설정: 이 날짜 근접순으로 최대 몇 개를 내려받을지. None = 후보 전부.
    MAX_DOWNLOADS = 10

    client = open_cdse_stac_client(cdse_cfg)

    results = {
        "stac_url": cdse_cfg.stac_url,
        "config": cfg.to_dict(),
        "targets": [],
    }

    selected_items = []

    for sensor, date_str in targets:
        print(f"\n=== {sensor} | target={date_str} | collection={cfg.collection} ===")
        res = list_s1_items_for_date(client, date_str, cfg)
        results["targets"].append({"sensor": sensor, **res})

        if res["status"] != "ok":
            print("-> NO ITEMS:", res.get("reason"))
            continue

        print("-> search used:", res["search_used"])
        print("-> count found:", res["count_found"])

        # 지정 날짜 근접순 후보에서 MAX_DOWNLOADS개만 선택(None이면 전부).
        cands = res["candidates"]
        if MAX_DOWNLOADS is not None:
            cands = cands[:MAX_DOWNLOADS]
        print(f"-> 근접순 선택: {len(cands)}개 (전체 {res['count_found']}개 중)")

        for i, cand in enumerate(cands, start=1):
            print(f"   [{i}] id={cand['id']}")
            print(f"       datetime={cand['datetime']}")
            print(f"       platform={cand['platform']}")
            print(f"       orbit_state={cand['orbit_state']}")
            print(f"       relative_orbit={cand['relative_orbit']}")
            print(f"       instrument_mode={cand['instrument_mode']}")
            print(f"       polarization={cand['polarization']}")
            print(f"       product_type={cand['product_type']}")
            print(f"       assets={cand['assets']}")
            print(f"       product_href={cand['product_href']}")
            print(f"       zipper_url={cand['zipper_url']}")
            selected_items.append(cand)

    # SLC용 manifest(s1_stac_list_manifest.json)를 덮어쓰지 않도록 GRD 전용 파일로 저장
    out_path = out_cfg.out_dir / "s1_stac_list_manifest_grd.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n✅ Saved manifest: {out_path}")

    print("\n=== Download selected Sentinel-1 GRD products ===")

    # SLC 폴더(sentinel1/)와 섞이지 않도록 분리 — prepro*.py가 sentinel1/의
    # 첫 zip을 자동 선택하므로 GRD가 섞이면 SLC 체인에 잘못 들어갈 수 있음
    download_dir = out_cfg.out_dir / "sentinel1_grd"

    # (개수 제한은 위 MAX_DOWNLOADS에서 이미 적용됨)
    for cand in selected_items:
        try:
            out_file = download_dir / f"{cand['id']}.zip"

            product_url = choose_download_url(
                zipper_url=cand.get("zipper_url"),
                product_href=cand.get("product_href"),
                allow_fallback=False,
                # allow_fallback=True,
            )

            # 항목마다 토큰을 새로 받아서 다운로드한다 (CDSE 토큰은 수명이
            # 짧아, 여러 개를 이어받는 동안 만료되어 401이 나는 것을 방지).
            download_odata_cdse_with_retry(product_url, out_file)

        except Exception as e:
            print(f"ERROR downloading {cand['id']}: {e}")
            continue


if __name__ == "__main__":
    main()