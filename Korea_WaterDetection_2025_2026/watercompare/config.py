"""watercompare.config — 4대강 AOI·비교 기간·기본 파라미터.

값을 바꿀 때 여기 한 곳만 고치면 river_water_area.py 전체에 반영된다.
"""
from __future__ import annotations

import os

# --- 산출물 출력 폴더 -----------------------------------------------------
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

# --- 수체탐지 기본 파라미터 ------------------------------------------------
DEFAULTS = {
    "pol": "VH",              # 수체탐지 편파(VH: 물/육지 대비 안정)
    "orbit": "ASCENDING",     # TODO: 4대강 전역에서 ASC 커버리지 실제 확인 필요.
                               # 유역별로 궤도가 다르면 비교 왜곡 → 지역별 오버라이드 고려.
    "use_otsu": True,         # 임계 자동화(시점마다 배경 조건이 다를 수 있어 고정임계보다 안정)
    "thresh_abs": -18.0,      # use_otsu=False일 때 절대 수체 임계(dB)
    "speckle_m": 30,          # 스펙클 완화 커널(m)
    "min_connected": 8,       # 소면적 노이즈 제거(연결픽셀 하한)
}

# --- 비교 기간: 올해(2026-07) vs 작년 동기(2025-07) ------------------------
# 관측 가능한 최신 S1 장면에 맞춰 실행 시점에 좁혀서 조정할 것.
PERIODS = {
    "this_year": ("2026-07-01", "2026-07-28"),
    "last_year": ("2025-07-01", "2025-07-28"),
}

# --- 4대강 유역 AOI([W,S,E,N], 대략 bbox) ----------------------------------
# 주의: 실제 유역경계 폴리곤이 아니라 근사 사각형이다(geeflood REGIONS와 동일한
# 1차 근사 관행). 인접 유역·해상 포함 오차가 있을 수 있으므로 정식 보고 전
# 환경부 표준유역도/K-water 유역경계 또는 GEE WWF/HydroSHEDS BasinATLAS로
# 교체할 것(footprint/ 실경계 판정 방식 참고).
BASINS = {
    "nakdong":  {"name_kr": "낙동강", "aoi": [127.90, 35.00, 129.50, 37.20]},
    "seomjin":  {"name_kr": "섬진강", "aoi": [127.00, 34.90, 127.90, 35.70]},
    "yeongsan": {"name_kr": "영산강", "aoi": [126.30, 34.70, 127.10, 35.40]},
    "geum":     {"name_kr": "금강",   "aoi": [126.50, 35.90, 127.90, 36.90]},
}

# --- 댐 저수량(TODO) -------------------------------------------------------
# 박사님 댐 리스트 도착 전까지 비워둠. 주의: S1 SAR로는 '수면적'만 나온다.
# 저수량(m3)은 수위-면적-용적 관계(rating curve/bathymetry)가 있어야 하므로
# SAR 단독 산정 불가 — 리스트 확보 시 공식 저수율(K-water 등) 병행 여부부터
# 확인 후 별도 모듈(dam_storage.py 등)로 설계한다. 여기서 미리 코드화하지 않음.
DAMS: dict = {}

# --- 인증(비대화식 실행 시 환경변수) -------------------------------------
AUTH = {
    "ee_project": os.environ.get("EE_PROJECT"),
    "sa_key": os.environ.get("EE_SA_KEY"),
    "sa_email": os.environ.get("EE_SA_EMAIL"),
}
