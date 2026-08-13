# -*- coding: utf-8 -*-
"""저장소 안의 모든 경로를 **한 곳에서** 정의한다.

왜 필요한가
-----------
경로가 스크립트마다 `Path("downloads/rtc_grd_frost")`처럼 제각각 박혀 있으면
두 가지가 깨진다.

1. **작업 디렉터리 의존** — 저장소 루트에서 실행할 때만 맞는다. 하위 폴더에서
   돌리면 조용히 엉뚱한 곳을 보거나 빈 목록을 반환한다.
2. **폴더를 옮기면 전수 수정** — 산출물 폴더 하나를 바꾸는 데 수십 파일을
   고쳐야 한다.

여기서는 **이 파일의 위치**를 기준으로 저장소 루트를 찾아, 그 아래 상대경로로
모든 폴더를 정의한다. 절대경로(드라이브 문자)를 코드에 넣지 않으므로 저장소를
어디로 옮기든, 어느 디렉터리에서 실행하든 같은 곳을 가리킨다.

사용:
    from s1.core.paths import RTC_FROST_DIR, WATER_OTSU_DIR
    for tif in RTC_FROST_DIR.glob("*_rtc_db.tif"):
        ...

경로를 사람이 읽기 좋게 찍고 싶으면 rel()을 쓴다:
    print(rel(tif))     # downloads/rtc_grd_frost/S1C_....tif
"""

from __future__ import annotations

from pathlib import Path

# 이 파일은 <저장소루트>/s1/core/paths.py 이므로 루트는 부모의 부모의 부모.
PROJECT_DIR = Path(__file__).resolve().parents[2]

# --- 입력 자료 -------------------------------------------------------------
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
GRD_DIR = DOWNLOADS_DIR / "sentinel1_grd"          # 원본 GRD zip
SLC_DIR = DOWNLOADS_DIR / "sentinel1"              # 원본 SLC zip
DEM_DIR = DOWNLOADS_DIR / "dem"
HAND_DIR = DOWNLOADS_DIR / "hand"

# --- 전처리 산출물 ---------------------------------------------------------
RTC_GRD_DIR = DOWNLOADS_DIR / "rtc_grd"            # RTC (Refined Lee, 구버전)
RTC_FROST_DIR = DOWNLOADS_DIR / "rtc_grd_frost"    # RTC (Frost, 현행 기본)
RTC_SLC_DIR = DOWNLOADS_DIR / "rtc"                # SLC 기반 RTC
GTC_DIR = DOWNLOADS_DIR / "gtc"                    # GTC (대조군)
EXCLUDED_DIR = DOWNLOADS_DIR / "excluded_china_japan"

RTC_FROST_VH_DIR = DOWNLOADS_DIR / "rtc_grd_frost_vh"   # VH 편파 RTC
RTC_EXTDEM_DIR = DOWNLOADS_DIR / "rtc_extdem"           # external DEM으로 다시 구운 RTC
DEM_BASIN_DIR = DOWNLOADS_DIR / "dem_basin"             # 유역별로 구운 COP30
DEM_TEST_DIR = DOWNLOADS_DIR / "dem_test"
COP30_KOREA_VRT = DEM_DIR / "cop30_korea.vrt"

# --- 수체·홍수 산출물 ------------------------------------------------------
WATER_DIR = DOWNLOADS_DIR / "water"                # 고정 임계값(-16dB) 기반
WATER_OTSU_DIR = DOWNLOADS_DIR / "water_otsu"      # 타일기반 Otsu 기반
WATER_OTSU_GTC_DIR = DOWNLOADS_DIR / "water_otsu_gtc"
VRT_DIR = WATER_OTSU_DIR / "vrt"                   # 궤도별 dB 모자이크(가상)
OTSU_THRESHOLD_CSV = WATER_OTSU_DIR / "otsu_thresholds.csv"
WATER_AREA_CSV = WATER_OTSU_DIR / "water_area_perrow.csv"

# --- 벡터·보조 자료 --------------------------------------------------------
GEOJSON_DIR = PROJECT_DIR / "geojson"
KOREA_PENINSULA = GEOJSON_DIR / "Korea_Peninsula.geojson"
SOUTH_KOREA = GEOJSON_DIR / "South_Korea.geojson"
NORTH_KOREA = GEOJSON_DIR / "NK.geojson"
GRAPHS_DIR = PROJECT_DIR / "graphs"
DATA_DIR = PROJECT_DIR / "data"
DOCS_DIR = PROJECT_DIR / "docs"

# --- 형제 저장소(gee/) --------------------------------------------------
# GEE 홍수·수체 작업 폴더는 이 저장소의 **형제**다. 드라이브 문자를 코드에
# 박지 않도록 루트 기준으로 찾는다. 위치가 다르면 여기만 고치면 된다.
GEE_DIR = PROJECT_DIR.parent / "gee"
GEE_WATER_DIR = GEE_DIR / "Korea_WaterDetection_2025_2026"
BASIN_SHP = GEE_DIR / "대권역" / "WKMBBSN.shp"           # 남한 대권역 경계
DAM_BASIN_SHP = GEE_DIR / "전댐유역" / "전댐유역.shp"     # 댐 유역


def rel(path: Path | str) -> str:
    """저장소 루트 기준 상대경로 문자열. 로그·출력에 절대경로를 찍지 않기 위해.

    루트 밖의 경로(임시폴더 등)는 절대경로 그대로 돌려준다.
    """
    p = Path(path).resolve()
    try:
        return p.relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        return str(p)
