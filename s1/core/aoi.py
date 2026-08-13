# -*- coding: utf-8 -*-
"""원본 zip의 **실제 촬영 footprint**로 관심지역 커버율을 재는 모듈.

왜 bbox가 아니라 footprint인가
------------------------------
Sentinel-1 IW 프레임은 궤도 방위각만큼 기울어진 평행사변형이다. 경위도 축에
정렬된 bbox로 감싸면 실제로 찍지 않은 삼각형 여백까지 "촬영 지역"이 된다.
그 여백이 관심 경계에 걸치면 **100% 바다인 프레임이 "육지를 찍었다"로 오판**
된다(SCENE_FOOTPRINT_REAUDIT_KR.md의 실제 사고).

SAFE 안의 `preview/map-overlay.kml`에는 그 프레임의 실제 촬영 폴리곤이 들어
있다. 여기서는 zip을 풀지 않고 그것만 읽어 경계 폴리곤과 대조한다.

측정 방법
---------
1. footprint 폴리곤의 bbox에 일정 간격(기본 0.01°) 격자점을 뿌린다.
2. 격자점 중 footprint 내부인 것만 남긴다(ray-casting).
3. 그중 관심 경계 내부 비율 = 커버율(%).

shapely가 없는 환경에서도 돌도록 순수 numpy 구현(s1.footprint.footprint_aoi)의
point-in-polygon을 쓴다.

사용:
    from s1.core.aoi import coverage_percent, south_korea_scenes
    pct = coverage_percent(zip_path)                    # 남한 커버율
    keep = south_korea_scenes(GRD_DIR.glob("*2026*.zip"), min_pct=1.0)
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np

from s1.core.paths import SOUTH_KOREA
from s1.footprint.footprint_aoi import load_exterior_rings, points_in_rings

KML_RE = re.compile(r"<coordinates>(.*?)</coordinates>", re.S)
GRID_STEP_DEG = 0.01     # 약 1 km. 커버율 판정에는 이 정도면 충분하다.


def footprint_ring(zip_path: Path | str) -> np.ndarray:
    """zip 안 preview/map-overlay.kml에서 촬영 폴리곤 외곽 링(Nx2, lon/lat)."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith("preview/map-overlay.kml")]
        if not names:
            raise FileNotFoundError(f"map-overlay.kml 없음: {zip_path}")
        text = z.read(names[0]).decode("utf-8", "ignore")
    m = KML_RE.search(text)
    if not m:
        raise ValueError(f"kml에 <coordinates>가 없음: {zip_path}")
    ring = np.asarray(
        [[float(v) for v in c.split(",")[:2]] for c in m.group(1).split()]
    )
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[0]])
    return ring


def coverage_percent(
    zip_path: Path | str,
    boundary_geojson: Path | str = SOUTH_KOREA,
    *,
    step_deg: float = GRID_STEP_DEG,
) -> float:
    """이 프레임이 경계 폴리곤을 덮는 비율(%). 기본 경계는 남한.

    반환값은 **프레임 면적 대비** 경계 내부 비율이다("이 촬영의 몇 %가 남한
    이냐"). 경계 전체 중 몇 %를 찍었냐가 아니다.
    """
    ring = footprint_ring(zip_path)
    lon0, lat0 = ring.min(axis=0)
    lon1, lat1 = ring.max(axis=0)
    gx, gy = np.meshgrid(
        np.arange(lon0, lon1, step_deg), np.arange(lat0, lat1, step_deg)
    )
    gx, gy = gx.ravel(), gy.ravel()
    inside_fp = points_in_rings(gx, gy, [ring])
    if not inside_fp.any():
        return 0.0
    rings = load_exterior_rings(boundary_geojson)
    return float(points_in_rings(gx[inside_fp], gy[inside_fp], rings).mean() * 100)


def south_korea_scenes(
    zips: Iterable[Path],
    *,
    min_pct: float = 1.0,
    boundary_geojson: Path | str = SOUTH_KOREA,
) -> dict[Path, float]:
    """남한 커버율이 min_pct 이상인 zip만 {경로: 커버율%}로 돌려준다.

    수체 판별 대상 씬을 고를 때 쓴다. 커버율 0%인 프레임까지 처리하면
    RTC 시간(씬당 15~80분)을 그냥 버린다.
    """
    out: dict[Path, float] = {}
    for z in zips:
        pct = coverage_percent(z, boundary_geojson)
        if pct >= min_pct:
            out[Path(z)] = pct
    return out
