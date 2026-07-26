# -*- coding: utf-8 -*-
"""
벤치마크용 단일 씬 SNAP RTC 러너 (s1_snappy 환경에서 실행).

prepro_grd_gpt.py의 main()은 출력 폴더가 downloads/rtc_grd로 고정이라 기존
Refined Lee 산출물을 덮을 수 있어, 벤치마크에서는 이 러너로 **별도 출력 폴더**에
쓰고 gpt 그래프 실행 시간만 따로 측정한다. 배치와 동일하게 zip을 SSD 임시로
복사한 뒤 처리한다(HDD 랜덤읽기 병목 배제).

DEM 소스 비교(옵션):
  - 기본: demName="Copernicus 30m Global DEM"  → SNAP이 C드라이브
    (.snap/auxdata/dem)로 **자동 다운로드**하는 DEM.
  - --external-dem <파일>: External DEM 모드. D드라이브의 로컬 COP30 VRT
    (D:/00_COP30/COP30_hh.vrt) 등을 직접 쓴다. 정표고 DEM이면 EGM 보정 on.

출력 마지막 줄에 `PROCESS_SECONDS=<gpt 실행 초>`, `OUT_PATH=<산출물>`,
`OUT_DIMS=<W>x<H>` 를 찍어 오케스트레이터가 파싱한다.

실행(오케스트레이터가 호출):
    conda run -n s1_snappy python _snap_rtc_one.py --zip <GRD.zip> \
        --out-dir downloads/rtc_grd_bench_snap --speckle Frost \
        --frost-size 5 --frost-damping 2
    # DEM 비교(외부 COP30):
    conda run -n s1_snappy python _snap_rtc_one.py --zip <GRD.zip> \
        --external-dem D:/00_COP30/COP30_hh.vrt --out-tag _cop30d --speckle none
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

try:  # 한글 print가 cp949 콘솔에서 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from prepro_grd_gpt import build_grd_rtc_graph


def main() -> None:
    ap = argparse.ArgumentParser(description="벤치마크용 단일 씬 SNAP RTC")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out-dir", default="downloads/rtc_grd_bench_snap")
    ap.add_argument("--speckle", default="Frost",
                    help="스펙클 필터명(Frost/'Refined Lee') 또는 'none'(필터 생략)")
    ap.add_argument("--frost-size", type=int, default=None,
                    help="Frost filterSizeX/Y (생략 시 SNAP 기본 3)")
    ap.add_argument("--frost-damping", type=int, default=None,
                    help="Frost dampingFactor (생략 시 SNAP 기본 2)")
    ap.add_argument("--external-dem", default=None,
                    help="External DEM 파일(예 D:/00_COP30/COP30_hh.vrt). 생략 시 "
                         "Copernicus 30m 자동 다운로드(C드라이브)")
    ap.add_argument("--no-egm", action="store_true",
                    help="External DEM에 EGM 보정을 끈다(기본 on)")
    ap.add_argument("--pixel-spacing", type=float, default=10.0,
                    help="Terrain-Correction 출력 픽셀 간격(m). 기본 10")
    ap.add_argument("--out-tag", default="", help="산출물 파일명 접미사")
    args = ap.parse_args()

    zip_path = Path(args.zip)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    apply_speckle = args.speckle.lower() != "none"
    tmpdir = Path(tempfile.mkdtemp(prefix="benchsnap_"))
    ssd_copy = tmpdir / zip_path.name
    try:
        shutil.copy2(zip_path, ssd_copy)
        graph = build_grd_rtc_graph(
            ssd_copy, out_dir=out_dir,
            external_dem_file=args.external_dem,
            external_dem_apply_egm=not args.no_egm,
            pixel_spacing_m=args.pixel_spacing,
            out_tag=args.out_tag,
            apply_speckle_filter=apply_speckle,
            speckle_filter_name=(args.speckle if apply_speckle else "Frost"),
            speckle_window_size=args.frost_size,
            speckle_damping_factor=args.frost_damping,
        )
        t0 = time.perf_counter()
        graph.run(gpt_options=["-q", "8", "-c", "14G"])
        dt = time.perf_counter() - t0
        out_path = out_dir / f"{zip_path.stem}_rtc_db{args.out_tag}.tif"
        dims = ""
        try:
            import rasterio
            with rasterio.open(out_path) as ds:
                dims = f"{ds.width}x{ds.height}"
        except Exception:
            pass
        dem_src = args.external_dem or "Copernicus 30m (auto, C:)"
        print(f"완료: {out_path.name}  ({dt/60:.1f}분)  DEM={dem_src}")
        print(f"PROCESS_SECONDS={dt:.2f}")
        print(f"OUT_PATH={out_path}")
        print(f"OUT_DIMS={dims}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
