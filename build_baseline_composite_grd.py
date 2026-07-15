# -*- coding: utf-8 -*-
"""
pre-event(홍수 전, ~7/3까지) GRD dB 관측을 "최신 관측 우선"으로 합성한 뒤
baseline 수체 지도를 만든다.

이전에는 이 합성 VRT(s1_rtc_db_composite_latest_pre.vrt)를 gdalbuildvrt를
직접 호출해 수동으로 만들었다 (재현 불가). 이 스크립트는 그 과정을
downloads/rtc_grd/*_rtc_db.tif 에서 시작해 전부 자동화한다:

  1) 파일명의 날짜(YYYYMMDD)를 파싱해 PRE_EVENT_CUTOFF 이하만 선택
  2) 날짜별로 묶어 프레임 모자이크 VRT 생성 (s1_rtc_db_mosaic_<날짜>.vrt,
     이미 있으면 재사용)
  3) 날짜 오름차순으로 gdalbuildvrt에 넘겨 합성 VRT 생성
     (gdalbuildvrt는 "나중에 준 파일이 이긴다" -> 최신 관측 우선이 됨)
  4) 합성 dB에 임계값(dB < -16, HAND 미사용)을 적용해 baseline 수체 지도 저장

산출물 (모두 downloads/rtc_grd 또는 downloads/water):
  s1_rtc_db_mosaic_<날짜>.vrt         날짜별 프레임 모자이크 (이미 있으면 스킵)
  s1_rtc_db_composite_latest_pre.vrt  최신관측 우선 pre-event 합성
  baseline_water_latest_grd.tif       baseline 수체 지도 (0/1, 255=미관측)

실행:
    conda run -n s1_snappy python build_baseline_composite_grd.py
    conda run -n s1_snappy python build_baseline_composite_grd.py --db -18
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
RTC_GRD_DIR = PROJECT_DIR / "downloads" / "rtc_grd"
OUT_WATER_DIR = PROJECT_DIR / "downloads" / "water"

COMPOSITE_VRT = RTC_GRD_DIR / "s1_rtc_db_composite_latest_pre.vrt"
BASELINE_OUT = OUT_WATER_DIR / "baseline_water_latest_grd.tif"

PRE_EVENT_CUTOFF = "20260703"  # 이 날짜까지 포함 (홍수일 7/8 이전)
DB_THRESHOLD_DEFAULT = -16.0
NODATA_U8 = 255
CHUNK_ROWS = 256  # 동시 실행 중인 gpt 프로세스와 메모리 경쟁 시 작게 유지

SCENE_DATE_RE = re.compile(r"_(\d{8})T\d{6}_")


def scene_date(tif: Path) -> str | None:
    m = SCENE_DATE_RE.search(tif.name)
    return m.group(1) if m else None


def build_per_date_vrts(dates: list[str]) -> dict[str, Path]:
    """날짜별 모자이크 VRT를 만든다 (이미 있으면 재사용)."""
    all_tifs = sorted(RTC_GRD_DIR.glob("*_rtc_db.tif"))
    by_date: dict[str, list[Path]] = defaultdict(list)
    for tif in all_tifs:
        d = scene_date(tif)
        if d in dates:
            by_date[d].append(tif)

    vrts: dict[str, Path] = {}
    for d in dates:
        vrt_path = RTC_GRD_DIR / f"s1_rtc_db_mosaic_{d}.vrt"
        if vrt_path.exists():
            vrts[d] = vrt_path
            continue
        frames = by_date.get(d, [])
        if not frames:
            raise FileNotFoundError(f"{d} 날짜의 _rtc_db.tif가 없습니다.")
        cmd = [
            "gdalbuildvrt", "-srcnodata", "0", "-vrtnodata", "0",
            str(vrt_path), *[str(f) for f in frames],
        ]
        print(f"[{d}] 모자이크 생성: {len(frames)}개 프레임")
        subprocess.run(cmd, check=True)
        vrts[d] = vrt_path
    return vrts


def build_composite(vrts: dict[str, Path]) -> Path:
    """날짜 오름차순으로 합성 VRT 생성 (나중 파일이 이겨 최신관측 우선)."""
    ordered_dates = sorted(vrts.keys())
    cmd = [
        "gdalbuildvrt", "-srcnodata", "0", "-vrtnodata", "0",
        str(COMPOSITE_VRT), *[str(vrts[d]) for d in ordered_dates],
    ]
    print(f"합성 순서(오래된->최신, 나중이 이김): {ordered_dates}")
    subprocess.run(cmd, check=True)
    return COMPOSITE_VRT


def apply_threshold(composite_vrt: Path, db_threshold: float) -> None:
    OUT_WATER_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(composite_vrt) as src:
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width,
            "count": 1, "dtype": "uint8", "crs": src.crs, "transform": src.transform,
            "nodata": NODATA_U8, "compress": "DEFLATE", "tiled": True,
            "bigtiff": "IF_SAFER",
        }
        res_deg = abs(src.transform.a)
        center_lat = (src.bounds.bottom + src.bounds.top) / 2
        px_area_km2 = (res_deg * 111_320.0) * (res_deg * 111_320.0 * np.cos(np.radians(center_lat))) / 1e6

        n_water = n_valid = 0
        print(f"격자: {src.width} x {src.height} px, 임계값 dB < {db_threshold}, HAND 미사용")

        with rasterio.open(BASELINE_OUT, "w", **profile) as dst:
            for row0 in range(0, src.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, src.height - row0)
                win = Window(0, row0, src.width, nrows)
                db = src.read(1, window=win).astype("float32")
                valid = np.isfinite(db) & (db != 0)
                water = valid & (db < db_threshold)
                dst.write(np.where(valid, water.astype("uint8"), NODATA_U8), 1, window=win)
                n_water += int(water.sum())
                n_valid += int(valid.sum())

    total_px = profile["height"] * profile["width"]
    print(f"커버리지: {100 * n_valid / total_px:.1f}%")
    print(f"baseline 수체 면적: {n_water * px_area_km2:,.2f} km^2")
    print(f"저장: {BASELINE_OUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description="pre-event GRD 최신관측 우선 baseline 생성")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    parser.add_argument("--cutoff", default=PRE_EVENT_CUTOFF, help="이 날짜(YYYYMMDD)까지 포함")
    args = parser.parse_args()

    all_tifs = sorted(RTC_GRD_DIR.glob("*_rtc_db.tif"))
    dates = sorted({d for t in all_tifs if (d := scene_date(t)) and d <= args.cutoff})
    print(f"pre-event 대상 날짜({args.cutoff} 이하): {dates}")

    vrts = build_per_date_vrts(dates)
    composite = build_composite(vrts)
    apply_threshold(composite, args.db)


if __name__ == "__main__":
    main()
