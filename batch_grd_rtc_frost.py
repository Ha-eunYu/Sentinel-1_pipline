# -*- coding: utf-8 -*-
"""
7월 GRD를 **Frost**로 RTC 재처리하는 배치 러너 — 기존 산출물은 건드리지 않고
**새 폴더**(기본 downloads/rtc_grd_frost)에 저장한다.

배경: 2026-07-23 파이프라인 기본 speckle 필터를 Refined Lee → Frost로 바꿨다
(FILTER_COMPARISON_KR.md §6). 기존 rtc_grd/의 RTC 65개는 Refined Lee라, 필터를
일관되게 맞추려면 Frost로 재처리가 필요하다. 이 스크립트는 그 재처리를
**기존 rtc_grd를 지우지 않고** 별도 폴더에 쌓는다(비교·롤백 가능).

- speckle 필터: build_grd_rtc_graph 기본값(=Frost)을 그대로 사용.
- 대상: 촬영일이 --month(기본 202607)로 시작하는 sentinel1_grd/*.zip.
- 순서: **최신 날짜 먼저**(--oldest-first 로 반대).
- 임시복사: C: SSD의 씬별 임시 하위폴더(원본 파일명 유지 → 산출물 이름 깔끔,
  동시실행 충돌 없음). 처리 후 임시폴더 삭제.
- 이미 새 폴더에 산출물이 있으면 건너뜀(중간에 끊겨도 이어서 재실행 가능).

실행:
    conda run -n s1_snappy python batch_grd_rtc_frost.py
    conda run -n s1_snappy python batch_grd_rtc_frost.py --month 202607 --out-dir downloads/rtc_grd_frost
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import time
from pathlib import Path

from prepro_grd_gpt import build_grd_rtc_graph

GRD_DIR = Path("downloads/sentinel1_grd")
DATE_RE = re.compile(r"_(\d{8})T\d{6}_")


def scene_date(p: Path) -> str:
    m = DATE_RE.search(p.name)
    return m.group(1) if m else "00000000"


def main() -> None:
    ap = argparse.ArgumentParser(description="7월 GRD Frost RTC 재처리(새 폴더, 최신순)")
    ap.add_argument("--out-dir", default="downloads/rtc_grd_frost")
    ap.add_argument("--month", default="202607", help="이 접두사로 시작하는 촬영일만 (예: 202607)")
    ap.add_argument("--oldest-first", action="store_true", help="기본은 최신순; 이 옵션이면 오래된 순")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zips = [z for z in GRD_DIR.glob("*.zip") if scene_date(z).startswith(args.month)]
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR} 에 {args.month} 촬영 GRD zip이 없습니다.")
    # 최신 날짜 먼저 (동일 날짜는 파일명 역순)
    zips.sort(key=lambda z: (scene_date(z), z.name), reverse=not args.oldest_first)

    order = "오래된순" if args.oldest_first else "최신순"
    print(f"대상 GRD({args.month}, {order}): {len(zips)}개 -> {out_dir} (Frost)")
    for z in zips:
        print(f"  {scene_date(z)}  {z.name}")

    done = skipped = failed = 0
    for i, zip_path in enumerate(zips, start=1):
        out_tif = out_dir / f"{zip_path.stem}_rtc_db.tif"
        if out_tif.exists():
            print(f"[{i}/{len(zips)}] 건너뜀 (이미 처리됨): {out_tif.name}")
            skipped += 1
            continue

        print(f"[{i}/{len(zips)}] 처리 시작: {zip_path.name}")
        t0 = time.time()
        # 씬별 임시 하위폴더(원본 파일명 유지). 파일명 접두사 대신 폴더로 격리해
        # 산출물 이름이 <씬ID>_rtc_db.tif 로 깔끔하게 나오고 동시실행 충돌도 없다.
        tmpdir = Path(tempfile.mkdtemp(prefix="frostrtc_"))
        ssd_copy = tmpdir / zip_path.name
        try:
            shutil.copy2(zip_path, ssd_copy)
            graph = build_grd_rtc_graph(ssd_copy, out_dir=out_dir)  # speckle 기본=Frost
            graph.run(gpt_options=["-q", "8", "-c", "14G"])
            print(f"[{i}/{len(zips)}] 완료 ({(time.time() - t0) / 60:.1f}분): {out_tif.name}")
            done += 1
        except Exception as e:
            print(f"[{i}/{len(zips)}] 실패: {zip_path.name} -> {e}")
            out_tif.unlink(missing_ok=True)
            failed += 1
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n배치 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
