# -*- coding: utf-8 -*-
"""
SNAP RTC vs sarsen RTC 속도 벤치마크 (같은 씬, 순차·비병렬).

표본 선택: 파일 **용량을 3분위(소/중/대)로 나눠 각 버킷에서 --per-bucket개씩**
고른다(기본 3×3=9장). 각 씬에 대해 아래를 **하나씩 순서대로** 실행한다
(두 도구를 절대 동시에 돌리지 않음 = 공정 비교의 핵심):

  1) sarsen RTC : rtc_sarsen.py (sarsen_clean). 스펙클 없음. DEM은 로컬 COP30(D:).
                  먼저 돌려 산출물 bounds를 얻는다(cop30 모드의 SNAP DEM 클립용).
  2) SNAP RTC   : _snap_rtc_one.py (s1_snappy). Frost 스펙클 포함(하이퍼파라미터
                  --frost-size/--frost-damping를 로컬 Frost와 동일하게 맞춤).
                  DEM 모드(--snap-dem-mode):
                    auto  = SNAP 자동 Copernicus 30m(C: 자동 다운로드) [SNAP 네이티브]
                    cop30 = 로컬 COP30(D:)을 씬 bbox로 클립한 GeoTIFF를 external DEM으로.
                            (SNAP은 VRT/폴더를 못 읽으므로 GeoTIFF 클립 필요.
                             sarsen과 동일 DEM → 가장 공정. 단 external DEM 읽기 오버헤드 있음.)
  3) 로컬 Frost : sarsen 산출물(dB)을 linear로 되돌려 filtering.frost_filter를
                  --frost-size/--frost-damping로 적용(시간만 측정).

이렇게 하면 한 번의 실행으로 세 가지 비교가 나온다:
  - (Part1) SNAP RTC vs sarsen RTC 순수 지형보정 시간 + **왜 다른지**(출력 픽셀수·
    throughput px/s로 정량화: SNAP 10m vs sarsen COP30 ~30m).
  - (Part3) 같은 Frost 하이퍼파라미터에서 SNAP(RTC+Frost) 총시간 vs
    sarsen(RTC)+로컬 Frost 총시간.

측정 지표(씬별):
  - *_wall_s   : 프로세스 전체 벽시계(conda run·JVM/파이썬 기동·zip 복사/추출·
                 DEM 준비 등 실사용 오버헤드 포함)
  - *_proc_s   : 워커가 보고한 '핵심 처리'만(PROCESS_SECONDS). SNAP=gpt 그래프,
                 sarsen=지형보정+dB.
  - *_px       : 산출물 전체 픽셀수. throughput = px / proc_s.
  - dem_clip_s : (cop30 모드) COP30을 씬 bbox로 클립한 gdalwarp 시간(SNAP 전처리).

실행(현재 SNAP 배치가 모두 끝난 뒤, 단독으로!):
    conda run -n sarsen_clean python benchmark_rtc.py                      # auto DEM
    conda run -n sarsen_clean python benchmark_rtc.py --snap-dem-mode cop30 # 로컬 COP30
    conda run -n sarsen_clean python benchmark_rtc.py --per-bucket 3 --frost-size 5 --frost-damping 2
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_DIR = Path(__file__).resolve().parent
GRD_DIR = PROJECT_DIR / "downloads" / "sentinel1_grd"
SNAP_OUT = PROJECT_DIR / "downloads" / "rtc_grd_bench_snap"
SARSEN_OUT = PROJECT_DIR / "downloads" / "rtc_grd_bench_sarsen"
CSV_OUT = PROJECT_DIR / "downloads" / "rtc_benchmark.csv"
DEFAULT_COP30_VRT = Path(r"D:/00_COP30/COP30_hh.vrt")

PROC_RE = re.compile(r"PROCESS_SECONDS=([\d.]+)")
DIMS_RE = re.compile(r"OUT_DIMS=(\d+)x(\d+)")


def pick_scenes_by_bucket(per_bucket: int, n_buckets: int = 3) -> list[tuple[int, Path]]:
    """파일 크기를 n_buckets 분위로 나눠 각 버킷에서 per_bucket개씩 고른다.
    버킷 내에서는 인덱스를 고르게 벌려(작은~큰) 대표성을 준다."""
    zips = sorted(GRD_DIR.glob("*.zip"), key=lambda p: p.stat().st_size)
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR}에 GRD zip이 없습니다.")
    n = len(zips)
    chosen: list[tuple[int, Path]] = []
    for b in range(n_buckets):
        lo = b * n // n_buckets
        hi = (b + 1) * n // n_buckets  # [lo, hi)
        group = zips[lo:hi]
        if not group:
            continue
        k = min(per_bucket, len(group))
        if k == 1:
            idx = [len(group) // 2]
        else:
            idx = [round(i * (len(group) - 1) / (k - 1)) for i in range(k)]
        for i in sorted(set(idx)):
            chosen.append((b, group[i]))
    return chosen


def guard_no_running_batch() -> None:
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
        pass


def run_worker(cmd: list[str]) -> tuple[float, float | None, str | None, int]:
    """워커 실행 → (wall초, process초|None, out_dims|None, returncode)."""
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    wall = time.perf_counter() - t0
    blob = (proc.stdout or "") + (proc.stderr or "")
    m = PROC_RE.findall(blob)
    process_s = float(m[-1]) if m else None
    d = DIMS_RE.findall(blob)
    dims = f"{d[-1][0]}x{d[-1][1]}" if d else None
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-6:] +
                         (proc.stderr or "").splitlines()[-6:])
        print(f"  [실패 rc={proc.returncode}]\n{tail}")
    return wall, process_s, dims, proc.returncode


def raster_px(path: Path) -> tuple[int, int]:
    """(전체픽셀, 실제 후방산란 픽셀 dB<-1). 못 열면 (0,0)."""
    try:
        import numpy as np
        import rasterio
        with rasterio.open(path) as ds:
            a = ds.read(1)
            total = ds.width * ds.height
            real = int(np.sum(np.isfinite(a) & (a < -1.0)))
            return total, real
    except Exception:
        return 0, 0


def clip_cop30_from_output(ref_tif: Path, cop30_vrt: Path, margin: float = 0.2) -> tuple[Path | None, float]:
    """sarsen 산출물 bounds(+margin)로 COP30 VRT를 GeoTIFF 클립(SNAP external DEM용).
    (클립경로, gdalwarp초) 반환. sarsen 출력이 y축 양수 transform이면 bounds 정규화."""
    try:
        import rasterio
        import rtc_sarsen
    except Exception as e:
        print(f"  [COP30 클립 임포트 실패] {e}")
        return None, 0.0
    if not ref_tif.exists():
        return None, 0.0
    with rasterio.open(ref_tif) as ds:
        b = ds.bounds
    bbox = (min(b.left, b.right), min(b.top, b.bottom),
            max(b.left, b.right), max(b.top, b.bottom))
    tmp = Path(tempfile.mkdtemp(prefix="cop30clip_"))
    t0 = time.perf_counter()
    dem = rtc_sarsen.build_dem_wgs84(bbox, margin, Path(cop30_vrt), None, tmp)
    dt = time.perf_counter() - t0
    SNAP_OUT.mkdir(parents=True, exist_ok=True)
    out = SNAP_OUT / f"_demclip_{ref_tif.stem}.tif"
    try:
        shutil.copy2(str(dem), str(out))
    except Exception as e:
        print(f"  [COP30 클립 복사 실패] {e} (dem={dem})")
        shutil.rmtree(tmp, ignore_errors=True)
        return None, dt
    shutil.rmtree(tmp, ignore_errors=True)
    return out, dt


def time_local_frost(db_tif: Path, window: int, damping: float) -> tuple[float | None, int]:
    """sarsen dB 산출물을 linear로 되돌려 로컬 Frost 적용, (frost초, 출력px)."""
    try:
        import numpy as np
        import rasterio
        from filtering import frost_filter
    except Exception as e:
        print(f"  [로컬 Frost 임포트 실패] {e}")
        return None, 0
    if not db_tif.exists():
        return None, 0
    tmp = Path(tempfile.mkdtemp(prefix="frost_"))
    try:
        with rasterio.open(db_tif) as ds:
            db = ds.read(1).astype("float32")
            prof = ds.profile
        prof.update(dtype="float32", nodata=float("nan"))
        lin = np.where(np.isfinite(db), np.power(10.0, db / 10.0), np.nan).astype("float32")
        lin_in = tmp / "lin_in.tif"
        with rasterio.open(lin_in, "w", **prof) as ds:
            ds.write(lin, 1)
        lin_out = tmp / "lin_frost.tif"
        t0 = time.perf_counter()
        frost_filter(lin_in, lin_out, window_size=window, damping=damping)
        dt = time.perf_counter() - t0
        px = prof["width"] * prof["height"]
        return dt, px
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pxps(px: int, s: float | None) -> str:
    return f"{px / s / 1e6:.2f}" if (s and px) else ""


def main() -> None:
    ap = argparse.ArgumentParser(description="SNAP RTC vs sarsen RTC 속도 벤치마크(크기 버킷별)")
    ap.add_argument("--per-bucket", type=int, default=3, help="용량 버킷별 표본 수(기본 3)")
    ap.add_argument("--buckets", type=int, default=3, help="용량 분위 개수(기본 3=소/중/대)")
    ap.add_argument("--zips", nargs="*", default=None, help="명시 zip 목록(주면 버킷 무시)")
    ap.add_argument("--snap-speckle", default="Frost", help="SNAP 스펙클(Frost/'Refined Lee'/none)")
    ap.add_argument("--frost-size", type=int, default=5, help="Frost 윈도우(SNAP·로컬 공통, 기본 5)")
    ap.add_argument("--frost-damping", type=int, default=2, help="Frost damping(SNAP·로컬 공통, 기본 2)")
    ap.add_argument("--snap-dem-mode", choices=["auto", "cop30"], default="auto",
                    help="SNAP DEM: auto=자동 Copernicus(C:), cop30=로컬 COP30(D:) 클립 external")
    ap.add_argument("--cop30-vrt", type=Path, default=DEFAULT_COP30_VRT)
    ap.add_argument("--snap-env", default="s1_snappy")
    ap.add_argument("--sarsen-env", default="sarsen_clean")
    ap.add_argument("--force", action="store_true", help="실행 중 gpt/java가 있어도 강행")
    args = ap.parse_args()

    if not args.force:
        guard_no_running_batch()

    if args.zips:
        scenes = [(-1, Path(z)) for z in args.zips]
    else:
        scenes = pick_scenes_by_bucket(args.per_bucket, args.buckets)
    SNAP_OUT.mkdir(parents=True, exist_ok=True)
    SARSEN_OUT.mkdir(parents=True, exist_ok=True)

    bucket_name = {0: "소", 1: "중", 2: "대"}
    print(f"벤치마크 {len(scenes)}개 씬 (순차·비병렬, SNAP DEM={args.snap_dem_mode}, "
          f"Frost {args.frost_size}x{args.frost_size} d{args.frost_damping}):")
    for b, z in scenes:
        print(f"  [{bucket_name.get(b, '?')}] {z.stat().st_size/1e6:6.0f} MB  {z.name}")

    rows = []
    for i, (b, z) in enumerate(scenes, 1):
        size_mb = round(z.stat().st_size / 1e6, 1)
        print(f"\n[{i}/{len(scenes)}] {z.name}  ({size_mb} MB, 버킷 {bucket_name.get(b, '?')})")

        snap_out = SNAP_OUT / f"{z.stem}_rtc_db.tif"
        sarsen_out = SARSEN_OUT / f"{z.stem}_rtc_db.tif"
        for p in (snap_out, sarsen_out):  # 신선한 타이밍 위해 기존 산출물 제거
            p.unlink(missing_ok=True)

        # 1) sarsen 먼저 (cop30 모드의 SNAP DEM 클립에 이 출력 bounds를 씀)
        print("  - sarsen RTC ...")
        sarsen_cmd = ["conda", "run", "-n", args.sarsen_env, "python", "rtc_sarsen.py",
                      "--zip", str(z), "--out-dir", str(SARSEN_OUT)]
        sarsen_wall, sarsen_proc, _, sarsen_rc = run_worker(sarsen_cmd)
        sarsen_total, sarsen_real = raster_px(sarsen_out)
        print(f"    wall {sarsen_wall/60:.1f}분, process {sarsen_proc/60 if sarsen_proc else float('nan'):.1f}분, "
              f"px {sarsen_total/1e6:.1f}M, {_pxps(sarsen_total, sarsen_proc)} Mpx/s")

        # 2) SNAP DEM 준비(cop30 모드면 COP30 클립)
        dem_clip = None
        dem_clip_s = 0.0
        if args.snap_dem_mode == "cop30":
            print("  - COP30 클립(SNAP external DEM) ...")
            dem_clip, dem_clip_s = clip_cop30_from_output(sarsen_out, args.cop30_vrt)
            print(f"    dem_clip {dem_clip_s:.1f}s -> {dem_clip.name if dem_clip else '실패'}")

        # 3) SNAP RTC
        print("  - SNAP RTC ...")
        snap_cmd = ["conda", "run", "-n", args.snap_env, "python", "_snap_rtc_one.py",
                    "--zip", str(z), "--out-dir", str(SNAP_OUT), "--speckle", args.snap_speckle,
                    "--frost-size", str(args.frost_size), "--frost-damping", str(args.frost_damping)]
        if args.snap_dem_mode == "cop30" and dem_clip is not None:
            snap_cmd += ["--external-dem", str(dem_clip)]
        snap_wall, snap_proc, snap_dims, snap_rc = run_worker(snap_cmd)
        snap_total, snap_real = raster_px(snap_out)
        real_pct = 100 * snap_real / snap_total if snap_total else 0
        print(f"    wall {snap_wall/60:.1f}분, process {snap_proc/60 if snap_proc else float('nan'):.1f}분, "
              f"px {snap_total/1e6:.1f}M (실제 {real_pct:.0f}%), {_pxps(snap_total, snap_proc)} Mpx/s")
        if snap_total and real_pct < 20:
            print(f"    ⚠️ SNAP 출력 실제 후방산란 {real_pct:.0f}% — DEM 커버리지 불량 의심(auto DEM 미수신?)")
        if dem_clip is not None:
            Path(dem_clip).unlink(missing_ok=True)

        # 4) 로컬 Frost (sarsen 산출물)
        print("  - 로컬 Frost (sarsen 산출물) ...")
        frost_s, _ = time_local_frost(sarsen_out, args.frost_size, args.frost_damping)
        print(f"    frost {frost_s:.1f}s" if frost_s else "    frost 실패")

        sarsen_rtcfrost = (sarsen_proc + frost_s) if (sarsen_proc and frost_s) else None
        rows.append({
            "scene": z.stem[:24] + "…" + z.stem[-9:], "bucket": bucket_name.get(b, "?"),
            "size_mb": size_mb,
            "snap_wall_s": round(snap_wall, 1), "snap_proc_s": round(snap_proc, 1) if snap_proc else "",
            "snap_px_M": round(snap_total / 1e6, 1), "snap_real_pct": round(real_pct, 0),
            "snap_Mpxps": _pxps(snap_total, snap_proc), "snap_rc": snap_rc, "dem_clip_s": round(dem_clip_s, 1),
            "sarsen_wall_s": round(sarsen_wall, 1), "sarsen_proc_s": round(sarsen_proc, 1) if sarsen_proc else "",
            "sarsen_px_M": round(sarsen_total / 1e6, 1), "sarsen_Mpxps": _pxps(sarsen_total, sarsen_proc), "sarsen_rc": sarsen_rc,
            "frost_s": round(frost_s, 1) if frost_s else "",
            "sarsen_rtcfrost_s": round(sarsen_rtcfrost, 1) if sarsen_rtcfrost else "",
            "ratio_proc_sarsen_over_snap": (round(sarsen_proc / snap_proc, 2) if (snap_proc and sarsen_proc) else ""),
            "ratio_rtcfrost_sarsen_over_snap": (round(sarsen_rtcfrost / snap_proc, 2) if (snap_proc and sarsen_rtcfrost) else ""),
        })
        # 중간 저장(장시간 실행 중 끊겨도 남게)
        with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    ok = [r for r in rows if r["snap_proc_s"] and r["sarsen_proc_s"]]
    print(f"\n=== 요약 (성공 {len(ok)}/{len(rows)}), SNAP DEM={args.snap_dem_mode}, "
          f"Frost {args.frost_size}x{args.frost_size} d{args.frost_damping} ===")
    if ok:
        def avg(key):
            vals = [r[key] for r in ok if r[key] != ""]
            return sum(vals) / len(vals) if vals else float("nan")
        sn, sa = avg("snap_proc_s"), avg("sarsen_proc_s")
        print(f"[Part1] 평균 process: SNAP {sn/60:.1f}분 vs sarsen {sa/60:.1f}분 (sarsen/SNAP {sa/sn:.2f}배)")
        print(f"        평균 wall   : SNAP {avg('snap_wall_s')/60:.1f}분 vs sarsen {avg('sarsen_wall_s')/60:.1f}분")
        print(f"        평균 출력 px: SNAP {avg('snap_px_M'):.0f}M(10m) vs sarsen {avg('sarsen_px_M'):.0f}M(COP30~30m)")
        snth = [float(r["snap_Mpxps"]) for r in ok if r["snap_Mpxps"]]
        sath = [float(r["sarsen_Mpxps"]) for r in ok if r["sarsen_Mpxps"]]
        if snth and sath:
            print(f"        평균 throughput: SNAP {sum(snth)/len(snth):.2f} vs sarsen {sum(sath)/len(sath):.2f} Mpx/s "
                  f"(← '왜 다른가'의 핵심: 해상도 보정)")
        sarf = avg("sarsen_rtcfrost_s")
        print(f"[Part3] 같은 Frost({args.frost_size}x{args.frost_size} d{args.frost_damping}) 총시간: "
              f"SNAP(RTC+Frost) {sn/60:.1f}분 vs sarsen(RTC)+로컬Frost {sarf/60:.1f}분 (sarsen/SNAP {sarf/sn:.2f}배)")
        print(f"        (로컬 Frost 평균 {avg('frost_s'):.1f}s, cop30 모드 DEM클립 평균 {avg('dem_clip_s'):.1f}s)")
    print(f"CSV: {CSV_OUT}")


if __name__ == "__main__":
    main()
