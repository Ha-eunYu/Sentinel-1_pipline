# -*- coding: utf-8 -*-
"""신규 한반도 S1 GRD 다운로드(오늘 근접순). 이미 받은 zip은 건너뛴다.
main_s1_list_grd.py의 로직을 재사용하되 target을 최신일로, skip-existing 추가.
실행: conda run -n s1_pipeline python scratch_download_new_korea.py
"""
from __future__ import annotations

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date
from stac.download_s1 import choose_download_url, download_odata_cdse_with_retry

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
out.out_dir.mkdir(parents=True, exist_ok=True)
download_dir = out.out_dir / "sentinel1_grd"
download_dir.mkdir(parents=True, exist_ok=True)

cfg = S1SearchConfig(
    bbox=[123.0, 32.5, 131.5, 43.5],
    intersects_geojson=None,
    collection="sentinel-1-grd",
    window_days=8,
    max_items=300,
    instrument_mode="IW",
    orbit_state=None,
    product_type=None,
    polarization=None,
)
TARGET = "2026-07-26"     # 이 날짜 근접순
MAX_DOWNLOADS = 6         # 신규 6장(7/26 1 + 7/25 5)

client = open_cdse_stac_client(cdse)
res = list_s1_items_for_date(client, TARGET, cfg)
if res["status"] != "ok":
    raise SystemExit(f"검색 실패: {res.get('reason')}")

have = {p.stem for p in download_dir.glob("*.zip")}
cands = res["candidates"]
# 이미 받은 것 제외, 근접순 앞에서 MAX_DOWNLOADS개
new_cands = [c for c in cands if c["id"] not in have][:MAX_DOWNLOADS]
print(f"후보 {len(cands)}개 중 신규 {len(new_cands)}개 다운로드:")
for c in new_cands:
    print(f"  {c['datetime'][:10]}  {c['id']}")

for c in new_cands:
    out_file = download_dir / f"{c['id']}.zip"
    if out_file.exists():
        print(f"skip (exists): {c['id']}")
        continue
    try:
        url = choose_download_url(zipper_url=c.get("zipper_url"),
                                  product_href=c.get("product_href"), allow_fallback=False)
        print(f"downloading {c['id']} ...")
        download_odata_cdse_with_retry(url, out_file)
        print(f"  done: {out_file.name} ({out_file.stat().st_size/1e6:.0f} MB)")
    except Exception as e:
        print(f"ERROR {c['id']}: {e}")
        continue
print("=== DOWNLOAD DONE ===")
