# -*- coding: utf-8 -*-
"""섬진강댐·평림댐용 ASC127 8월 쌍(2025-08-11 ↔ 2026-08-07) GRD를 받는다.

왜 이 쌍인가
-----------
ASC54(2025-08-06 ↔ 2026-08-02)는 6개 댐 유역을 100% 덮지만 **섬진강댐·평림댐은
교차 0%**다. 두 유역을 두 해 모두 100% 덮는 궤도는 **ASC127**뿐이다
(DESC134도 덮지만 2026년 8월에 관측이 없어 짝이 안 된다).

2025년 ASC127 후보는 08-05·08-11·08-17·08-29 네 날짜인데 **08-11(S1C)**를
고른다. 나머지 셋은 S1A라 2026-08-07(S1D)과 짝지으면 S1A↔S1D가 되는데,
S1A는 2026-06-29에 운용을 마쳤다. 08-11을 쓰면 8개 유역 전체가 **S1C↔S1D**로
통일돼 위성 상이 단서를 하나만 달면 된다.

⚠ 2026-08-07 자료는 08-07 최초 조회 때 카탈로그에 없었다(촬영→등재 수 시간).
   "없다"는 결론은 조회 시점에 매인다.

씬 식별은 끝 해시를 뺀 키로 한다(`download_aug_pair.py`와 같은 규칙).

실행:
    conda run -n s1_pipeline python download_asc127_aug.py --dry-run
    conda run -n s1_pipeline python download_asc127_aug.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from s1.core.config import CDSEConfig, OutputConfig, load_env
from s1.stac.client import open_cdse_stac_client
from s1.stac.download_s1 import choose_download_url, download_odata_cdse_with_retry
from s1.stac.models import S1SearchConfig
from s1.stac.search_s1 import list_s1_items_for_date

DATES = ["2025-08-11", "2026-08-07"]
REL_ORBIT = 127
BBOX = [125.0, 32.8, 131.0, 39.5]

_KEY = re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    m = _KEY.search(name)
    return m.group(1) if m else name


def search(client, day: str, cfg, tries: int = 6):
    """CDSE STAC은 429(WAF)를 잘 뱉는다 — 지수 백오프."""
    delay = 20.0
    for i in range(tries):
        try:
            return list_s1_items_for_date(client, day, cfg)
        except Exception as e:                              # noqa: BLE001
            if ("429" not in str(e) and "Rate limit" not in str(e)) or i == tries - 1:
                raise
            print(f"    · 429 rate limit — {delay:.0f}초 대기", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)


DRY = "--dry-run" in sys.argv

load_env(".env")
out = OutputConfig()
dl = out.out_dir / "sentinel1_grd"
dl.mkdir(parents=True, exist_ok=True)

have = {key(p.name) for p in dl.iterdir()
        if p.suffix == ".zip" or p.name.endswith(".SAFE")}
rtc = {key(p.name) for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}
skip = have | rtc

client = open_cdse_stac_client(CDSEConfig())
cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                     collection="sentinel-1-grd", window_days=1,
                     max_items=300, instrument_mode="IW",
                     orbit_state=None, product_type=None, polarization=None)

found: dict[str, dict] = {}
for d in DATES:
    r = search(client, d, cfg)
    if not r or r.get("status") != "ok":
        print(f"⚠ {d} 검색 실패: {r}")
        continue
    for c in r.get("candidates", []):
        if str(c.get("datetime", ""))[:10] != d:
            continue
        if int(c.get("relative_orbit") or -1) != REL_ORBIT:
            continue
        found[key(c["id"])] = c
    time.sleep(2)

todo = [c for k, c in found.items() if k not in skip]
todo.sort(key=lambda c: str(c.get("datetime", "")))
print(f"\nASC{REL_ORBIT} {DATES[0]} ↔ {DATES[1]}")
print(f"검색됨 {len(found)}장 · 이미 보유 {len(found) - len(todo)}장 → "
      f"받을 것 **{len(todo)}장**\n")
for c in todo:
    print(f"  {str(c['datetime'])[:10]}  {str(c.get('platform', '')):<12}"
          f" r{c.get('relative_orbit', '')}  ...{c['id'][-14:]}")
if DRY:
    raise SystemExit("\n--dry-run: 받지 않았습니다.")

print()
ok = err = 0
for i, c in enumerate(todo, 1):
    f = dl / f"{c['id']}.zip"
    if f.exists():
        continue
    try:
        url = choose_download_url(zipper_url=c.get("zipper_url"),
                                  product_href=c.get("product_href"),
                                  allow_fallback=False)
        download_odata_cdse_with_retry(url, f)
        print(f"[{i}/{len(todo)}] {f.stat().st_size / 1e6:>5.0f} MB  {c['id'][-18:]}",
              flush=True)
        ok += 1
    except Exception as e:                                  # noqa: BLE001
        print(f"[{i}/{len(todo)}] 실패 {c['id'][-18:]}: {e}", flush=True)
        err += 1
print(f"\n완료 {ok} · 실패 {err}")
print("다음: batch_grd_rtc_frost.py --month 202508 / 202608 --pol VH "
      "--out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G")
