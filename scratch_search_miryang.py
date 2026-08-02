# -*- coding: utf-8 -*-
"""밀양호(밀양댐)를 덮는 S1 GRD가 아카이브에 몇 장 있는지 확인한다.

왜
--
로컬 보유분으로만 시계열을 냈더니 **2026년 7월 밀양호 관측이 1장(07-15)뿐**이었다.
그런데 로컬은 "내려받은 것"이지 "있는 것"이 아니다. 아카이브(CDSE STAC)에
더 있으면 받아서 시계열을 채울 수 있다.

밀양호  128.9498E 35.4709N (국가기본도 호소 TN_LKMH representative_point)

⚠ STAC 풋프린트는 **공칭 범위**다. 실제 유효화소가 있는지는 내려받아
   RTC까지 돌려야 안다(밀양호가 DESC134 경계상자 안이면서도 값이 없었다).

실행:
    conda run -n s1_pipeline python scratch_search_miryang.py
    conda run -n s1_pipeline python scratch_search_miryang.py 2025-07
"""
from __future__ import annotations

import sys
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date

MONTH = sys.argv[1] if len(sys.argv) > 1 else "2026-07"
LON, LAT = 128.9498, 35.4709
PAD = 0.25                      # 약 ±25 km — 스와스 가장자리 판정 여유

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
cfg = S1SearchConfig(
    bbox=[LON - PAD, LAT - PAD, LON + PAD, LAT + PAD],
    intersects_geojson=None,
    collection="sentinel-1-grd",
    window_days=31,             # 그 달 전체
    max_items=300,
    instrument_mode="IW",
    orbit_state=None,
    product_type=None,
    polarization=None,
)
client = open_cdse_stac_client(cdse)
mid = f"{MONTH}-16"
res = list_s1_items_for_date(client, mid, cfg)

have = {p.stem for p in (out.out_dir / "sentinel1_grd").glob("*.zip")}
# 이미 RTC까지 돌린 것
rtc = {p.name.split("_rtc")[0].replace(".SAFE", "")
       for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}

print(f"밀양호 {LON}E {LAT}N ±{PAD}°  |  {MONTH}  "
      f"status={res.get('status')} found={res.get('count_found')}")
print(f"{'상태':<8}{'촬영일':<12}{'궤도':<7}{'rel':<5}{'위성':<5}  씬 ID 끝자리")
print("-" * 70)

cands = sorted(res.get("candidates", []), key=lambda c: str(c.get("datetime", "")))
n_new = 0
for c in cands:
    cid = c["id"]
    dt = str(c.get("datetime", ""))[:10]
    stem = cid if cid.endswith(".SAFE") else cid
    downloaded = any(stem in h or h in stem for h in have)
    processed = any(stem[-9:] in r for r in rtc)
    st = "RTC완료" if processed else ("보유" if downloaded else "★신규")
    n_new += st == "★신규"
    print(f"{st:<8}{dt:<12}{str(c.get('orbit_state', ''))[:4]:<7}"
          f"r{str(c.get('relative_orbit', '')):<4}"
          f"{cid[:3]:<5}  ...{cid[-12:]}")

print(f"\n총 {len(cands)}장 · 신규 {n_new}장")
print("* 신규를 받으면 밀양호 시계열이 그만큼 늘어난다")
print("* 단 STAC 풋프린트는 공칭이라, 실제 유효화소는 RTC 후에 확인해야 한다")
