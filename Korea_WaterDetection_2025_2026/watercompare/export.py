"""watercompare.export — 결과물 로컬 내보내기(geemap 래퍼).

로컬로 가져올 것은 '결과물'뿐: 수면 마스크 폴리곤(GeoJSON)·통계(CSV).
원본 S1은 내려받지 않는다.
"""
from __future__ import annotations

import os

import ee
import geemap


def export_water_vector(mask: ee.Image, aoi: ee.Geometry, path: str,
                        scale: int = 10) -> None:
    """수면 마스크를 폴리곤(GeoJSON)으로 로컬 저장."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    vec = mask.reduceToVectors(
        geometry=aoi, scale=scale, maxPixels=int(1e10), eightConnected=True,
        labelProperty="water", reducer=ee.Reducer.countEvery())
    geemap.ee_export_vector(vec, path)
