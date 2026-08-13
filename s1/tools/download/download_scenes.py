# -*- coding: utf-8 -*-
"""날짜·상대궤도·씬ID로 지정한 GRD만 받는다 (범용 소량 수집기).

`download_aug_pair.py`·`download_asc127_aug.py`는 특정 비교쌍에 맞춰 목록이
박혀 있다. 유역이 늘 때마다 스크립트를 새로 만들지 않도록 인자로 받는다.

씬 식별은 **끝 해시를 뺀 키**로 한다 — 같은 촬영인데 제품 생성 해시가 다르면
이미 받은 것을 신규로 센다.

실행:
    python download_scenes.py --date 2026-08-02 --orbit 54 --id 17B9 --dry-run
    python download_scenes.py --date 2026-08-02 --orbit 54 --id 17B9
"""
from __future__ import annotations

import argparse
import re
import time

from s1.core.config import CDSEConfig, OutputConfig, load_env
from s1.stac.client import open_cdse_stac_client
from s1.stac.download_s1 import choose_download_url, download_odata_cdse_with_retry
from s1.stac.models import S1SearchConfig
from s1.stac.search_s1 import list_s1_items_for_date

BBOX = [125.0, 32.8, 131.0, 39.5]
_KEY = re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    m = _KEY.search(name)
    return m.group(1) if m else name


def search(client, day: str, cfg, tries: int = 6):
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", action="append", required=True, help="YYYY-MM-DD")
    ap.add_argument("--orbit", type=int, help="상대궤도로 한정 (예: 54)")
    ap.add_argument("--id", action="append", default=[],
                    help="씬 ID 4자리. 여러 번 줄 수 있다. 없으면 날짜·궤도 전부")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env(".env")
    out = OutputConfig()
    dl = out.out_dir / "sentinel1_grd"
    dl.mkdir(parents=True, exist_ok=True)
    have = {key(p.name) for p in dl.iterdir()
            if p.suffix == ".zip" or p.name.endswith(".SAFE")}
    rtc = {key(p.name) for p in (out.out_dir / "rtc_grd_frost_vh").glob("*.tif")}
    skip = have | rtc
    want = {s.strip().upper() for s in args.id}

    client = open_cdse_stac_client(CDSEConfig())
    cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                         collection="sentinel-1-grd", window_days=1,
                         max_items=300, instrument_mode="IW",
                         orbit_state=None, product_type=None, polarization=None)

    found: dict[str, dict] = {}
    for d in args.date:
        r = search(client, d, cfg)
        if not r or r.get("status") != "ok":
            print(f"⚠ {d} 검색 실패")
            continue
        for c in r.get("candidates", []):
            if str(c.get("datetime", ""))[:10] != d:
                continue
            if args.orbit is not None and int(c.get("relative_orbit") or -1) != args.orbit:
                continue
            if want and not any(f"_{w}_" in c["id"].upper() for w in want):
                continue
            found[key(c["id"])] = c
        time.sleep(2)

    missing = want - {w for w in want
                      for c in found.values() if f"_{w}_" in c["id"].upper()}
    if missing:
        print(f"⚠ 아카이브에서 못 찾은 씬: {sorted(missing)}")

    todo = [c for k, c in found.items() if k not in skip]
    todo.sort(key=lambda c: str(c.get("datetime", "")))
    print(f"검색됨 {len(found)}장 · 이미 보유 {len(found) - len(todo)}장 → "
          f"받을 것 **{len(todo)}장**\n")
    for c in todo:
        print(f"  {str(c['datetime'])[:19]}  {str(c.get('platform', '')):<12}"
              f" r{c.get('relative_orbit', '')}  ...{c['id'][-14:]}")
    if args.dry_run:
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
            print(f"[{i}/{len(todo)}] {f.stat().st_size / 1e6:>5.0f} MB  "
                  f"{c['id'][-18:]}", flush=True)
            ok += 1
        except Exception as e:                              # noqa: BLE001
            print(f"[{i}/{len(todo)}] 실패 {c['id'][-18:]}: {e}", flush=True)
            err += 1
    print(f"\n완료 {ok} · 실패 {err}")


if __name__ == "__main__":
    main()
