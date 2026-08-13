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
    ap.add_argument(
        "--only",
        default="",
        help="쉼표로 구분한 씬 ID(4자리) 목록만 처리 (예: 08EE,9B8B). "
        "남한 footprint 씬만 골라 돌릴 때 사용.",
    )
    # gpt 자원 옵션: 실측상 gpt는 -q 8 을 줘도 1코어 남짓만 쓰고(단일 스레드 구간이
    # 병목) 디스크도 유휴라, 배치 2개를 병렬로 띄우는 편이 총 처리시간을 줄인다.
    # 그때 타일 캐시(-c)를 나눠 잡아야 RAM(32GB)을 넘기지 않는다.
    ap.add_argument("--gpt-q", default="8", help="gpt 병렬도 (-q). 기본 8")
    ap.add_argument("--gpt-c", default="14G", help="gpt 타일 캐시 (-c). 기본 14G. "
                    "배치를 병렬로 돌릴 땐 6~7G씩으로 나눌 것.")
    # 편파 (2026-07-31 추가)
    # 기존 rtc_grd_frost/ 65개는 전부 VV다. 그런데 GEE 수체탐지는 VH를 쓴다
    # (VH가 물/육지 대비가 안정적이고 풍파에 덜 민감). 두 산출물을 비교하면
    # RTC 차이가 아니라 **편파 차이**를 재게 된다 — 실측 오프셋 약 6 dB
    # (gee/Korea_WaterDetection_2025_2026/EDGE_OTSU_INITIAL_THRESHOLD_KR.md §2).
    # VH로 재처리해야 정식 RTC ↔ 근사 RTC 비교가 성립한다.
    ap.add_argument("--pol", default="VV", choices=["VV", "VH"],
                    help="편파. VH로 돌릴 땐 --out-dir도 따로 줄 것")
    ap.add_argument("--out-tag", default="",
                    help="산출물 파일명 접미사(예: _vh). 같은 폴더에 섞일 때 구분용")
    # External DEM (2026-08-10 추가)
    # SNAP에 demName="Copernicus 30m Global DEM"(자동 캐시)을 주면 **하구 수역을
    # 무효로 해석**해 결측을 만든다 — 영산강 제약면적의 20.2%가 그렇게 날아갔다.
    # 같은 COP30 값이라도 GeoTIFF로 구워 external로 물리면 결측이 0.00%다
    # (rtc_basin_extdem.py 모듈 주석의 2026-08-03 실측).
    # 하구가 포함된 유역(영산강 등)을 다룰 땐 반드시 --dem 을 줄 것.
    ap.add_argument("--dem", default="",
                    help="External DEM GeoTIFF 경로. 주면 SNAP 자동 캐시 DEM 대신 "
                         "이것을 쓴다. ⚠ VRT는 안 된다(Graph execution failed) — "
                         "GeoTIFF로 구울 것. DEM은 **분석 영역**만 덮으면 되고, "
                         "granule 가장자리가 DEM 밖이라 무효로 남는 건 정상이다.")
    ap.add_argument("--dem-nodata", type=float, default=-32768.0,
                    help="External DEM의 nodata (기본 -32768, COP30 관례)")
    ap.add_argument("--dem-egm", action="store_true",
                    help="External DEM에 EGM 지오이드 보정을 적용한다. **COP30에는 "
                         "주지 말 것** — COP30은 이미 타원체고라 이중 적용되면 "
                         "약 25 m 어긋난다. NGII처럼 정표고 DEM일 때만 켠다.")
    args = ap.parse_args()

    dem_file = Path(args.dem).resolve() if args.dem else None
    if dem_file is not None and not dem_file.exists():
        raise FileNotFoundError(f"External DEM이 없습니다: {dem_file}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zips = [z for z in GRD_DIR.glob("*.zip") if scene_date(z).startswith(args.month)]
    if args.only:
        wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
        # 파일명 형식(…_<씬ID>.zip / …_<씬ID>_COG.zip)이 섞여 있어 부분일치로 판정.
        zips = [z for z in zips if any(f"_{s}" in z.name.upper() for s in wanted)]
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR} 에 {args.month} 촬영 GRD zip이 없습니다.")
    # 최신 날짜 먼저 (동일 날짜는 파일명 역순)
    zips.sort(key=lambda z: (scene_date(z), z.name), reverse=not args.oldest_first)

    order = "오래된순" if args.oldest_first else "최신순"
    dem_desc = (f"external DEM {dem_file.name} (EGM {'on' if args.dem_egm else 'off'})"
                if dem_file else "Copernicus 30m Global DEM (SNAP 자동 캐시)")
    print(f"대상 GRD({args.month}, {order}): {len(zips)}개 -> {out_dir} "
          f"(Frost, {args.pol})")
    print(f"DEM: {dem_desc}")
    for z in zips:
        print(f"  {scene_date(z)}  {z.name}")

    done = skipped = failed = 0
    for i, zip_path in enumerate(zips, start=1):
        out_tif = out_dir / f"{zip_path.stem}_rtc_db{args.out_tag}.tif"
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
            graph = build_grd_rtc_graph(ssd_copy, out_dir=out_dir,
                                        polarization=args.pol,
                                        external_dem_file=dem_file,
                                        external_dem_nodata=args.dem_nodata,
                                        external_dem_apply_egm=args.dem_egm,
                                        out_tag=args.out_tag)  # speckle 기본=Frost
            graph.run(gpt_options=["-q", args.gpt_q, "-c", args.gpt_c])
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
