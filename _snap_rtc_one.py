# -*- coding: utf-8 -*-
"""
벤치마크용 단일 씬 SNAP RTC 러너 (s1_snappy 환경에서 실행).

prepro_grd_gpt.py의 main()은 출력 폴더가 downloads/rtc_grd로 고정이라 기존
Refined Lee 산출물을 덮을 수 있어, 벤치마크에서는 이 러너로 **별도 출력 폴더**에
쓰고 gpt 그래프 실행 시간만 따로 측정한다. 배치와 동일하게 zip을 SSD 임시로
복사한 뒤 처리한다(HDD 랜덤읽기 병목 배제).

출력 마지막 줄에 `PROCESS_SECONDS=<gpt 실행 초>` 를 찍어 오케스트레이터가 파싱한다.

실행(오케스트레이터가 호출):
    conda run -n s1_snappy python _snap_rtc_one.py --zip <GRD.zip> \
        --out-dir downloads/rtc_grd_bench_snap --speckle Frost
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from prepro_grd_gpt import build_grd_rtc_graph


def main() -> None:
    ap = argparse.ArgumentParser(description="벤치마크용 단일 씬 SNAP RTC")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out-dir", default="downloads/rtc_grd_bench_snap")
    ap.add_argument("--speckle", default="Frost",
                    help="스펙클 필터명(Frost/'Refined Lee') 또는 'none'(필터 생략)")
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
            apply_speckle_filter=apply_speckle,
            speckle_filter_name=(args.speckle if apply_speckle else "Frost"),
        )
        t0 = time.perf_counter()
        graph.run(gpt_options=["-q", "8", "-c", "14G"])
        dt = time.perf_counter() - t0
        print(f"완료: {zip_path.stem}_rtc_db.tif  ({dt/60:.1f}분)")
        print(f"PROCESS_SECONDS={dt:.2f}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
