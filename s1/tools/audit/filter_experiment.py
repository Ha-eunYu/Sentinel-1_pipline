# -*- coding: utf-8 -*-
"""같은 씬을 speckle 필터만 바꿔가며 RTC 처리한다 — 필터 비교 실험용.

왜 다시 하나
------------
`FILTER_COMPARISON_KR.md`의 "Frost가 낫다"는 결론은 **VV로만** 낸 것이다.
VH는 물/육지 대비가 다르고 절대값도 약 6 dB 낮아, 같은 결론이 성립하는지
확인된 바 없다(2026-08-17 지적).

무엇을 하나
-----------
지정한 zip 하나를 `--filters` 목록의 필터로 각각 RTC 처리해
`experiments/<태그>/` 에 나란히 쌓는다. 나머지 조건(편파·DEM·픽셀간격)은 동일.
비교 지표 산정은 `qa` 패키지로 따로 한다.

실행:
    conda run -n s1_snappy python -m s1.tools.audit.filter_experiment \
        --zip downloads/sentinel1_grd/S1C_..._9B8B_COG.zip --pol VH
    conda run -n s1_snappy python -m s1.tools.audit.filter_experiment \
        --zip ... --filters Frost "Refined Lee" Lee none --gpt-c 7G
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from s1.core.paths import COP30_KOREA_VRT, DEM_BASIN_DIR, PROJECT_DIR, rel
from s1.preprocess.prepro_grd_gpt import build_grd_rtc_graph

DEFAULT_FILTERS = ["Frost", "Refined Lee", "Lee", "none"]
DEFAULT_DEM = DEM_BASIN_DIR / "korea_full_cop30.tif"


def main() -> None:
    ap = argparse.ArgumentParser(description="speckle 필터별 RTC 산출 (비교 실험)")
    ap.add_argument("--zip", required=True, type=Path, help="입력 GRD zip")
    ap.add_argument("--pol", default="VH", choices=["VV", "VH"])
    ap.add_argument("--filters", nargs="+", default=DEFAULT_FILTERS,
                    help='필터 목록. "none" 은 무필터(대조군)')
    ap.add_argument("--out-dir", type=Path,
                    default=PROJECT_DIR / "experiments" / "vh_filter")
    ap.add_argument("--dem", type=Path, default=DEFAULT_DEM,
                    help="external DEM (기본 korea_full_cop30.tif)")
    ap.add_argument("--gpt-q", default="8")
    ap.add_argument("--gpt-c", default="7G")
    args = ap.parse_args()

    if not args.zip.exists():
        raise SystemExit(f"입력 zip 이 없습니다: {args.zip}")
    if args.dem and not args.dem.exists():
        raise SystemExit(f"DEM 이 없습니다: {args.dem} (VRT 는 안 된다 — ISSUES #1)")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"입력 {args.zip.name}\n편파 {args.pol} · DEM {rel(args.dem)} · "
          f"필터 {len(args.filters)}종 -> {rel(args.out_dir)}\n")

    for i, filt in enumerate(args.filters, 1):
        tag = "_nofilter" if filt == "none" else "_" + filt.lower().replace(" ", "")
        out_tif = args.out_dir / f"{args.zip.stem}_rtc_db_{args.pol.lower()}{tag}.tif"
        if out_tif.exists():
            print(f"[{i}/{len(args.filters)}] 건너뜀 (이미 있음): {out_tif.name}")
            continue

        print(f"[{i}/{len(args.filters)}] {filt} 처리 시작")
        t0 = time.time()
        tmpdir = Path(tempfile.mkdtemp(prefix="filtexp_"))
        try:
            src = tmpdir / args.zip.name
            shutil.copy2(args.zip, src)
            graph = build_grd_rtc_graph(
                src, out_dir=args.out_dir,
                polarization=args.pol,
                apply_speckle_filter=(filt != "none"),
                speckle_filter_name=(None if filt == "none" else filt),
                external_dem_file=args.dem,
                external_dem_apply_egm=False,   # COP30 은 이미 타원체고 (ISSUES #3)
                out_tag=f"_{args.pol.lower()}{tag}",
            )
            graph.run(gpt_options=["-q", args.gpt_q, "-c", args.gpt_c])
            print(f"[{i}/{len(args.filters)}] 완료 ({(time.time()-t0)/60:.1f}분): "
                  f"{out_tif.name}")
        except Exception as e:                  # noqa: BLE001
            print(f"[{i}/{len(args.filters)}] 실패: {filt} -> {e}")
            out_tif.unlink(missing_ok=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n다음 단계: qa 패키지로 ENL·가는선·경계·수면분리도 산정 후 "
          "FILTER_COMPARISON_KR.md 에 VH 절 추가")


if __name__ == "__main__":
    main()
