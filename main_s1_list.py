from __future__ import annotations

import json
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date
from stac.download_s1 import get_cdse_access_token, choose_download_url, download_odata_cdse
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

    korea_geojson = Path(__file__).resolve().parent / "Korea_flood_AOI.geojson"
    korea_geom = load_geojson_geometry(korea_geojson)



    cfg = S1SearchConfig(
        # bbox=korea_bbox,
        bbox=None,
        intersects_geojson=korea_geom,
        collection="sentinel-1-slc",
        window_days=15,
        max_items=200,
        instrument_mode="IW",
        orbit_state=None,
        product_type=None,
        polarization=None,
    )

    targets = [
        ("Korea_flood", "2026-07-08T18:30:00+09:00"),  # KST 촬영 시각
        # ("Jeddah_flood", "2022-11-24"),
        # ("ICEYE_ref", "2021-01-21"),
        # ("UMBRA_ref", "2024-07-17"),
        # ("Capella_ref", "2024-08-19"),
    ]

    client = open_cdse_stac_client(cdse_cfg)

    results = {
        "stac_url": cdse_cfg.stac_url,
        "config": cfg.to_dict(),
        "targets": [],
    }

    selected_items = []

    for sensor, date_str in targets:
        print(f"\n=== {sensor} | target={date_str} | collection={cfg.collection} ===")
        res = list_s1_items_for_date(client, date_str, cfg, k=10)
        results["targets"].append({"sensor": sensor, **res})

        if res["status"] != "ok":
            print("-> NO ITEMS:", res.get("reason"))
            continue

        print("-> search used:", res["search_used"])
        print("-> count found:", res["count_found"])
        
        
        for i, cand in enumerate(res["candidates_topk"], start=1):
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
            
            # # Jeddah pre/post pair:
            # # 2022-11-17 and 2022-11-29
            # if cand["id"].startswith("S1A_IW_SLC__1SDV_20221117") or cand["id"].startswith("S1A_IW_SLC__1SDV_20221129"):
            #     selected_item_ids.append(cand["id"])

    out_path = out_cfg.out_dir / "s1_stac_list_manifest.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n✅ Saved manifest: {out_path}")

    print("\n=== Download selected Sentinel-1 SLC products ===")

    access_token = get_cdse_access_token()
    download_dir = out_cfg.out_dir / "sentinel1"

    for cand in selected_items:
        try:
            out_file = download_dir / f"{cand['id']}.zip"

            product_url = choose_download_url(
                zipper_url=cand.get("zipper_url"),
                product_href=cand.get("product_href"),
                allow_fallback=False,
                # allow_fallback=True,
            )
            
            status, saved_path = download_odata_cdse(product_url, out_file, access_token)
            
            if status == "skipped":
                continue
        
        except Exception as e:
            print(f"ERROR downloading {cand['id']}: {e}")
            status = "error"
            continue


if __name__ == "__main__":
    main()