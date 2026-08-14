# -*- coding: utf-8 -*-
"""연도·월별 **상대궤도 인벤토리** — 어느 해 어느 궤도가 한반도를 찍었나.

왜 필요한가
-----------
연도 간 수면적을 비교하려면 **같은 상대궤도**끼리 붙여야 한다. 궤도가 다르면
입사각·촬영기하가 달라 후방산란 dB 분포 자체가 달라지기 때문이다.

그런데 절대궤도 산술(차이가 175의 배수면 같은 상대궤도)은 **같은 위성 안에서만**
성립한다. S1A는 2026-06-29에 운용을 마쳤고 S1C·S1D가 그 자리를 이어받았으므로,
연도를 건너뛰는 비교는 위성이 바뀐다. 그래서 절대궤도 계산 대신 **STAC이 주는
`sat:relative_orbit`을 직접 읽어** 위성 간 짝을 확정한다.

이 스크립트는 원본을 내려받지 않는다. **메타데이터만 조회**하므로 로컬 디스크
용량과 무관하고 몇 분이면 끝난다.

무엇을 내나
-----------
1. 씬 단위 CSV — 날짜·위성·절대궤도·상대궤도·방향·한반도/남한/제주 겹침 비율
2. 요약 표 — (연도, 월) × 상대궤도 격자로 "몇 씬 찍혔나"
3. **상대궤도 ↔ 절대궤도 오프셋** — 위성별로
   `(절대궤도 − 상대궤도) mod 175`가 일정한지 확인해 오프셋을 확정한다.
   이게 나오면 파일명만 보고도 상대궤도를 계산할 수 있다.

실행:
    conda run -n s1_pipeline python -m s1.tools.audit.relative_orbit_survey \
        --years 2022 2023 2024 2025 2026 --months 7 8
    conda run -n s1_pipeline python -m s1.tools.audit.relative_orbit_survey \
        --years 2025 2026 --months 7 8 --collection sentinel-1-slc
"""

from __future__ import annotations

import argparse
import calendar
import csv
from collections import Counter, defaultdict
from pathlib import Path

from s1.core.config import CDSEConfig, load_env
from s1.core.paths import DATA_DIR, KOREA_PENINSULA, PROJECT_DIR, SOUTH_KOREA, rel
from s1.footprint import load_boundary_union
from s1.stac.client import open_cdse_stac_client

REPEAT_ORBITS = 175  # Sentinel-1 반복주기: 175궤도 = 12일

# 제주 폴리곤은 따로 파일이 없어 Korea_Peninsula 링에서 이 상자로 골라낸다.
JEJU_BBOX = (126.10, 33.10, 126.99, 33.60)  # w, s, e, n


def jeju_union():
    """Korea_Peninsula에서 제주 본섬 링만 추려 하나로 합친다."""
    import json

    from shapely.geometry import shape
    from shapely.ops import unary_union

    data = json.loads(Path(KOREA_PENINSULA).read_text(encoding="utf-8"))
    geoms = ([f["geometry"] for f in data["features"]]
             if data.get("type") == "FeatureCollection" else [data])
    w, s, e, n = JEJU_BBOX
    picked = []
    for g in geoms:
        polys = ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"])
        for poly in polys:
            p = shape({"type": "Polygon", "coordinates": poly})
            c = p.centroid
            if w <= c.x <= e and s <= c.y <= n:
                picked.append(p)
    return unary_union(picked) if picked else None


def overlap(geom: dict, boundary) -> float:
    """footprint 면적 대비 경계와의 교집합 비율(%).

    s1.footprint.footprint_overlap_ratio 는 경계를 파일 경로로 받는데, 제주는
    별도 파일이 없어 shapely 객체로만 존재한다. 세 경계(한반도·남한·제주)를
    같은 방식으로 다루려고 여기서 shapely 객체를 직접 받는다.
    """
    from shapely.geometry import shape

    if not geom or boundary is None:
        return 0.0
    fp = shape(geom)
    if fp.area == 0:
        return 0.0
    return float(fp.intersection(boundary).area / fp.area) * 100


def month_range(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01T00:00:00Z/{year}-{month:02d}-{last}T23:59:59Z"


def main() -> None:
    ap = argparse.ArgumentParser(description="연도·월별 상대궤도 인벤토리 (STAC 메타데이터만)")
    ap.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--months", type=int, nargs="+", default=[7, 8])
    ap.add_argument("--collection", default="sentinel-1-grd",
                    help="sentinel-1-grd (기본) / sentinel-1-slc")
    ap.add_argument("--limit", type=int, default=2000, help="월별 최대 조회 수")
    ap.add_argument("--out", type=Path, default=None,
                    help="CSV 경로 (기본 data/relative_orbits_<collection>.csv)")
    args = ap.parse_args()

    load_env(PROJECT_DIR / ".env")
    client = open_cdse_stac_client(CDSEConfig())

    kp = load_boundary_union(KOREA_PENINSULA)
    sk = load_boundary_union(SOUTH_KOREA)
    jeju = jeju_union()

    out_csv = args.out or DATA_DIR / f"relative_orbits_{args.collection}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    grid: dict[tuple[int, int], Counter] = defaultdict(Counter)
    offsets: dict[str, Counter] = defaultdict(Counter)

    for year in args.years:
        for month in args.months:
            # 검색은 **bbox**로 한다. Korea_Peninsula는 꼭짓점 9,711개짜리
            # MultiPolygon이라 intersects로 넘기면 URL이 감당 못 해 서버가
            # JSON이 아닌 오류 페이지를 돌려준다(JSONDecodeError). 느슨한 상자로
            # 받아온 뒤 아래에서 footprint 겹침으로 정확히 거른다.
            search = client.search(
                collections=[args.collection],
                datetime=month_range(year, month),
                query={"sar:instrument_mode": {"eq": "IW"}},
                bbox=list(kp.bounds),
                limit=100,
            )
            n = 0
            for it in search.items():
                n += 1
                if n > args.limit:
                    break
                p = it.properties
                geom = it.geometry
                rel_orb = p.get("sat:relative_orbit") or p.get("relativeOrbitNumber")
                abs_orb = p.get("sat:absolute_orbit") or p.get("orbitNumber")
                platform = (p.get("platform") or "").upper()
                kp_pct = overlap(geom, kp)
                if kp_pct <= 0:
                    continue  # 한반도 미교차(중국/일본/공해)
                sk_pct = overlap(geom, sk)
                jeju_pct = overlap(geom, jeju)
                rows.append({
                    "date": (p.get("datetime") or "")[:10],
                    "platform": platform,
                    "abs_orbit": abs_orb,
                    "rel_orbit": rel_orb,
                    "orbit_state": p.get("sat:orbit_state"),
                    "kp_pct": round(kp_pct, 1),
                    "sk_pct": round(sk_pct, 1),
                    "jeju_pct": round(jeju_pct, 1),
                    "id": it.id,
                })
                if rel_orb is not None:
                    grid[(year, month)][rel_orb] += 1
                if rel_orb is not None and abs_orb is not None and platform:
                    offsets[platform][(int(abs_orb) - int(rel_orb)) % REPEAT_ORBITS] += 1
            print(f"{year}-{month:02d}: {n}건 조회 → 한반도 교차 "
                  f"{sum(1 for r in rows if r['date'].startswith(f'{year}-{month:02d}'))}건")

    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["date", "platform", "abs_orbit", "rel_orbit", "orbit_state",
                            "kp_pct", "sk_pct", "jeju_pct", "id"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV: {rel(out_csv)}  ({len(rows)}행)")

    # --- 요약 1: (연도, 월) × 상대궤도 ---------------------------------------
    all_orbits = sorted({o for c in grid.values() for o in c})
    print("\n[상대궤도별 씬 수]  행=연도-월, 열=상대궤도")
    print("        " + " ".join(f"{o:>4}" for o in all_orbits))
    for key in sorted(grid):
        y, m = key
        print(f"{y}-{m:02d} " + " ".join(f"{grid[key].get(o, 0):>4}" for o in all_orbits))

    # --- 요약 2: 남한/제주를 찍은 상대궤도 -----------------------------------
    sk_orbits = defaultdict(set)
    jeju_orbits = defaultdict(set)
    for r in rows:
        if r["rel_orbit"] is None:
            continue
        if r["sk_pct"] > 0:
            sk_orbits[r["date"][:7]].add((r["rel_orbit"], r["platform"]))
        if r["jeju_pct"] > 0:
            jeju_orbits[r["date"][:7]].add((r["rel_orbit"], r["platform"]))
    print("\n[남한을 찍은 상대궤도]")
    for ym in sorted(sk_orbits):
        print(f"  {ym}: " + ", ".join(f"{o}({p})" for o, p in sorted(sk_orbits[ym])))
    print("\n[제주를 찍은 상대궤도]")
    for ym in sorted(jeju_orbits):
        print(f"  {ym}: " + ", ".join(f"{o}({p})" for o, p in sorted(jeju_orbits[ym])))

    # --- 요약 3: 위성별 절대궤도 ↔ 상대궤도 오프셋 ---------------------------
    print("\n[위성별 오프셋]  rel = ((abs - offset) mod 175) + 1  형태로 쓰려면 offset+1")
    for plat in sorted(offsets):
        c = offsets[plat]
        top, cnt = c.most_common(1)[0]
        total = sum(c.values())
        flag = "일정" if cnt == total else f"불일치 {total - cnt}건"
        print(f"  {plat:6s} (abs - rel) mod 175 = {top:>3}  [{cnt}/{total} {flag}]")


if __name__ == "__main__":
    main()
