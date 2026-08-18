# -*- coding: utf-8 -*-
"""footprint 하나를 사람 말로 바꾸는 부품 — "어디를 찍나"와 "무엇이 들어오나".

`scene_dashboard`(이미 촬영된 것)와 `acquisition_plan`(앞으로 촬영할 것)이
똑같이 필요로 해서 여기로 뺐다. 둘 다 **표준 라이브러리만** 쓰는 감시 계열
도구라, 이 모듈도 shapely·numpy를 쓰지 않는다. 점-다각형 판정은
`monitor_new_scenes`의 순수 파이썬 ray-casting을 그대로 쓴다.

- `SidoIndex` — 좌표 하나가 어느 시도인지 (`geojson/sido_simplified.geojson`).
- `describe_footprint` — 폴리곤 하나 → (한반도 겹침%, "충남·전북").
- `load_points` / `points_inside` — 관심 지점(댐·보) 목록과 포함 판정.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from s1.core.paths import GEOJSON_DIR, PROJECT_DIR
from s1.tools.monitor.monitor_new_scenes import Boundary, point_in_ring

SIDO_GEOJSON = GEOJSON_DIR / "sido_simplified.geojson"
DAM_POINTS_CSV = PROJECT_DIR / "data" / "dam_points_kwater.csv"


class SidoIndex:
    """시도 경계 묶음. monitor_new_scenes.Boundary 와 같은 1°격자 색인 방식이되,
    "안/밖"이 아니라 **어느 시도인지**를 돌려준다.

    경계는 `geojson/sido_simplified.geojson`(build_sido_geojson.py 산출물).
    파일이 없으면 위치 표시만 비고 나머지는 그대로 돈다.
    """

    def __init__(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.rings: list[tuple[str, list[tuple[float, float]]]] = []
        self.index: dict[tuple[int, int], list[int]] = {}
        for feat in data.get("features", []):
            name = feat.get("properties", {}).get("name", "?")
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Polygon":
                polys = [geom["coordinates"]]
            elif geom.get("type") == "MultiPolygon":
                polys = geom["coordinates"]
            else:
                continue
            for poly in polys:
                ring = [(float(p[0]), float(p[1])) for p in poly[0]]
                k = len(self.rings)
                self.rings.append((name, ring))
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                for cx in range(int(min(xs) // 1), int(max(xs) // 1) + 1):
                    for cy in range(int(min(ys) // 1), int(max(ys) // 1) + 1):
                        self.index.setdefault((cx, cy), []).append(k)

    def at(self, x: float, y: float) -> str | None:
        for k in self.index.get((int(x // 1), int(y // 1)), ()):
            name, ring = self.rings[k]
            if point_in_ring(x, y, ring):
                return name
        return None


def rings_of(geom: dict) -> list[list[tuple[float, float]]]:
    """GeoJSON (Multi)Polygon → 외곽 링 목록. 구멍은 무시한다."""
    if not geom:
        return []
    if geom.get("type") == "Polygon":
        polys = [geom["coordinates"]]
    elif geom.get("type") == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in poly[0]] for poly in polys]


def summarize_rings(rings: list[list[tuple[float, float]]],
                    boundary: Boundary | None, sido: SidoIndex | None,
                    step: float = 0.05, min_share: float = 8.0,
                    max_names: int = 3, clip: tuple | None = None
                    ) -> tuple[float, str]:
    """링 묶음을 (한반도 겹침%, "충남·전북")으로 요약한다.

    겹침%와 시도 판정을 **같은 표본 격자 한 번**으로 처리한다. 따로 돌리면
    격자를 두 번 뿌리게 되고, 이걸 수십 프레임에 반복하므로 차이가 체감된다.

    시도는 **육지 표본 중 비율**이 min_share% 이상인 것만 큰 순서로 최대
    max_names개. 프레임 대부분이 바다인 경우가 흔해 전체 표본 대비로 세면
    이름이 전부 잘려 나간다.

    `clip`(lon_min, lat_min, lon_max, lat_max)을 주면 그 상자 안만 표본한다.
    촬영계획의 datatake는 위도 10°를 넘는 긴 띠라, 한반도 상자로 잘라야 표본
    수가 수만 개로 튀지 않는다. 이때 겹침%는 **잘라낸 구간 기준**이다.
    """
    if not rings:
        return 0.0, ""
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if clip:
        x0, y0 = max(x0, clip[0]), max(y0, clip[1])
        x1, y1 = min(x1, clip[2]), min(y1, clip[3])
        if x0 > x1 or y0 > y1:
            return 0.0, ""

    n_in = n_hit = 0
    counts: dict[str, int] = {}
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if any(point_in_ring(x, y, r) for r in rings):
                n_in += 1
                if boundary is not None and boundary.contains(x, y):
                    n_hit += 1
                if sido is not None:
                    name = sido.at(x, y)
                    if name:
                        counts[name] = counts.get(name, 0) + 1
            x += step
        y += step

    pct = 100.0 * n_hit / n_in if n_in else 0.0
    total_land = sum(counts.values())
    names = ""
    if total_land:
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        keep = [n for n, c in ranked if 100.0 * c / total_land >= min_share]
        names = "·".join(keep[:max_names]) or ranked[0][0]
    return pct, names


def describe_footprint(geom: dict, boundary: Boundary | None,
                       sido: SidoIndex | None, step: float = 0.05,
                       min_share: float = 8.0, max_names: int = 3
                       ) -> tuple[float, str]:
    """GeoJSON geometry 판 `summarize_rings`(STAC footprint용)."""
    return summarize_rings(rings_of(geom), boundary, sido, step,
                           min_share, max_names)


def load_points(path: Path = DAM_POINTS_CSV) -> list[tuple[str, str, float, float]]:
    """관심 지점 CSV → [(구분, 지점명, lon, lat)]. 파일이 없으면 빈 목록."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append((row["구분"], row["지점명"],
                            float(row["경도"]), float(row["위도"])))
            except (KeyError, TypeError, ValueError):
                continue                      # 깨진 줄 하나로 전체를 버리지 않는다
    return out


def points_inside(rings: list[list[tuple[float, float]]],
                  points: list[tuple[str, str, float, float]]) -> list[str]:
    """링 안에 들어오는 지점 이름 목록(입력 순서 유지)."""
    return [name for _kind, name, lon, lat in points
            if any(point_in_ring(lon, lat, r) for r in rings)]
