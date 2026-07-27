# -*- coding: utf-8 -*-
"""footprint AOI 툴킷 패키지.

위성영상 촬영 지역을 bbox 대신 실제 footprint 폴리곤으로 판정하는 로직 모음.
배경·사용법은 FOOTPRINT_AOI_KR.md 참조.

파이프라인에서는 `from footprint import footprint_intersects`처럼 패키지에서
바로 가져다 쓴다(stac/search_s1.py). 픽셀 단위 함수는 shapely 없이 동작한다.
"""

from .footprint_aoi import (
    bbox_to_polygon,
    compare_bbox_vs_footprint,
    footprint_intersects,
    footprint_overlap_ratio,
    fraction_inside,
    load_boundary_union,
    load_exterior_rings,
    points_in_rings,
)

__all__ = [
    "bbox_to_polygon",
    "compare_bbox_vs_footprint",
    "footprint_intersects",
    "footprint_overlap_ratio",
    "fraction_inside",
    "load_boundary_union",
    "load_exterior_rings",
    "points_in_rings",
]
