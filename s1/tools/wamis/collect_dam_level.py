# -*- coding: utf-8 -*-
"""댐 **저수위·저수량**을 WAMIS 에서 받아 CSV 로 떨군다.

왜 이걸 받나
------------
SAR 은 **수면적**밖에 못 잰다. 가뭄 보고가 원하는 **저수량**은 면적에서 유도할 수
없고(형상에 따라 −30% 면적이 −30~−52% 부피가 된다), 그래서 규칙이
*"공표된 공식 저수율이 있으면 그걸 쓴다"* 이다 —
docs/drought/AREA_VS_VOLUME_KR.md §5-1. **이 도구가 그 "공식 값"을 가져온다.**

세 가지 모드
------------
=========== ================= =============================================
--mode       받는 것            쓰는 곳
=========== ================= =============================================
``daily``    일자료             저수위 추세·유입/방류. **저수량 없음.** 기본값
``storage``  시자료 -> 일 1행    **저수율(%)** 일별 시계열 — SAR 면적과 대조용
``hourly``   시자료 원본         호우 사상의 시간 해상도가 필요할 때
=========== ================= =============================================

⚠ **저수량·저수율은 시자료에만 있다.** ``daily`` 로는 아무리 받아도 안 나온다.
대신 ``storage`` 는 하루에 청크를 여러 번 도니 훨씬 느리다.

실행
----
    # 무엇이 있나 (전국 79곳, 캐시도 남긴다)
    python -m s1.tools.wamis.collect_dam_level --list

    # 가뭄 산출이 보는 담수호 21곳의 저수율, 최근 1년
    python -m s1.tools.wamis.collect_dam_level --preset reservoirs --mode storage

    # 이름·코드 직접 지정
    python -m s1.tools.wamis.collect_dam_level --dams 소양호,안동호,3008110 \
        --start 20250101 --end 20260908

산출은 ``downloads/wamis/`` 아래 **긴 형식(long) CSV** 한 장이다 — 댐마다 파일을
쪼개면 합치는 코드를 매번 다시 쓰게 된다.

⚠ 이름을 못 찾으면 **받기 전에 멈춘다.** WAMIS 는 없는 댐코드에도 "자료 없음"
으로 답해서, 오타를 그냥 두면 조용히 빈 CSV 가 나오기 때문이다.

자세한 설명은 docs/water/WAMIS_DAM_LEVEL_KR.md.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from s1.core.paths import WAMIS_DAM_LIST_CSV, WAMIS_DIR, rel        # noqa: E402
from s1.wamis import dams as damlib                                 # noqa: E402
from s1.wamis import series                                         # noqa: E402

MODES = ("daily", "storage", "hourly")


def _preset_names(preset: str) -> list[str] | None:
    """프리셋 이름 목록. ``all`` 은 목록 전체를 쓰므로 여기서는 ``None``."""
    if preset == "kwater":
        return damlib.load_kwater_points()
    if preset == "reservoirs":
        return damlib.load_reservoir_points()
    return None                                    # all


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # 열 순서는 첫 줄 기준. 뒤 줄에만 있는 열도 빠뜨리지 않는다.
    cols = list(rows[0])
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def cmd_list() -> int:
    found = damlib.fetch_dams()
    idx = damlib.build_index(found)

    # 이 저장소의 이름들이 어디로 붙는지 같이 보여준다 — 별칭표를 손보는 근거가 된다.
    tagged: dict[str, list[str]] = {}
    for src, names in (("kwater", damlib.load_kwater_points()),
                       ("호수", damlib.load_reservoir_points())):
        for n in names:
            d = damlib.resolve(n, idx)
            if d:
                tagged.setdefault(d.damcd, []).append(f"{src}:{n}")

    print(f"WAMIS 댐·보 {len(found)}곳")
    for d in found:
        who = " ".join(tagged.get(d.damcd, []))
        print(f"  {d.damcd}  {d.damnm:12s} {str(d.bbsnnm or '-'):8s} "
              f"{str(d.mggvnm or '-'):10s} {who}")

    _write_csv(Path(WAMIS_DAM_LIST_CSV),
               [{"damcd": d.damcd, "damnm": d.damnm, "bbsnnm": d.bbsnnm,
                 "sbsncd": d.sbsncd, "mggvnm": d.mggvnm} for d in found])
    print(f"\n캐시: {rel(WAMIS_DAM_LIST_CSV)}")
    return 0


def _resolve_targets(args) -> list[damlib.Dam] | None:
    """요청된 이름들을 Dam 목록으로. 하나라도 못 찾으면 ``None`` (=중단)."""
    found = damlib.fetch_dams()
    idx = damlib.build_index(found)

    if args.dams:
        names = [n.strip() for n in args.dams.split(",") if n.strip()]
    else:
        names = _preset_names(args.preset)

    if names is None:                              # --preset all
        return found

    targets: list[damlib.Dam] = []
    missing: list[str] = []
    seen: set[str] = set()
    for n in names:
        d = damlib.resolve(n, idx)
        if d is None:
            missing.append(n)
        elif d.damcd not in seen:
            seen.add(d.damcd)
            targets.append(d)
            print(f"  {n:12s} -> {d.label}")

    if missing:
        print(f"\n[중단] 이름 {len(missing)}개를 WAMIS 댐 목록에서 못 찾았다: "
              f"{', '.join(missing)}", file=sys.stderr)
        print("       --list 로 실제 이름을 확인하고, 규칙으로 안 되는 이름은 "
              "s1/wamis/dams.py 의 별칭표에 추가한다.", file=sys.stderr)
        return None
    return targets


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="WAMIS 댐 저수위·저수량 수집기",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="전국 댐·보 목록만 찍고 끝")
    p.add_argument("--preset", choices=("all", "kwater", "reservoirs"),
                   default="reservoirs",
                   help="대상 묶음 (기본 reservoirs = reservoir_points.json 21곳)")
    p.add_argument("--dams", help="쉼표로 구분한 이름 또는 댐코드 (--preset 무시)")
    p.add_argument("--mode", choices=MODES, default="daily")
    p.add_argument("--start", help="YYYYMMDD (기본: 끝에서 365일 전)")
    p.add_argument("--end", help="YYYYMMDD (기본: 오늘. 미래면 오늘로 당긴다)")
    p.add_argument("--hour", type=int, default=0,
                   help="--mode storage 에서 하루 중 고를 시각 (기본 0시)")
    p.add_argument("--out", help="산출 폴더 (기본 downloads/wamis)")
    p.add_argument("--sleep", type=float, default=0.3,
                   help="댐 사이 간격(초). 서버가 연속 호출에 민감하다")
    args = p.parse_args(argv)

    if args.list:
        return cmd_list()

    end = args.end or date.today().strftime("%Y%m%d")
    if args.start:
        start = args.start
    else:
        start = (datetime.strptime(end, "%Y%m%d").date()
                 - timedelta(days=365)).strftime("%Y%m%d")

    who = args.dams if args.dams else f"--preset {args.preset}"
    print(f"대상 해석 ({who})")
    targets = _resolve_targets(args)
    if targets is None:
        return 2

    print(f"\n{args.mode} {start}~{end}, 댐 {len(targets)}곳")
    if args.mode != "daily":
        print("  (시자료라 느리다 — 댐당 수십 초 걸릴 수 있다)")

    out_rows: list[dict] = []
    incomplete: list[str] = []
    t0 = time.time()

    for i, d in enumerate(targets, 1):
        if args.mode == "daily":
            got = series.daily(d.damcd, start, end)
            recs = got.rows
        else:
            got = series.hourly(d.damcd, start, end)
            recs = (got.rows if args.mode == "hourly"
                    else series.daily_from_hourly(got.rows, args.hour))

        for r in recs:
            out_rows.append({"damcd": d.damcd, "damnm": d.damnm, **r})

        flag = "" if got.complete else f"  ⚠ 구간 {len(got.failed)}개 실패"
        if not got.complete:
            incomplete.append(d.label)
        print(f"  [{i:>2}/{len(targets)}] {d.label:18s} {len(recs):>5}행 "
              f"(청크 {got.chunks}){flag}")
        time.sleep(args.sleep)

    out_dir = Path(args.out) if args.out else Path(WAMIS_DIR)
    dest = out_dir / f"dam_{args.mode}_{start}_{end}.csv"
    _write_csv(dest, out_rows)

    print(f"\n{len(out_rows)}행 -> {rel(dest)}  ({time.time() - t0:.0f}초)")
    if incomplete:
        # 조용히 넘어가면 나중에 "이 댐은 원래 자료가 없다"로 오해한다.
        print(f"⚠ 불완전 {len(incomplete)}곳: {', '.join(incomplete)}\n"
              f"  같은 명령을 다시 돌리면 대개 채워진다(서버 일시 스로틀).",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
