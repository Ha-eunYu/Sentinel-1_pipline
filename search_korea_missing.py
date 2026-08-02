# -*- coding: utf-8 -*-
"""한반도 6~7월 S1 GRD 중 **아직 안 받은 것**을 찾는다(다운로드는 안 함).

왜
--
로컬 보유분으로만 시계열을 냈더니 밀양호 2026-07이 1시점뿐이었다. 그런데
로컬은 "내려받은 것"이지 "있는 것"이 아니다. 아카이브에 뭐가 더 있는지
날짜별로 훑어 목록만 낸다.

⚠ STAC bbox 교차는 **공칭 범위**라 과대집계된다. 실제 관측 여부는 받아서
   풋프린트(KML)를 봐야 하고, 유효화소는 RTC까지 돌려야 안다.
   실측: 밀양호를 STAC bbox로 세면 2026-07에 8장인데, 실제 풋프린트 포함은
   2장이었다(07-03, 07-15).

실행:
    conda run -n s1_pipeline python search_korea_missing.py
    conda run -n s1_pipeline python search_korea_missing.py 202506 202507 202606 202607
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date

MONTHS = sys.argv[1:] or ["202506", "202507", "202606", "202607"]
# 남한 위주(북한 접경 일부 포함). 5대강 + 주요 댐을 담는다.
BBOX = [125.0, 33.0, 130.0, 38.5]

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
download_dir = out.out_dir / "sentinel1_grd"
rtc_dir = out.out_dir / "rtc_grd_frost_vh"

import re as _re

_KEY = _re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    """씬 식별 키 — **끝 해시를 뺀다.**

    같은 촬영인데 제품 생성 해시가 다르다. 실측(2026-08-03, 2025-07-07):

        STAC   ..._059976_077359_**E45B**_COG
        로컬    ..._059976_077359_**EDCA**.zip
        로컬    ..._059976_077359_**4653**_COG.SAFE

    끝 4자리와 `_COG` 유무로 비교하면 이미 받은 것을 전부 '신규'로 센다
    (2025-07 17장을 통째로 신규로 셌다). 위성·모드·시작·종료·절대궤도·
    데이터테이크까지가 촬영을 유일하게 정한다.
    """
    m = _KEY.search(name)
    return m.group(1) if m else name


# .zip과 압축 해제된 .SAFE 둘 다 본다 — 로컬에 섞여 있다
have = {key(p.name) for p in download_dir.iterdir()
        if p.suffix in (".zip",) or p.name.endswith(".SAFE")}
rtc = {key(p.name) for p in rtc_dir.glob("*.tif")}

# 이미 처리해 NAS에 둔 것 — 다시 받지 않는다
NAS = Path(r"X:\02_Analysis\20260708_Flood")
nas: set[str] = set()
if NAS.exists():
    for pat in ("*.zip", "*.SAFE", "*.tif"):
        for p in NAS.rglob(pat):
            nas.add(key(p.name.split("_rtc")[0]))
print(f"로컬 GRD {len(have)} · VH RTC {len(rtc)} · NAS {len(nas)}\n")

client = open_cdse_stac_client(cdse)
cfg = S1SearchConfig(
    bbox=BBOX, intersects_geojson=None, collection="sentinel-1-grd",
    window_days=6, max_items=300, instrument_mode="IW",
    orbit_state=None, product_type=None, polarization=None,
)

seen: dict[str, dict] = {}
for mon in MONTHS:
    y, m = int(mon[:4]), int(mon[4:])
    d = date(y, m, 1)
    # 6일 창을 겹쳐가며 그 달 전체를 훑는다
    while d.month == m:
        res = list_s1_items_for_date(client, d.isoformat(), cfg)
        if res.get("status") == "ok":
            for c in res.get("candidates", []):
                seen.setdefault(c["id"], c)
        d += timedelta(days=5)

rows = []
for cid, c in seen.items():
    dt = str(c.get("datetime", ""))[:10]
    if not dt.replace("-", "")[:6] in MONTHS:
        continue
    k = key(cid)
    st = ("RTC" if k in rtc else
          "보유" if k in have else
          "NAS" if k in nas else "★신규")
    rows.append((dt, str(c.get("orbit_state", ""))[:4],
                 str(c.get("relative_orbit", "")), cid[:3], cid, st))

rows.sort()
print(f"{'촬영일':<12}{'궤도':<6}{'rel':<6}{'위성':<5}{'상태':<7}씬")
print("-" * 78)
for dt, orb, rel, sat, cid, st in rows:
    print(f"{dt:<12}{orb:<6}r{rel:<5}{sat:<5}{st:<7}...{cid[-14:]}")

from collections import Counter
cnt = Counter(r[5] for r in rows)
print(f"\n총 {len(rows)}장 · " + " · ".join(
    f"{k} {v}" for k, v in sorted(cnt.items())))
print("\n날짜별 신규:")
from collections import Counter
for dt, cnt in sorted(Counter(r[0] for r in rows if r[5] == "★신규").items()):
    print(f"  {dt}  {cnt}장")
