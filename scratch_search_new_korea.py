# -*- coding: utf-8 -*-
"""오늘(기준일) 근접으로 한반도 신규 S1 GRD를 검색해, 이미 받은 것과 대조.
다운로드는 하지 않고 목록만 출력한다(무엇이 새로 있는지 확인용).
실행: conda run -n s1_pipeline python scratch_search_new_korea.py [YYYY-MM-DD]
"""
from __future__ import annotations

import sys
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date

REF_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-27"

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
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
client = open_cdse_stac_client(cdse)
res = list_s1_items_for_date(client, REF_DATE, cfg)
have = {p.stem for p in (out.out_dir / "sentinel1_grd").glob("*.zip")}

print(f"ref={REF_DATE} status={res.get('status')} count_found={res.get('count_found')} reason={res.get('reason')}")
cands = res.get("candidates", [])
newc = []
for c in cands:
    dt = str(c.get("datetime", ""))[:10]
    is_new = c["id"] not in have
    if is_new:
        newc.append(c)
    print(f"  {'NEW ' if is_new else 'have'} {dt}  {c['id'][:62]}  {c.get('orbit_state','')[:4]} r{c.get('relative_orbit','')}")
print(f"\n총 후보 {len(cands)}개, 이미 보유 {len(cands)-len(newc)}개, 신규 {len(newc)}개")
# 신규 중 촬영일이 최신(REF 근처)인 것 요약
newdates = sorted({str(c.get('datetime',''))[:10] for c in newc})
print("신규 촬영일:", newdates)
