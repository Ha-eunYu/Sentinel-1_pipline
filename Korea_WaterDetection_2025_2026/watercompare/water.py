"""watercompare.water — S1 수면 마스크(스냅샷) + 면적 산출.

geeflood.sar와 달리 before/after 차이가 아니라 **한 기간의 후방산란을 그대로
Otsu 이진화**한다. 상시수체(JRC)를 제외하지 않는다 — 하천·저수지 자체가
측정 대상이기 때문(홍수 변화탐지는 반대로 상시수체를 제외해 신규 침수만 남김).
"""
from __future__ import annotations

import ee

from . import config

_D = config.DEFAULTS


def load_s1(aoi: ee.Geometry, start: str, end: str,
            pol: str = _D["pol"], orbit: str = _D["orbit"],
            speckle_m: int = _D["speckle_m"]) -> ee.Image:
    """궤도 고정 + 스펙클 완화한 S1 후방산란(dB) 평균 합성."""
    coll = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
        .filter(ee.Filter.eq("orbitProperties_pass", orbit))
        .select(pol)
        .filterDate(start, end)
        .map(lambda img: img.focalMean(speckle_m, "circle", "meters").rename(pol)
             .copyProperties(img, ["system:time_start"]))
    )
    return coll.mean().clip(aoi)


def otsu(histogram) -> ee.Number:
    """히스토그램에서 클래스간 분산(BSS) 최대화 임계 산출(geeflood.sar.otsu와 동일 공식)."""
    histogram = ee.Dictionary(histogram)
    counts = ee.Array(histogram.get("histogram"))
    means = ee.Array(histogram.get("bucketMeans"))
    size = means.length().get([0])
    total = counts.reduce(ee.Reducer.sum(), [0]).get([0])
    sum_ = means.multiply(counts).reduce(ee.Reducer.sum(), [0]).get([0])
    mean = sum_.divide(total)
    indices = ee.List.sequence(1, size)

    def bss(i):
        a_counts = counts.slice(0, 0, i)
        a_count = a_counts.reduce(ee.Reducer.sum(), [0]).get([0])
        a_means = means.slice(0, 0, i)
        a_mean = a_means.multiply(a_counts).reduce(ee.Reducer.sum(), [0]).get([0]).divide(a_count)
        b_count = total.subtract(a_count)
        b_mean = sum_.subtract(a_count.multiply(a_mean)).divide(b_count)
        return (a_count.multiply(a_mean.subtract(mean).pow(2))
                .add(b_count.multiply(b_mean.subtract(mean).pow(2))))

    return means.sort(ee.Array(indices.map(bss))).get([-1])


def water_mask(aoi: ee.Geometry, start: str, end: str, *,
               use_otsu: bool = _D["use_otsu"],
               thresh_abs: float = _D["thresh_abs"],
               min_connected: int = _D["min_connected"],
               verbose: bool = True):
    """한 기간의 S1 수면 마스크. 반환: (backscatter_img, water_mask)."""
    img = load_s1(aoi, start, end)

    if use_otsu:
        hist = img.reduceRegion(
            reducer=ee.Reducer.histogram(255, 0.1),
            geometry=aoi, scale=30, maxPixels=int(1e10), bestEffort=True
        ).get(_D["pol"])
        thr = ee.Number(otsu(hist))
        if verbose:
            print(f"  Otsu 임계(dB): {thr.getInfo():.2f}")
        mask = img.lt(thr)
    else:
        mask = img.lt(thresh_abs)

    water = mask.connectedPixelCount(25).gte(min_connected).selfMask()
    return img, water


def area_km2(mask: ee.Image, aoi: ee.Geometry, scale: int = 10) -> float:
    """마스크(1) 영역의 면적(km²). 위도 왜곡은 pixelArea로 보정."""
    r = (mask.multiply(ee.Image.pixelArea()).divide(1e6)
         .reduceRegion(reducer=ee.Reducer.sum(), geometry=aoi, scale=scale,
                       maxPixels=int(1e10)))
    return ee.Number(r.values().get(0)).getInfo()
