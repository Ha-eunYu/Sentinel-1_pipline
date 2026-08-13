# -*- coding: utf-8 -*-
"""
downloads/sentinel1 의 SLC zip들을 순차적으로 RTC(dB) 처리하는 배치 러너.

batch_grd_rtc.py의 SLC 버전. 홍수 AOI(Korea_flood_AOI + 0.1도) 서브셋으로
처리하므로 씬당 20분 내외.

**AOI 미교차 씬은 처리 전에 footprint로 걸러낸다** (2026-08-14 변경).
예전에는 그냥 SNAP에 넣고 Subset 단계에서 나는 예외를 "AOI 미교차일 수 있음"
으로 처리했는데, 그러면 *대상이 아닌 씬*과 *진짜 실패*가 같은 칸에 집계돼
배치 결과를 신뢰할 수 없었다. 이제 원본 zip의 map-overlay.kml footprint로
미리 판정해서, 안 겹치면 아예 목록에서 빼고 겹치는 것만 돌린다. 남는 실패는
전부 진짜 실패다.

- 2022년 등 과거 참조용 씬은 제외하고 --year 접두어 씬만 처리한다.
- 이미 산출물(downloads/rtc/<씬ID>_rtc_db.tif)이 있으면 건너뛴다 (재실행 안전).
- 입력 zip은 시스템 임시 폴더(C: SSD)로 복사 후 처리하고 복사본은 삭제한다
  (공통 러너 s1.preprocess.batch_runner 가 담당).

실행:
    conda run -n s1_snappy python -m s1.tools.preprocess.batch_slc_rtc
    conda run -n s1_snappy python -m s1.tools.preprocess.batch_slc_rtc --year 2025
    conda run -n s1_snappy python -m s1.tools.preprocess.batch_slc_rtc --no-aoi-filter
"""

from __future__ import annotations

import argparse
from pathlib import Path

from s1.core.aoi import intersects
from s1.core.paths import KOREA_FLOOD_AOI, RTC_SLC_DIR, SLC_DIR, rel
from s1.preprocess.batch_runner import run_batch
from s1.preprocess.prepro_gpt import aoi_wkt_from_geojson, build_rtc_graph


def main() -> None:
    ap = argparse.ArgumentParser(description="SLC 일괄 RTC (홍수 AOI 서브셋)")
    ap.add_argument("--year", default="2026", help="이 연도 씬만 처리 (기본 2026)")
    ap.add_argument("--aoi", type=Path, default=KOREA_FLOOD_AOI,
                    help="서브셋·교차판정에 쓸 경계 GeoJSON")
    ap.add_argument("--min-overlap", type=float, default=0.5,
                    help="이 비율(%%) 미만으로 겹치면 처리 대상에서 제외 (기본 0.5)")
    ap.add_argument("--no-aoi-filter", action="store_true",
                    help="footprint 사전 판정을 끈다(예전 동작). 판정이 의심될 때만.")
    ap.add_argument("--gpt-q", default="8", help="gpt 병렬도 (-q)")
    ap.add_argument("--gpt-c", default="14G", help="gpt 타일 캐시 (-c)")
    args = ap.parse_args()

    zips = [z for z in sorted(SLC_DIR.glob("*.zip")) if f"_{args.year}" in z.name]
    if not zips:
        raise FileNotFoundError(f"{rel(SLC_DIR)} 에 {args.year} 씬 zip이 없습니다.")

    if args.no_aoi_filter:
        targets, dropped = zips, []
    else:
        # 처리 전 판정: AOI와 안 겹치는 씬은 목록에서 뺀다(실패로 세지 않는다).
        targets = [z for z in zips if intersects(z, args.aoi, min_pct=args.min_overlap)]
        dropped = [z for z in zips if z not in targets]

    print(f"대상 SLC: {len(targets)}개 / 전체 {len(zips)}개 "
          f"(AOI {rel(args.aoi)} 서브셋)")
    for z in dropped:
        print(f"  제외(AOI 미교차): {z.name}")
    if not targets:
        raise SystemExit("AOI와 겹치는 씬이 없습니다. --no-aoi-filter 로 판정을 끌 수 있습니다.")

    aoi_wkt = aoi_wkt_from_geojson(args.aoi)
    run_batch(targets, RTC_SLC_DIR,
              lambda src, out: build_rtc_graph(src, out_dir=out, aoi_wkt=aoi_wkt),
              suffix="_rtc_db",
              gpt_options=["-q", args.gpt_q, "-c", args.gpt_c],
              tmp_prefix="slcrtc_", label="SLC 배치")


if __name__ == "__main__":
    main()
