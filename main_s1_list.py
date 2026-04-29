from __future__ import annotations

import json
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date
from stac.download_s1 import get_cdse_access_token, download_odata_product

def main() -> None:
    load_env(".env")  # 현재 사용자 환경 반영

    cdse_cfg = CDSEConfig()
    out_cfg = OutputConfig()
    out_cfg.out_dir.mkdir(parents=True, exist_ok=True)

    cfg = S1SearchConfig(
        bbox = [38.9, 21.2, 39.7, 21.9],   # 예시 AOI
        # bbox=[127.2, 36.2, 127.6, 36.5],   # 예시 AOI
        # collection="sentinel-1-grd",       # "sentinel-1-slc" 로 바꾸면 SLC 검색
        collection="sentinel-1-slc",       # "sentinel-1-slc" 로 바꾸면 SLC 검색
        window_days=10,
        max_items=200,
        instrument_mode="IW",
        orbit_state=None,                  # "ascending" / "descending"
        product_type=None,
        polarization=None,
    )

    targets = [
        ("Jeddah_flood", "2022-11-24"),
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

    for sensor, date_str in targets:
        print(f"\n=== {sensor} | target={date_str} | collection={cfg.collection} ===")
        res = list_s1_items_for_date(client, date_str, cfg, k=10)
        results["targets"].append({"sensor": sensor, **res})

        if res["status"] != "ok":
            print("-> NO ITEMS:", res.get("reason"))
            continue

        print("-> search used:", res["search_used"])
        print("-> count found:", res["count_found"])
        
        selected_items = []
        
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
        url = cand.get("zipper_url")

        if not url:
            print(f"SKIP no zipper url: {cand['id']}")
            continue

        out_file = download_dir / f"{cand['id']}.zip"
        download_odata_product(url, out_file, access_token)

if __name__ == "__main__":
    main()