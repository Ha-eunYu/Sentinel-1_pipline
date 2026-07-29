"""watercompare — 남한 4대강(낙동강·섬진강·영산강·금강) 수면적 전년 동기 비교.

`gee/geeflood`(북한 홍수 변화탐지)와 목적이 다르다:
    - geeflood.sar.detect_flood: before/after 차이에서 '신규' 침수만 남기고
      JRC 상시수체는 제외한다(변화탐지).
    - watercompare.water.water_mask: 각 시점의 '전체' 수면(하천·저수지 포함)을
      그대로 남긴다(상시수체 제외 안 함). 목적이 변화가 아니라 절대 수면적
      스냅샷 비교이기 때문.

향후 `F:/GEE`류 독립 프로젝트로 옮겨질 가능성을 고려해 부모 프로젝트 코드에
대한 import 의존 없이 폴더 상대로만 동작한다(geeflood와 동일한 설계 원칙).

서브모듈
    config   4대강 AOI(대략 bbox)·비교 기간·기본 파라미터
    auth     Earth Engine 초기화(geeflood.auth와 동일 로직, 독립 사본)
    water    S1 수면 마스크(Otsu, 상시수체 유지) + 면적(km2)
    export   결과물 로컬 내보내기(GeoJSON/CSV)
"""
from __future__ import annotations

from . import auth, config, export, water

__all__ = ["auth", "config", "export", "water"]
