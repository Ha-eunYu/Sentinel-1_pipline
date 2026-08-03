# -*- coding: utf-8 -*-
"""영산강 granule 하나를 **세 DEM**으로 RTC 처리해 결측률을 비교한다.

가르려는 것
-----------
영산강 제약 안 dB의 20.3%가 결측이고, 그 자리의 COP30은 75.2%가 정확히 0 m다.
원인이 둘 중 무엇인지 모른다.

    ① SNAP이 0을 nodata로 취급        → 0.1 m 치환만으로 해결
    ② 수역 평탄면에서 조사면적이 퇴화   → 값을 바꿔도 재발

세 판을 돌려 결측률을 비교하면 갈린다.

    cop30        원본 (대조군)
    cop30_fix    육지 안 0값 → 0.1 m
    ngii_hybrid  육지 안 0값 → NGII(64.7%) 우선, 없으면 0.1 m

⚠ `externalDEMApplyEGM=False` — COP30·NGII 둘 다 이미 타원체고다. 실측
   COP30−NGII 중앙이 −0.64 m라 지오이드고(+24~26 m)가 아니다. `True`로 주면
   이중 보정이 된다.

실행
----
    conda run -n s1_snappy python test_dem_rtc.py --only 6D9F
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from prepro_grd_gpt import build_grd_rtc_graph

GRD_DIR = Path("downloads/sentinel1_grd")
DEM_DIR = Path("downloads/dem_test")
OUT = Path("downloads/rtc_dem_test")
DEMS = ["cop30", "cop30_fix", "ngii_hybrid"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="38C3",
                    help="씬 ID 4자리. 기본은 영산강을 덮는 20250718 씬")
    ap.add_argument("--pol", default="VH")
    ap.add_argument("--gpt-c", default="6G")
    ap.add_argument("--dem", action="append", choices=DEMS)
    args = ap.parse_args()

    zips = [z for z in GRD_DIR.glob("*.zip") if f"_{args.only.upper()}" in z.name.upper()]
    if not zips:
        raise SystemExit(f"{args.only} 씬을 못 찾았습니다.")
    z = zips[0]
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"대상 {z.name}\n")

    for tag in (args.dem or DEMS):
        dem = DEM_DIR / f"yeongsan_{tag}.tif"
        if not dem.exists():
            print(f"[{tag}] DEM 없음: {dem}")
            continue
        out_tif = OUT / f"{z.stem}_rtc_db_{tag}.tif"
        if out_tif.exists():
            print(f"[{tag}] 이미 있음 — 건너뜀")
            continue

        t0 = time.time()
        tmp = Path(tempfile.mkdtemp(prefix=f"demtest_{tag}_"))
        try:
            local = tmp / z.name
            shutil.copy2(z, local)
            g = build_grd_rtc_graph(
                local, OUT, polarization=args.pol,
                external_dem_file=dem.resolve(),
                external_dem_nodata=-32768.0,
                # COP30·NGII 둘 다 타원체고 — EGM 보정을 걸면 이중 적용된다
                external_dem_apply_egm=False,
                out_tag=f"_{tag}")
            g.run(gpt_options=["-q", "8", "-c", args.gpt_c])
            print(f"[{tag}] {time.time()-t0:>5.0f}s  {out_tif.name}", flush=True)
        except Exception as e:                       # noqa: BLE001
            print(f"[{tag}] 실패: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n산출 → {OUT}")
    print("검증: gee/Korea_WaterDetection_2025_2026/dem_test_compare.py")


if __name__ == "__main__":
    main()
