# -*- coding: utf-8 -*-
"""지정한 달의 **남한 촬영** Sentinel-1 GRD 중 아직 없는 것을 받는다.

`download_korea_missing.py`와 다른 점
------------------------------------
그쪽 필터는 `Korea_Peninsula.geojson`(남북 전체)이라 **북한 전용 프레임까지
받는다.** 남한 가뭄·수체 분석만 할 거면 그건 낭비다. 여기서는 남한만 남긴다.

남한 경계로 무엇을 쓰나 — **대권역 shp**
---------------------------------------
`geojson/South_Korea.geojson`은 쓰면 안 된다. 실측 확인 결과 이 폴리곤은
**부산·강릉·여수·해남·완도·제주를 전부 제외**하는 거친 내륙 덩어리다
(bounds 34.69~38.84°N). 이걸로 판정하면 남해안·제주를 찍은 프레임을 통째로
놓친다.

`Korea_Peninsula.geojson` − `NK.geojson`도 안 된다. NK 폴리곤이 북한을 다 덮지
못해(신의주가 차집합에 남는다) 북한 프레임이 새어 들어온다.

그래서 **`gee/대권역/WKMBBSN.shp`(21개 대권역, 제주도 포함, 33.20~39.19°N)**를
쓴다. 국가 표준 유역경계라 남한 영토를 정확히 덮고, 하류 분석(gee 쪽
`watershed_pairs.py`)이 쓰는 것과 **같은 폴리곤**이라 기준이 어긋나지 않는다.

제외 규칙 (`download_korea_missing.py`와 동일)
  · 로컬 `downloads/sentinel1_grd`에 이미 있는 것(.zip / .SAFE)
  · VH RTC를 이미 돌린 것 (`downloads/rtc_grd_frost_vh/*.tif`)
  · NAS `X:\02_Analysis\20260708_Flood`에 있는 것
씬 식별 키는 **끝 해시를 뺀 촬영 단위** — 같은 촬영인데 제품 생성 해시가
다르면 보유분을 통째로 신규로 센다.

실행:
    conda run -n sar-gee python download_south_korea_month.py --dry-run 202508 202608
    conda run -n sar-gee python download_south_korea_month.py 202508 202608
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pyogrio
from shapely.geometry import shape

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.download_s1 import choose_download_url, download_odata_cdse_with_retry
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date

BBOX = [125.0, 32.8, 131.0, 39.5]          # 검색용 느슨한 사각형(제주 포함)
BASINS = Path(r"F:\06_SAR_system\gee\대권역\WKMBBSN.shp")
NAS = Path(r"X:\02_Analysis\20260708_Flood")

_KEY = re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    """씬 식별 키 — 끝 해시를 뺀 촬영 단위."""
    m = _KEY.search(name)
    return m.group(1) if m else name


def search_with_backoff(client, day: str, cfg, tries: int = 6) -> dict:
    """CDSE STAC은 429(WAF Rate limit)를 잘 뱉는다 — 지수 백오프로 다시 묻는다."""
    delay = 20.0
    for i in range(1, tries + 1):
        try:
            return list_s1_items_for_date(client, day, cfg)
        except Exception as e:                              # noqa: BLE001
            if "429" not in str(e) and "Rate limit" not in str(e):
                raise
            if i == tries:
                raise
            print(f"    · 429 rate limit — {delay:.0f}초 쉬고 재시도 ({i}/{tries})",
                  flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 300)
    raise RuntimeError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("months", nargs="*", default=["202508", "202608"],
                    help="YYYYMM (기본 202508 202608)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-cover", type=float, default=0.0,
                    help="남한 교집합 면적비 하한(%%). 기본 0 = 조금이라도 걸치면 받는다")
    args = ap.parse_args()
    months = args.months or ["202508", "202608"]

    load_env(".env")
    cdse = CDSEConfig()
    out = OutputConfig()
    dl = out.out_dir / "sentinel1_grd"
    dl.mkdir(parents=True, exist_ok=True)

    sk = pyogrio.read_dataframe(BASINS).to_crs(4326).geometry.union_all()
    print(f"남한 경계: 대권역 21개 union  bounds="
          f"{tuple(round(v, 2) for v in sk.bounds)}")

    have = {key(p.name) for p in dl.iterdir()
            if p.suffix == ".zip" or p.name.endswith(".SAFE")}
    rtc = {key(p.name) for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}
    nas: set[str] = set()
    if NAS.exists():
        for pat in ("*.zip", "*.SAFE", "*.tif"):
            nas |= {key(p.name) for p in NAS.rglob(pat)}
    skip = have | rtc | nas
    print(f"제외 대상 {len(skip)}건 (로컬 {len(have)} · VH RTC {len(rtc)} · NAS {len(nas)})")

    client = open_cdse_stac_client(cdse)
    cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                         collection="sentinel-1-grd", window_days=6,
                         max_items=300, instrument_mode="IW",
                         orbit_state=None, product_type=None, polarization=None)

    seen: dict[str, dict] = {}
    for mon in months:
        y, m = int(mon[:4]), int(mon[4:])
        d = date(y, m, 1)
        print(f"\n■ {mon} 검색")
        while d.month == m:
            r = search_with_backoff(client, d.isoformat(), cfg)
            if r.get("status") == "ok":
                for c in r.get("candidates", []):
                    if str(c.get("datetime", ""))[:7].replace("-", "") == mon:
                        seen.setdefault(c["id"], c)
            d += timedelta(days=5)
            time.sleep(2)                    # WAF를 자극하지 않는 최소 간격

    # 남한 교집합 — bbox가 아니라 item.geometry(실제 footprint)로 판정
    south: list[tuple[float, dict]] = []
    for c in seen.values():
        geom = c.get("geometry")
        if not geom:
            continue
        fp = shape(geom)
        pct = fp.intersection(sk).area / fp.area * 100 if fp.area else 0.0
        if pct > args.min_cover:
            south.append((pct, c))

    todo = [(p, c) for p, c in south if key(c["id"]) not in skip]
    todo.sort(key=lambda pc: str(pc[1].get("datetime", "")))
    print(f"\n검색 {len(seen)}장 → 남한 걸침 {len(south)}장 → "
          f"받을 것 **{len(todo)}장**\n")
    for p, c in todo:
        print(f"  {str(c['datetime'])[:10]}  {str(c.get('orbit_state', ''))[:4]}"
              f" r{str(c.get('relative_orbit', '')):<3} 남한{p:6.1f}%  "
              f"...{c['id'][-14:]}")
    if args.dry_run:
        raise SystemExit("\n--dry-run: 받지 않았습니다.")

    print()
    ok = err = 0
    for i, (_, c) in enumerate(todo, 1):
        f = dl / f"{c['id']}.zip"
        if f.exists():
            continue
        try:
            url = choose_download_url(zipper_url=c.get("zipper_url"),
                                      product_href=c.get("product_href"),
                                      allow_fallback=False)
            download_odata_cdse_with_retry(url, f)
            print(f"[{i}/{len(todo)}] {f.stat().st_size / 1e6:>5.0f} MB  "
                  f"{c['id'][-18:]}", flush=True)
            ok += 1
        except Exception as e:                              # noqa: BLE001
            print(f"[{i}/{len(todo)}] 실패 {c['id'][-18:]}: {e}", flush=True)
            err += 1
    print(f"\n완료 {ok} · 실패 {err}")
    print("다음: batch_grd_rtc_frost.py --month <YYYYMM> --pol VH "
          "--out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G")


if __name__ == "__main__":
    main()
