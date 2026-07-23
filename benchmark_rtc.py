# -*- coding: utf-8 -*-
"""
SNAP RTC vs sarsen RTC 속도 벤치마크 (같은 씬, 순차·비병렬).

각 씬에 대해 (1) SNAP RTC(_snap_rtc_one.py, s1_snappy) → (2) sarsen RTC
(rtc_sarsen.py, sarsen_clean)를 **하나씩 순서대로** 실행하며 시간을 잰다.
두 도구는 절대 동시에 돌리지 않는다(자원 경쟁 배제 = 공정 비교의 핵심).

측정 지표(씬별):
  - wall_s      : 해당 도구 프로세스 전체 벽시계 시간(conda run·JVM/파이썬 기동·
                  zip 복사/추출·DEM 준비 등 실사용 오버헤드 포함)
  - process_s   : 워커가 보고한 '핵심 처리'만의 시간
                  (SNAP=gpt 그래프 실행, sarsen=지형보정+dB). 워커의 PROCESS_SECONDS.

공정성 주의(리포트에도 명시):
  - SNAP RTC에는 스펙클 필터(Frost) 단계가 포함되지만 sarsen에는 없다.
    순수 지형보정 비교를 원하면 --snap-speckle none 으로 SNAP 스펙클을 끈다.
  - sarsen wall에는 zip 추출 + COP30 클립 + EGM 보정이 포함된다(SNAP은 DEM을
    내부 처리). process_s는 그 오버헤드를 뺀 값이라 둘을 같이 본다.

실행(현재 SNAP 배치가 모두 끝난 뒤!):
    conda run -n sarsen_clean python benchmark_rtc.py --n 9
    conda run -n sarsen_clean python benchmark_rtc.py --zips a.zip b.zip ...
    conda run -n sarsen_clean python benchmark_rtc.py --n 9 --snap-speckle none
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
GRD_DIR = PROJECT_DIR / "downloads" / "sentinel1_grd"
SNAP_OUT = PROJECT_DIR / "downloads" / "rtc_grd_bench_snap"
SARSEN_OUT = PROJECT_DIR / "downloads" / "rtc_grd_bench_sarsen"
CSV_OUT = PROJECT_DIR / "downloads" / "rtc_benchmark.csv"

PROC_RE = re.compile(r"PROCESS_SECONDS=([\d.]+)")


def pick_scenes(n: int) -> list[Path]:
    """파일 크기 스펙트럼(작은~큰)에 고르게 걸치도록 n개 선택."""
    zips = sorted(GRD_DIR.glob("*.zip"), key=lambda p: p.stat().st_size)
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR}에 GRD zip이 없습니다.")
    if n >= len(zips):
        return zips
    idx = [round(i * (len(zips) - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]
    return [zips[i] for i in sorted(set(idx))]


def guard_no_running_batch() -> None:
    """SNAP gpt / 배치가 돌고 있으면 벤치마크를 멈춘다(비병렬 보장)."""
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-Process gpt,java -ErrorAction SilentlyContinue | Measure-Object | "
             "Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        if out and out.split()[-1] != "0":
            raise SystemExit(
                f"경고: gpt/java 프로세스가 {out}개 실행 중입니다. 진행 중인 SNAP 배치가 "
                "끝난 뒤 실행하세요(비병렬 비교를 위해). 무시하려면 --force.")
    except FileNotFoundError:
        pass  # powershell 없으면 스킵


def run_worker(cmd: list[str]) -> tuple[float, float | None, int]:
    """워커를 실행하고 (wall초, process초|None, returncode) 반환."""
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    m = PROC_RE.findall((proc.stdout or "") + (proc.stderr or ""))
    process_s = float(m[-1]) if m else None
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-5:] +
                         (proc.stderr or "").splitlines()[-5:])
        print(f"  [실패 rc={proc.returncode}]\n{tail}")
    return wall, process_s, proc.returncode


def main() -> None:
    ap = argparse.ArgumentParser(description="SNAP RTC vs sarsen RTC 속도 벤치마크")
    ap.add_argument("--n", type=int, default=9, help="표본 씬 수(파일크기 스펙트럼 고르게)")
    ap.add_argument("--zips", nargs="*", default=None, help="명시적 zip 목록(주면 --n 무시)")
    ap.add_argument("--snap-speckle", default="Frost", help="SNAP 스펙클 필터(Frost/'Refined Lee'/none)")
    ap.add_argument("--snap-env", default="s1_snappy")
    ap.add_argument("--sarsen-env", default="sarsen_clean")
    ap.add_argument("--force", action="store_true", help="실행 중 gpt/java가 있어도 강행")
    args = ap.parse_args()

    if not args.force:
        guard_no_running_batch()

    scenes = [Path(z) for z in args.zips] if args.zips else pick_scenes(args.n)
    SNAP_OUT.mkdir(parents=True, exist_ok=True)
    SARSEN_OUT.mkdir(parents=True, exist_ok=True)
    print(f"벤치마크 대상 {len(scenes)}개 씬 (순차·비병렬):")
    for z in scenes:
        print(f"  {z.stat().st_size/1e9:.2f} GB  {z.name}")

    rows = []
    for i, z in enumerate(scenes, 1):
        size_gb = round(z.stat().st_size / 1e9, 3)
        print(f"\n[{i}/{len(scenes)}] {z.name}  ({size_gb} GB)")

        print("  - SNAP RTC ...")
        snap_cmd = ["conda", "run", "-n", args.snap_env, "python", "_snap_rtc_one.py",
                    "--zip", str(z), "--out-dir", str(SNAP_OUT), "--speckle", args.snap_speckle]
        snap_wall, snap_proc, snap_rc = run_worker(snap_cmd)
        print(f"    wall {snap_wall/60:.1f}분, process {snap_proc/60 if snap_proc else float('nan'):.1f}분")

        print("  - sarsen RTC ...")
        sarsen_cmd = ["conda", "run", "-n", args.sarsen_env, "python", "rtc_sarsen.py",
                      "--zip", str(z), "--out-dir", str(SARSEN_OUT)]
        sarsen_wall, sarsen_proc, sarsen_rc = run_worker(sarsen_cmd)
        print(f"    wall {sarsen_wall/60:.1f}분, process {sarsen_proc/60 if sarsen_proc else float('nan'):.1f}분")

        rows.append({
            "scene": z.stem, "size_gb": size_gb,
            "snap_wall_s": round(snap_wall, 1), "snap_process_s": round(snap_proc, 1) if snap_proc else "",
            "snap_rc": snap_rc,
            "sarsen_wall_s": round(sarsen_wall, 1), "sarsen_process_s": round(sarsen_proc, 1) if sarsen_proc else "",
            "sarsen_rc": sarsen_rc,
            "process_ratio_sarsen_over_snap": (round(sarsen_proc / snap_proc, 2)
                                               if (snap_proc and sarsen_proc) else ""),
        })

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["snap_process_s"] and r["sarsen_process_s"]]
    print(f"\n=== 요약 (성공 {len(ok)}/{len(rows)}) ===")
    if ok:
        sn = sum(r["snap_process_s"] for r in ok) / len(ok)
        sa = sum(r["sarsen_process_s"] for r in ok) / len(ok)
        snw = sum(r["snap_wall_s"] for r in ok) / len(ok)
        saw = sum(r["sarsen_wall_s"] for r in ok) / len(ok)
        print(f"평균 process: SNAP {sn/60:.1f}분 vs sarsen {sa/60:.1f}분  (sarsen/SNAP {sa/sn:.2f}배)")
        print(f"평균 wall   : SNAP {snw/60:.1f}분 vs sarsen {saw/60:.1f}분")
        print(f"SNAP 스펙클: {args.snap_speckle}  (none이 아니면 SNAP만 스펙클 단계 포함)")
    print(f"CSV: {CSV_OUT}")


if __name__ == "__main__":
    main()
