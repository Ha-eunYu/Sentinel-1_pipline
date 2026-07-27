# -*- coding: utf-8 -*-
"""
위성영상(SAR)의 실제 촬영 지역을 **bbox(외접 사각형)가 아니라 footprint
(실제 촬영 폴리곤)** 로 판정하는 공용 유틸.

왜 bbox가 아니라 footprint인가
-------------------------------
Sentinel-1 IW 프레임은 궤도 방위각만큼 기울어진 **평행사변형**이다. 이걸
경위도 축에 정렬된 bbox(minLon,minLat,maxLon,maxLat)로 감싸면, 프레임이
실제로 찍지 않은 삼각형 여백까지 "촬영 지역"에 포함된다. 그 여백이 하필
관심 경계(한반도)에 걸치면, **실제로는 100% 바다/외국인 프레임이 bbox 기준
으로는 '한반도를 찍었다'** 고 오판된다. 이 오판이 실제로 홍수 침수 수치를
아티팩트로 만든 사고가 있었다(SCENE_FOOTPRINT_REAUDIT_KR.md 참조).

이 모듈의 역할
--------------
CDSE STAC이 프레임마다 제공하는 실제 footprint 폴리곤(item.geometry)을
관심 경계 폴리곤과 대조하는 로직을 한 곳에 모은다. 두 계층을 제공한다.

1. **프레임 단위**(shapely, STAC footprint 대조)
   - load_boundary_union() / footprint_intersects() / footprint_overlap_ratio()
   - 다운로드 파이프라인에서 "이 프레임이 한반도를 찍었나?" 판정에 사용
     (stac/search_s1.py의 touches_korea가 이 로직을 씀).

2. **픽셀 단위**(순수 numpy, shapely 불필요)
   - load_exterior_rings() / points_in_rings()
   - 이미 처리된 래스터의 물 픽셀 등이 정말 경계 안에 있는지 사후 검증
     (verify_scene_footprint.py가 이 로직을 씀).

또한 bbox와 footprint의 차이를 수치로 보여주는 compare_bbox_vs_footprint()를
제공해, 특정 프레임에서 bbox 판정이 왜 틀리는지 근거를 남길 수 있다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent
GEOJSON_DIR = PROJECT_DIR / "geojson"
KOREA_PENINSULA = GEOJSON_DIR / "Korea_Peninsula.geojson"


# ---------------------------------------------------------------------------
# 0. bbox <-> polygon 변환
# ---------------------------------------------------------------------------
def bbox_to_polygon(bbox: list[float]) -> dict:
    """[minLon,minLat,maxLon,maxLat] -> GeoJSON Polygon(축 정렬 사각형)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]],
    }


# ---------------------------------------------------------------------------
# 1. 프레임 단위 판정 (shapely — STAC footprint 대조)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8)
def load_boundary_union(geojson_path: str | Path = KOREA_PENINSULA):
    """경계 GeoJSON(FeatureCollection/Feature/Geometry)을 하나의 shapely
    geometry로 union해 반환. 경로별로 캐시한다.

    shapely는 여기서만 import 한다(픽셀 단위 함수는 shapely 없이 동작)."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        geoms = [shape(data["geometry"])]
    else:
        geoms = [shape(data)]
    return unary_union(geoms)


def footprint_intersects(
    footprint: dict | None,
    boundary_geojson: str | Path = KOREA_PENINSULA,
) -> bool:
    """프레임 footprint(GeoJSON geometry)가 경계와 조금이라도 겹치면 True.

    footprint가 None이면(=STAC이 geometry를 안 준 경우) 판단 불가로 보고
    안전하게 True(통과)를 돌려준다 — 파이프라인이 프레임을 실수로 버리지
    않게 하기 위함. stac/search_s1.py의 touches_korea가 이 규약을 따른다."""
    if not footprint:
        return True
    from shapely.geometry import shape

    return shape(footprint).intersects(load_boundary_union(boundary_geojson))


def footprint_overlap_ratio(
    footprint: dict,
    boundary_geojson: str | Path = KOREA_PENINSULA,
) -> float:
    """footprint 면적 대비 경계와의 교집합 면적 비율(0.0~1.0).

    경위도 평면에서의 단순 면적비라 절대값은 근사지만, "0%인가 아닌가",
    "얼마나 걸쳤나"를 프레임끼리 비교하는 상대 지표로는 충분하다."""
    from shapely.geometry import shape

    fp = shape(footprint)
    if fp.area == 0:
        return 0.0
    inter = fp.intersection(load_boundary_union(boundary_geojson))
    return float(inter.area / fp.area)


def compare_bbox_vs_footprint(
    bbox: list[float],
    footprint: dict,
    boundary_geojson: str | Path = KOREA_PENINSULA,
) -> dict[str, Any]:
    """같은 프레임을 bbox로 판정할 때와 footprint로 판정할 때의 차이를
    수치로 반환. bbox는 통과시키지만 footprint는 0%인 경우가
    'bbox 오판'의 정체다."""
    boundary = load_boundary_union(boundary_geojson)
    from shapely.geometry import shape

    bbox_poly = shape(bbox_to_polygon(bbox))
    fp = shape(footprint)
    bbox_ratio = float(bbox_poly.intersection(boundary).area / bbox_poly.area) if bbox_poly.area else 0.0
    fp_ratio = float(fp.intersection(boundary).area / fp.area) if fp.area else 0.0
    return {
        "bbox_intersects": bbox_poly.intersects(boundary),
        "bbox_overlap_ratio": bbox_ratio,
        "footprint_intersects": fp.intersects(boundary),
        "footprint_overlap_ratio": fp_ratio,
        # bbox는 걸친다고 하는데 footprint는 안 걸치면 = bbox가 만든 유령 겹침
        "bbox_false_positive": bbox_poly.intersects(boundary) and not fp.intersects(boundary),
    }


# ---------------------------------------------------------------------------
# 2. 픽셀 단위 판정 (순수 numpy — shapely 불필요)
# ---------------------------------------------------------------------------
def load_exterior_rings(geojson_path: str | Path) -> list[np.ndarray]:
    """FeatureCollection/Feature/Geometry에서 모든 (Multi)Polygon 외곽 링을
    Nx2(lon,lat) 배열 목록으로 추출(구멍은 무시 — 해안선 검증엔 충분)."""
    data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        geoms = [data["geometry"]]
    else:
        geoms = [data]
    rings: list[np.ndarray] = []
    for g in geoms:
        if g["type"] == "Polygon":
            rings.append(np.asarray(g["coordinates"][0], dtype="float64"))
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                rings.append(np.asarray(poly[0], dtype="float64"))
    return rings


def points_in_rings(
    lons: np.ndarray,
    lats: np.ndarray,
    rings: list[np.ndarray],
) -> np.ndarray:
    """벡터화 ray-casting point-in-polygon. 점이 어느 링에든 들어가면 True
    (even-odd 규칙, 링별 OR). shapely 없이 대량 픽셀을 한 번에 처리한다."""
    inside = np.zeros(lons.shape, dtype=bool)
    for ring in rings:
        rx, ry = ring[:, 0], ring[:, 1]
        n = len(ring)
        j = n - 1
        acc = np.zeros(lons.shape, dtype=bool)
        for i in range(n):
            xi, yi, xj, yj = rx[i], ry[i], rx[j], ry[j]
            cond = (yi > lats) != (yj > lats)
            denom = yj - yi
            denom = np.where(denom == 0, 1e-12, denom)
            xints = (xj - xi) * (lats - yi) / denom + xi
            acc ^= cond & (lons < xints)
            j = i
        inside |= acc
    return inside


def fraction_inside(
    lons: np.ndarray,
    lats: np.ndarray,
    boundary_geojson: str | Path = KOREA_PENINSULA,
) -> float:
    """주어진 점들 중 경계 내부 비율(0.0~1.0). 물 픽셀 검증용 단축 함수."""
    rings = load_exterior_rings(boundary_geojson)
    return float(points_in_rings(np.asarray(lons), np.asarray(lats), rings).mean())


# ---------------------------------------------------------------------------
# 간단 자기검증 (python footprint_aoi.py)
# ---------------------------------------------------------------------------
def _demo_bbox_false_positive() -> None:
    """bbox 오판의 기하학적 원리를 합성 예제로 보여준다(실제 경계 불필요).

    경계 = 단위 정사각형 [0,1]x[0,1].
    footprint = 45° 기울어진 마름모(SAR 프레임처럼 축에 안 맞음)로, 경계와
    실제로는 전혀 안 겹친다. 그런데 그 footprint의 축 정렬 bbox는 경계의
    한 귀퉁이를 덮는다 -> bbox_false_positive = True."""
    from shapely.geometry import shape

    boundary = shape({"type": "Polygon", "coordinates": [[
        [0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]})
    footprint = {"type": "Polygon", "coordinates": [[
        [0.6, 1.6], [1.6, 0.6], [2.6, 1.6], [1.6, 2.6], [0.6, 1.6]]]}
    fp = shape(footprint)
    bbox_poly = shape(bbox_to_polygon([0.6, 0.6, 2.6, 2.6]))

    print("bbox 오판 기하 데모 (경계=[0,1]^2, footprint=기울어진 마름모):")
    print(f"  bbox 가 경계와 겹치나?      : {bbox_poly.intersects(boundary)}  <- '찍었다'고 오판")
    print(f"  footprint 가 경계와 겹치나? : {fp.intersects(boundary)}  <- 실제로는 안 찍음")
    print(f"  => bbox_false_positive       : {bbox_poly.intersects(boundary) and not fp.intersects(boundary)}")


if __name__ == "__main__":
    _demo_bbox_false_positive()

    # 픽셀 단위 데모: shapely 없이 동작(실제 한반도 경계 대조)
    if KOREA_PENINSULA.exists():
        lons = np.array([132.0, 127.0])  # 동해 먼바다 / 한반도 내륙 근처
        lats = np.array([34.0, 38.0])
        rings = load_exterior_rings(KOREA_PENINSULA)
        print("\n픽셀 단위(point-in-polygon) 데모 [먼바다, 내륙]:")
        print("  ", points_in_rings(lons, lats, rings))
    else:
        print(f"\n경계 파일 없음: {KOREA_PENINSULA} (픽셀 데모 생략)")
