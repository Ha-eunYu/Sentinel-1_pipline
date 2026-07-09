# -*- coding: utf-8 -*-
"""
downloads/sentinel1 의 SLC zip들을 순차적으로 RTC(dB) 처리하는 배치 러너.

batch_grd_rtc.py의 SLC 버전. 홍수 AOI(Korea_flood_AOI + 0.1도) 서브셋으로
처리하므로 씬당 20분 내외. AOI와 교차하지 않는 씬은 Subset 단계에서 실패하며,
그 씬은 건너뛰고 다음으로 진행한다.

- 2022년 등 과거 참조용 씬은 제외하고 2026년 씬만 처리한다.
- 이미 산출물(downloads/rtc/<씬ID>_rtc_db.tif)이 있으면 건너뛴다 (재실행 안전).
- 입력 zip은 시스템 임시 폴더(C: SSD)로 복사 후 처리하고 복사본은 삭제한다.

실행:
    conda run -n s1_snappy python batch_slc_rtc.py
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from prepro_gpt import aoi_wkt_from_geojson, build_rtc_graph

SLC_DIR = Path("downloads/sentinel1")
OUT_DIR = Path("downloads/rtc")
PROJECT_DIR = Path(__file__).resolve().parent

# 이 접두어의 씬만 처리 (과거 참조용 2022 씬 등 제외)
YEAR_FILTER = "_2026"


def main() -> None:
    zips = [z for z in sorted(SLC_DIR.glob("*.zip")) if YEAR_FILTER in z.name]
    if not zips:
        raise FileNotFoundError(f"{SLC_DIR} 에 {YEAR_FILTER} 씬 zip이 없습니다.")

    aoi_wkt = aoi_wkt_from_geojson(PROJECT_DIR / "Korea_flood_AOI.geojson")
    print(f"대상 SLC: {len(zips)}개 (AOI 서브셋 적용)")

    done, skipped, failed = 0, 0, 0

    for i, zip_path in enumerate(zips, start=1):
        out_tif = OUT_DIR / f"{zip_path.stem}_rtc_db.tif"
        if out_tif.exists():
            print(f"[{i}/{len(zips)}] 건너뜀 (이미 처리됨): {zip_path.name}")
            skipped += 1
            continue

        print(f"[{i}/{len(zips)}] 처리 시작: {zip_path.name}")
        t0 = time.time()

        ssd_copy = Path(tempfile.gettempdir()) / zip_path.name
        try:
            shutil.copy2(zip_path, ssd_copy)
            graph = build_rtc_graph(ssd_copy, out_dir=OUT_DIR, aoi_wkt=aoi_wkt)
            graph.run(gpt_options=["-q", "8", "-c", "14G"])
            print(f"[{i}/{len(zips)}] 완료 ({(time.time() - t0) / 60:.1f}분): {out_tif.name}")
            done += 1
        except Exception as e:
            print(f"[{i}/{len(zips)}] 실패(AOI 미교차 씬일 수 있음): {zip_path.name} -> {e}")
            out_tif.unlink(missing_ok=True)
            failed += 1
        finally:
            ssd_copy.unlink(missing_ok=True)

    print(f"\n배치 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
