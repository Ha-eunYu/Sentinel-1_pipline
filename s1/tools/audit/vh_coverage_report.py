# -*- coding: utf-8 -*-
"""VH external DEM RTC 커버리지 보고 — CDSE 관측 목록 대비 로컬 보유·처리 현황.

무엇을 답하나
-------------
"어느 시기의 어느 관측이 아직 VH ext-DEM RTC 가 안 됐고, 그중 원본이 로컬에
있는 것은 무엇이고 받아야 하는 것은 무엇인가."

⚠ 대조 키 (ISSUES_KR #16)
-------------------------
씬 ID 끝 4hex 는 **제품 생성 해시**다. 같은 촬영이라도 CDSE 재생성본이나 다른
제품이면 값이 달라, 이걸로 대조하면 **같은 촬영을 다른 씬으로 센다**. 실제로
"2025-07 남한 VH완료 0 / 원본없음 16"이라는 정반대 결과가 나온 적이 있다
(실제로는 16씬 전부 처리 완료).

그래서 키는 **관측 시작시각 + 절대궤도**로 잡는다. 같은 촬영이면 항상 같다.

입력
----
`data/relative_orbits_sentinel-1-grd.csv` — relative_orbit_survey.py 산출물.
없으면 먼저 그걸 돌린다.

실행:
    conda run -n s1_snappy python -m s1.tools.audit.vh_coverage_report
    conda run -n s1_snappy python -m s1.tools.audit.vh_coverage_report --zone kp
    conda run -n s1_snappy python -m s1.tools.audit.vh_coverage_report --months 2025-07 2026-07 --list
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from s1.core.paths import DATA_DIR, GRD_DIR, RTC_FROST_VH_DIR, rel

# 관측 시작시각 + 절대궤도 (씬 ID 해시를 쓰지 않는다 — ISSUES #16)
KEY_RE = re.compile(r"_(\d{8}T\d{6})_\d{8}T\d{6}_(\d{6})_")

ZONES = {
    "kp": ("한반도", lambda r: float(r["kp_pct"]) > 0),
    "sk": ("남한", lambda r: float(r["sk_pct"]) > 0),
    "nk": ("북한·해상", lambda r: float(r["sk_pct"]) <= 0),
}

# NAS 보유분. 로컬에 없다고 다 받으면 안 된다 — 이미 NAS 에 있는 것이 많다.
# (2026-08-17 확인: 22-08·23-07·24-07 자료도 NAS 에 있다)
NAS_ROOTS = [
    r"X:\02_Analysis\20220906_Typhoon hinnamnor_International Charter",
    r"X:\02_Analysis\20230714_Flood_Korea",
    r"X:\02_Analysis\20240717_Flood_Korea",
    r"X:\02_Analysis\20250717_Flood",
    r"X:\02_Analysis\20250725_Namgang",
    r"X:\02_Analysis\20260708_Flood",
]


def key_of(name: str) -> tuple[str, str] | None:
    m = KEY_RE.search(name)
    return (m.group(1), m.group(2)) if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description="VH ext-DEM RTC 커버리지 보고")
    ap.add_argument("--csv", type=Path,
                    default=DATA_DIR / "relative_orbits_sentinel-1-grd.csv")
    ap.add_argument("--zone", choices=list(ZONES), default="kp",
                    help="집계 범위 (기본 kp=한반도 전체)")
    ap.add_argument("--months", nargs="*", default=None,
                    help="YYYY-MM 목록으로 제한 (예: 2025-07 2026-07)")
    ap.add_argument("--list", action="store_true",
                    help="미처리 관측을 날짜/상대궤도까지 나열")
    ap.add_argument("--no-nas", action="store_true",
                    help="NAS 보유분을 세지 않는다(로컬만 볼 때)")
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(
            f"{rel(args.csv)} 가 없습니다. 먼저 relative_orbit_survey.py 를 돌리세요.")

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig")))
    zips = {k for z in GRD_DIR.glob("*.zip") if (k := key_of(z.name))}
    vh = {k for t in RTC_FROST_VH_DIR.glob("*_vh.tif") if (k := key_of(t.name))}

    nas: set[tuple[str, str]] = set()
    if not args.no_nas:
        for root in NAS_ROOTS:
            p = Path(root)
            if not p.exists():
                print(f"  (NAS 경로 없음: {root})")
                continue
            for f in p.rglob("S1*_IW_GRDH*"):
                k = key_of(f.name)
                if k:
                    nas.add(k)

    zone_name, zone_ok = ZONES[args.zone]
    print(f"기준 {zone_name} · 로컬 원본 {len(zips)}건 · VH 산출물 {len(vh)}건 · "
          f"NAS {len(nas)}건\n")

    stat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    detail: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        k = key_of(r["id"])
        if not k or not zone_ok(r):
            continue
        ym = r["date"][:7]
        if args.months and ym not in args.months:
            continue
        if k in vh:
            state = "VH완료"
        elif k in zips:
            state = "로컬·미처리"
        elif k in nas:
            state = "NAS보유"      # 받을 필요 없다. 복사해 오면 된다
        else:
            state = "받아야함"
        stat[ym][state] += 1
        if state != "VH완료":
            detail[(ym, state)].append(
                f"{r['date'][5:]}/rel{r['rel_orbit']}/{r['platform'][-2:]}")

    cols = ("VH완료", "로컬·미처리", "NAS보유", "받아야함")
    print(f"{'연월':>8} {'VH완료':>7} {'로컬·미처리':>12} {'NAS보유':>8} {'받아야함':>9} {'계':>5}")
    tot = defaultdict(int)
    for ym in sorted(stat):
        d = stat[ym]
        vals = [d[c] for c in cols]
        for c, v in zip(cols, vals):
            tot[c] += v
        print(f"{ym:>8} {vals[0]:>7} {vals[1]:>12} {vals[2]:>8} {vals[3]:>9} "
              f"{sum(vals):>5}")
    print(f"{'합계':>8} {tot['VH완료']:>7} {tot['로컬·미처리']:>12} "
          f"{tot['NAS보유']:>8} {tot['받아야함']:>9} {sum(tot.values()):>5}")

    if args.list:
        print("\n=== 미처리 상세 ===")
        for (ym, state), items in sorted(detail.items()):
            uniq = sorted(set(items))
            print(f"  {ym} {state:>8} {len(items):>3}건")
            for i in range(0, len(uniq), 6):
                print("      " + "  ".join(uniq[i:i + 6]))


if __name__ == "__main__":
    main()
