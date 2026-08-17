# -*- coding: utf-8 -*-
"""`search_korea_missing.py`가 찾은 미보유분을 내려받는다.

제외 규칙
---------
  · 로컬 `downloads/sentinel1_grd`에 이미 있는 것(.zip / .SAFE 둘 다)
  · VH RTC를 이미 돌린 것
  · **NAS `X:\\02_Analysis\\20260708_Flood`에 있는 것** — 이미 처리해 둔 것이라
    다시 받지 않는다(2026-08-03 사용자 지시)
  · 2025-06 — 대상 아님(같은 지시)

⚠ 씬 식별 키에서 **끝 해시를 빼야 한다.** 같은 촬영인데 제품 생성 해시가
   다르다(STAC `..._E45B_COG` vs 로컬 `..._EDCA.zip` vs `..._4653_COG.SAFE`).
   그대로 비교하면 이미 받은 것을 전부 신규로 세어 2025-07 17장을 헛으로
   다시 받게 된다.

실행:
    conda run -n s1_pipeline python download_korea_missing.py 202606 202607
    conda run -n s1_pipeline python download_korea_missing.py --dry-run 202606
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from s1.core.config import CDSEConfig, OutputConfig, load_env
from s1.stac.client import open_cdse_stac_client
from s1.stac.download_s1 import (choose_download_url,
                              download_odata_cdse_with_retry)
from s1.stac.models import S1SearchConfig
from s1.stac.search_s1 import list_s1_items_for_date

import re as _re

# `search_korea_missing.py`와 같은 규칙. import하면 그 모듈의 최상위 코드가
# sys.argv를 파싱해 버려서 여기 인자와 충돌한다 — 그래서 복사해 둔다.
_KEY = _re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    """씬 식별 키 — 끝 해시를 뺀 촬영 단위."""
    m = _KEY.search(name)
    return m.group(1) if m else name

args = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
MONTHS = args or ["202507", "202606", "202607"]
# 한반도 전체(북한 포함) 검색 상자. 예전 값 [125.0, 33.0, 130.0, 38.5]은 남한
# 위주라 북한·서해·동해 프레임이 통째로 빠졌다(2026-08-17 한반도 대상 확대).
# 느슨한 상자로 받아온 뒤 footprint 로 정확히 거른다(touches_korea).
BBOX = [124.0, 32.9, 132.0, 43.5]
NAS = Path(r"X:\02_Analysis\20260708_Flood")

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
dl = out.out_dir / "sentinel1_grd"
dl.mkdir(parents=True, exist_ok=True)

have = {key(p.name) for p in dl.iterdir()
        if p.suffix == ".zip" or p.name.endswith(".SAFE")}
rtc = {key(p.name) for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}
nas: set[str] = set()
if NAS.exists():
    for pat in ("*.zip", "*.SAFE", "*.tif"):
        nas |= {key(p.name) for p in NAS.rglob(pat)}
skip = have | rtc | nas
print(f"제외 대상 {len(skip)}건 (로컬 {len(have)} · RTC {len(rtc)} · NAS {len(nas)})")

client = open_cdse_stac_client(cdse)
cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                     collection="sentinel-1-grd", window_days=6,
                     max_items=300, instrument_mode="IW",
                     orbit_state=None, product_type=None, polarization=None)

def search_with_backoff(day: str, tries: int = 5):
    """CDSE STAC 은 연속 조회에 429(WAF rate limit)를 낸다. 지수 백오프로 재시도.

    여러 달을 한 번에 훑으면 반드시 걸린다(2026-08-17). 실패를 그냥 넘기면
    그 날짜 관측이 통째로 빠지므로, 마지막 시도까지 실패하면 예외를 올린다.
    """
    import time

    for attempt in range(tries):
        try:
            return list_s1_items_for_date(client, day, cfg)
        except Exception as e:  # noqa: BLE001
            if "429" not in str(e) and "Rate limit" not in str(e):
                raise
            wait = 30 * (2 ** attempt)          # 30s, 60s, 120s, 240s, 480s
            print(f"  [rate limit] {day} — {wait}초 후 재시도 "
                  f"({attempt + 1}/{tries})")
            time.sleep(wait)
    raise RuntimeError(f"{day}: rate limit 로 {tries}회 실패")


seen: dict[str, dict] = {}
for mon in MONTHS:
    y, m = int(mon[:4]), int(mon[4:])
    d = date(y, m, 1)
    while d.month == m:
        r = search_with_backoff(d.isoformat())
        if r.get("status") == "ok":
            for c in r.get("candidates", []):
                if str(c.get("datetime", ""))[:7].replace("-", "") == mon:
                    seen.setdefault(c["id"], c)
        d += timedelta(days=5)

todo = [c for c in seen.values() if key(c["id"]) not in skip]
todo.sort(key=lambda c: str(c.get("datetime", "")))
print(f"검색 {len(seen)}장 → 받을 것 **{len(todo)}장**\n")
for c in todo:
    print(f"  {str(c['datetime'])[:10]}  {str(c.get('orbit_state',''))[:4]}"
          f" r{c.get('relative_orbit','')}  ...{c['id'][-14:]}")
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
        print(f"[{i}/{len(todo)}] {f.stat().st_size/1e6:>5.0f} MB  {c['id'][-18:]}",
              flush=True)
        ok += 1
    except Exception as e:                              # noqa: BLE001
        print(f"[{i}/{len(todo)}] 실패 {c['id'][-18:]}: {e}", flush=True)
        err += 1
print(f"\n완료 {ok} · 실패 {err}")
print("다음: conda run -n s1_snappy python batch_grd_rtc_frost.py "
      "--pol VH --out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G")
