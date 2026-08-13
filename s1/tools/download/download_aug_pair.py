# -*- coding: utf-8 -*-
"""8월 가뭄 비교쌍(ASC54 2025-08-06 ↔ 2026-08-02) GRD 5장만 골라 받는다.

왜 이것만인가
------------
8개 댐 유역 가뭄 분석에서 광학은 2025-08 ↔ 2026-08인데 SAR만 7월이었다.
두 해 공통 상대궤도는 **ASC54 하나뿐**이고(2025의 ASC127·DESC134는 2026 짝이
없고, 2026의 DESC32는 2025 짝이 없다), 궤도를 섞으면 커버 영역이 달라져
면적 비교가 성립하지 않는다. 2025는 08-06/12/24 중 광학(08-01)과 가장 가까운
**08-06**(5일 차)을 쓴다.

⚠ 위성이 다르다 — 2025-08-06은 S1C, 2026-08-02는 S1D. 8월에는 같은 위성
   조합이 없다(2025의 S1A 날짜와 짝지으면 S1A↔S1D로 더 나빠진다).
   산출 후 두 해 임계값이 1.5 dB 넘게 벌어지면 보고서에 단서를 달 것.

⚠ ASC54 스와스가 **섬진강·평림을 전혀 안 지난다**(교차 0%). 8월 SAR은
   안동·임하·밀양·영천·성덕·운문 6개 유역만 가능하다.

씬 식별은 `download_korea_missing.py`와 같이 **끝 해시를 뺀 키**로 한다
(같은 촬영인데 제품 생성 해시가 다를 수 있다).

실행:
    conda run -n s1_pipeline python download_aug_pair.py --dry-run
    conda run -n s1_pipeline python download_aug_pair.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from s1.core.config import CDSEConfig, OutputConfig, load_env
from s1.stac.client import open_cdse_stac_client
from s1.stac.download_s1 import choose_download_url, download_odata_cdse_with_retry
from s1.stac.models import S1SearchConfig
from s1.stac.search_s1 import list_s1_items_for_date

# 받을 5장 (사전 조사 2026-08-07, CDSE STAC 검색 결과)
WANTED = [
    "S1C_IW_GRDH_1SDV_20250806T092202_20250806T092231_003550_0071C5_D0A4_COG",
    "S1C_IW_GRDH_1SDV_20250806T092231_20250806T092256_003550_0071C5_E160_COG",
    "S1C_IW_GRDH_1SDV_20250806T092256_20250806T092321_003550_0071C5_3EEB_COG",
    "S1D_IW_GRDH_1SDV_20260802T092231_20260802T092300_003945_00725D_3B05_COG",
    "S1D_IW_GRDH_1SDV_20260802T092300_20260802T092325_003945_00725D_B10F_COG",
]
DATES = ["2025-08-06", "2026-08-02"]
BBOX = [125.0, 33.0, 130.0, 38.5]

_KEY = re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    """씬 식별 키 — 끝 해시를 뺀 촬영 단위."""
    m = _KEY.search(name)
    return m.group(1) if m else name


DRY = "--dry-run" in sys.argv

load_env(".env")
cdse = CDSEConfig()
out = OutputConfig()
dl = out.out_dir / "sentinel1_grd"
dl.mkdir(parents=True, exist_ok=True)

want = {key(w): w for w in WANTED}
have = {key(p.name) for p in dl.iterdir()
        if p.suffix == ".zip" or p.name.endswith(".SAFE")}
rtc = {key(p.name) for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}
skip = have | rtc

client = open_cdse_stac_client(cdse)
# window_days=1: 지정일 하루만 보면 되므로 검색을 좁게 잡는다.
cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                     collection="sentinel-1-grd", window_days=1,
                     max_items=300, instrument_mode="IW",
                     orbit_state=None, product_type=None, polarization=None)

found: dict[str, dict] = {}
for d in DATES:
    r = list_s1_items_for_date(client, d, cfg)
    if r.get("status") != "ok":
        print(f"⚠ {d} 검색 실패: {r}")
        continue
    for c in r.get("candidates", []):
        k = key(c["id"])
        if k in want:
            found.setdefault(k, c)

missing = [want[k] for k in want if k not in found]
if missing:
    print(f"⚠ **아카이브에서 못 찾은 씬 {len(missing)}장** — 이름을 확인할 것")
    for m in missing:
        print(f"    {m}")

todo = [c for k, c in found.items() if k not in skip]
todo.sort(key=lambda c: str(c.get("datetime", "")))
print(f"\n대상 {len(WANTED)}장 · 검색됨 {len(found)}장 · 이미 보유 "
      f"{len(found) - len(todo)}장 → 받을 것 **{len(todo)}장**\n")
for c in todo:
    print(f"  {str(c['datetime'])[:10]}  {str(c.get('orbit_state', ''))[:4]}"
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
    except Exception as e:                              # noqa: BLE001
        print(f"[{i}/{len(todo)}] 실패 {c['id'][-18:]}: {e}", flush=True)
        err += 1
print(f"\n완료 {ok} · 실패 {err}")
print("다음: conda run -n s1_snappy python batch_grd_rtc_frost.py --month 202508 "
      "--pol VH --out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G")
