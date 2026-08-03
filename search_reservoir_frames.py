# -*- coding: utf-8 -*-
"""저수지 시계열의 빈칸을 채울 **부족 프레임**을 찾는다.

왜
--
19개 댐 × 18개 날짜 = 342칸 중 196칸이 비어 있는데, 그중 195칸이 커버리지
**정확히 0%**다. 로컬 미처리 granule로는 한 칸도 못 채운다
(`gee/Korea_WaterDetection_2025_2026/reservoir_gap_audit.py` 실측).

원인은 **그 패스의 프레임을 안 받은 것**이다. Sentinel-1 IW 한 패스가 한반도를
덮으려면 프레임 3~4장이 필요한데 여러 날짜가 1~2장뿐이다.

    2025-07-12·07-13·07-17·07-19·07-29   각 1장
    2026-07-26·07-31                     각 1장

무엇을 하나
-----------
CDSE STAC에서 그 날짜들의 GRD를 훑어, **로컬에 없으면서 어느 댐을 덮는** 프레임만
추린다. 날짜는 `reservoir_series.ORBIT`에 있는 18개로 한정한다 — 모자이크가 있는
날짜라야 시계열에 들어간다.

⚠ 선별은 STAC `bbox`로 한다
    bbox는 실제 footprint보다 넓다. 그래서 여기 나온 것이 전부 실제로 댐을
    덮지는 않는다(과다 선별). 받은 뒤 KML footprint로 다시 걸러야 한다 —
    `search_korea_missing.py` 주석의 실측 참고(bbox로 8장, footprint로 2장).

    반대 방향 오류(덮는데 빠뜨림)는 없으므로 다운로드 목록으로는 안전하다.

⚠ 환경이 둘로 나뉜다
    STAC 검색은 `s1_pipeline`에서 도는데 거기엔 `pyogrio`가 없다. 그래서 댐
    좌표는 `sar-gee`에서 미리 뽑아 `reservoir_points.json`에 넣어 두고, 이
    스크립트는 그 파일만 읽는다.

실행
----
    conda run -n sar-gee python export_reservoir_points.py      # 좌표 먼저
    conda run -n s1_pipeline python search_reservoir_frames.py
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from config import CDSEConfig, OutputConfig, load_env
from stac.client import open_cdse_stac_client
from stac.models import S1SearchConfig
from stac.search_s1 import list_s1_items_for_date

BBOX = [125.0, 33.0, 130.0, 38.5]
_KEY = re.compile(
    r"(S1[A-D]_[A-Z]{2}_[A-Z]{4}_\w{4}_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_\w{6})")


def key(name: str) -> str:
    """씬 식별 키 — 끝 해시를 뺀다(제품 생성 해시가 로컬/STAC 간 다르다)."""
    m = _KEY.search(name)
    return m.group(1) if m else name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", nargs="+", default=None,
                    help="생략하면 points 파일에 든 저수지 전부")
    ap.add_argument("--points", type=Path,
                    default=Path("reservoir_points.json"))
    ap.add_argument("--csv", type=Path, default=Path("reservoir_frames.csv"))
    args = ap.parse_args()

    if not args.points.exists():
        raise SystemExit(
            f"{args.points} 없음 — 먼저 실행:\n"
            f"    conda run -n sar-gee python export_reservoir_points.py")
    raw = json.loads(args.points.read_text(encoding="utf-8"))
    lakes, ORBIT = raw["lakes"], raw["orbit"]
    pts = {n: (v["lon"], v["lat"]) for n, v in lakes.items()
           if args.lake is None or n in args.lake}

    load_env(".env")
    out = OutputConfig()
    dl = out.out_dir / "sentinel1_grd"
    have = {key(p.name) for p in dl.iterdir()
            if p.suffix == ".zip" or p.name.endswith(".SAFE")}
    print(f"댐 {len(pts)}곳 · 로컬 GRD {len(have)}장 · 대상 날짜 {len(ORBIT)}개\n")

    client = open_cdse_stac_client(CDSEConfig())
    cfg = S1SearchConfig(bbox=BBOX, intersects_geojson=None,
                         collection="sentinel-1-grd", window_days=1,
                         max_items=300, instrument_mode="IW",
                         orbit_state=None, product_type=None, polarization=None)

    rows = []
    for d in sorted(ORBIT):
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        res = list_s1_items_for_date(client, iso, cfg)
        if res.get("status") != "ok":
            print(f"{iso}  검색 실패: {res.get('status')}")
            continue
        new = 0
        for c in res.get("candidates", []):
            if str(c.get("datetime", ""))[:10] != iso:
                continue
            if key(c["id"]) in have:
                continue
            b = c.get("bbox")
            if not b:
                continue
            hit = [n for n, (x, y) in pts.items()
                   if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
            if hit:
                rows.append((d, ORBIT[d][0], c["id"], sorted(hit)))
                new += 1
        print(f"{iso}  {ORBIT[d][0]:<8} 신규 후보 {new}장")

    print(f"\n**받을 프레임 {len(rows)}장**\n")
    print(f"{'날짜':<10}{'궤도':<9}{'덮는 댐':<34}씬")
    print("-" * 92)
    for d, orb, cid, hit in rows:
        print(f"{d:<10}{orb:<9}{','.join(hit):<34}...{cid[-18:]}")

    fills = {(n, d) for d, _, _, hit in rows for n in hit}
    print(f"\n채울 수 있는 칸 **{len(fills)}개**  (현재 빈칸 196개)")

    if rows:
        args.csv.write_text("", encoding="utf-8")
        with args.csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "orbit", "scene_id", "lakes"])
            for d, orb, cid, hit in rows:
                w.writerow([d, orb, cid, " ".join(hit)])
        print(f"\nCSV → {args.csv}")
    print("\n  * bbox 기준이라 과다 선별이다 — 받은 뒤 KML footprint 로 거를 것")


if __name__ == "__main__":
    main()
