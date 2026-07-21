# -*- coding: utf-8 -*-
"""
날짜별(패스별) 순수 수체 지도 생성 — baseline 비교 없이, 그 날짜의 프레임들만
모자이크해서 dB<임계값으로 수체를 판정한다.

detect_flood_grd_v2.py의 flood_water_total과의 차이: 그쪽은 baseline과의
교집합(valid = post 유효 AND baseline 유효)에 한정되지만, 이 스크립트는
baseline과 무관하게 **그 날짜에 관측된 전체 범위**에서 수체를 판정한다.
따라서 baseline 커버리지가 없는 지역(예: 북한 상당 부분)도 빠짐없이 나온다.

한 날짜에 여러 패스(예: 7/14의 09:31 UTC + 21:31 UTC)가 있으면 전부 하나의
모자이크로 합쳐진다 — "그 날짜에 관측된 모든 것"이 목적이라 패스를 구분하지
않는다(구분하려면 --hour-filter 등 별도 확장 필요, 지금은 불필요).

실행:
    conda run -n s1_snappy python build_water_per_date.py --dates 20260625,20260626
    conda run -n s1_snappy python build_water_per_date.py --dates 20260625 --db -18
"""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from build_baseline_composite_grd import RTC_GRD_DIR, scene_date

OUT_DIR = Path(__file__).resolve().parent / "downloads" / "water"

DB_THRESHOLD_DEFAULT = -16.0
NODATA_U8 = 255
CHUNK_ROWS = 512


def _vrt_sources_exist(vrt_path: Path) -> bool:
    """VRT가 참조하는 소스 tif가 전부 로컬에 실제로 존재하는지 확인.
    RTC 완료 후 NAS 업로드+로컬 삭제 운영 방식 때문에, 예전에 만든 VRT가
    이미 지워진 파일을 가리키는 "낡은 캐시" 상태가 될 수 있다."""
    import re
    text = vrt_path.read_text(encoding="utf-8", errors="ignore")
    for name in re.findall(r"<SourceFilename[^>]*>([^<]+)</SourceFilename>", text):
        if not (RTC_GRD_DIR / name).exists():
            return False
    return True


def per_date_mosaic(date: str) -> Path:
    vrt_path = RTC_GRD_DIR / f"s1_rtc_db_mosaic_{date}.vrt"
    if vrt_path.exists() and _vrt_sources_exist(vrt_path):
        return vrt_path
    if vrt_path.exists():
        print(f"[{date}] 낡은 VRT(삭제된 소스 참조) 재생성")
    all_tifs = sorted(RTC_GRD_DIR.glob("*_rtc_db.tif"))
    frames = [t for t in all_tifs if scene_date(t) == date]
    if not frames:
        raise FileNotFoundError(f"{date} 날짜의 _rtc_db.tif가 없습니다.")
    cmd = ["gdalbuildvrt", "-srcnodata", "0", "-vrtnodata", "0", "-overwrite",
           str(vrt_path), *[str(f) for f in frames]]
    print(f"[{date}] 모자이크 생성: {len(frames)}개 프레임")
    subprocess.run(cmd, check=True)
    return vrt_path


def water_for_date(date: str, db_threshold: float) -> None:
    mosaic = per_date_mosaic(date)
    out_path = OUT_DIR / f"flood_water_total_{date}.tif"
    if out_path.exists():
        print(f"[{date}] 이미 존재, 건너뜀: {out_path.name}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(mosaic) as src:
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
        with rasterio.open(out_path, "w", **profile) as dst:
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
    print(f"[{date}] 격자 {profile['width']}x{profile['height']}px, "
          f"커버리지 {100*n_valid/total_px:.1f}%, 수체 {n_water*px_area_km2:,.2f} km^2 "
          f"-> {out_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="날짜별(패스별) baseline-무관 순수 수체 지도")
    parser.add_argument("--dates", required=True, help="쉼표구분 YYYYMMDD 목록")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    args = parser.parse_args()

    for date in args.dates.split(","):
        water_for_date(date.strip(), args.db)


if __name__ == "__main__":
    main()
