# -*- coding: utf-8 -*-
"""
downloads/rtc 의 RTC dB GeoTIFF들을 촬영 날짜별로 묶어 VRT 모자이크를 만든다.

같은 날짜(같은 패스)의 이웃 프레임들은 촬영 시각이 수십 초 차이라 한 장처럼
취급할 수 있으므로, QGIS에는 개별 프레임 대신 이 VRT 하나만 올리면 된다.
VRT는 원본을 참조만 하는 가상 파일이라 생성이 즉시 끝나고 용량도 거의 없다.

파일명 규칙: prepro_gpt.py가 만드는 `<씬ID>_rtc_db.tif` 를 전제로 하며,
씬ID의 촬영 시작 시각(예: 20260701T213938)에서 날짜(20260701)를 뽑아 묶는다.

실행:
    conda run -n s1_snappy python build_rtc_mosaic.py            # 날짜별 전부
    conda run -n s1_snappy python build_rtc_mosaic.py 20260701   # 특정 날짜만

실제 병합 GeoTIFF가 필요하면(공유용 등) 만들어진 VRT를 변환:
    gdal_translate -of GTiff -co COMPRESS=DEFLATE <날짜>.vrt merged.tif
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RTC_DIR = Path("downloads/rtc")

# 씬ID에서 촬영 시작 날짜 추출 (예: S1C_IW_SLC__1SDV_20260701T213938_... -> 20260701)
DATE_PATTERN = re.compile(r"_(\d{8})T\d{6}_")


def main() -> None:
    if shutil.which("gdalbuildvrt") is None:
        raise RuntimeError(
            "'gdalbuildvrt'를 찾을 수 없습니다. gdal이 설치된 환경(s1_snappy)에서 실행해주세요."
        )

    only_date = sys.argv[1] if len(sys.argv) > 1 else None

    groups: dict[str, list[Path]] = defaultdict(list)
    for tif in sorted(RTC_DIR.glob("*_rtc_db.tif")):
        m = DATE_PATTERN.search(tif.name)
        if not m:
            print(f"건너뜀 (날짜를 못 찾음): {tif.name}")
            continue
        date = m.group(1)
        if only_date and date != only_date:
            continue
        groups[date].append(tif)

    if not groups:
        raise FileNotFoundError(
            f"{RTC_DIR} 에 대상 *_rtc_db.tif 가 없습니다"
            + (f" (날짜 {only_date})" if only_date else "")
        )

    for date, tifs in sorted(groups.items()):
        out_vrt = RTC_DIR / f"s1_rtc_db_mosaic_{date}.vrt"
        cmd = ["gdalbuildvrt", "-overwrite", str(out_vrt)] + [str(t) for t in tifs]
        print(f"[{date}] 프레임 {len(tifs)}개 -> {out_vrt.name}")
        for t in tifs:
            print(f"    - {t.name}")
        subprocess.run(cmd, check=True, capture_output=True)

    print("\n완료. QGIS에는 .vrt 파일을 올리면 됩니다.")


if __name__ == "__main__":
    main()
