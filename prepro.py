# -*- coding: utf-8 -*-
"""
Sentinel-1 IW SLC -> RTC(Radiometric Terrain Correction) 전처리.

흐름 (서브스와스 IW1/IW2/IW3 각각):
  Open SLC -> Apply-Orbit-File -> TOPSAR-Split -> Thermal Noise Removal
  -> Calibration(Beta0) -> TOPSAR-Deburst
  -> [서브스와스 3개를 TOPSAR-Merge로 병합]
  -> Multilook -> Speckle-Filter(Refined Lee) -> Terrain-Flattening
  -> Terrain-Correction -> dB 변환

Terrain-Flattening(지형 기인 radiometric 왜곡 보정)은 Beta0로 보정된 밴드를
입력으로 요구하므로, Calibration 단계는 Gamma0가 아니라 Beta0를 출력한다.
Terrain-Flattening과 Terrain-Correction은 서로 대체 관계가 아니라 순서대로
둘 다 실행해야 방사보정 + 기하보정(geocoding)이 모두 끝난 RTC 산출물이 된다.

실행하려면 ESA SNAP Desktop이 설치되어 있고 snappy-conf로 esa_snappy가
연결되어 있어야 한다 (environment_snappy.yml 상단 주석 참고). 수체 탐지는
이 스크립트의 범위가 아니며, dB 산출물을 입력으로 별도 스크립트에서 진행한다.
"""

from __future__ import annotations

from pathlib import Path

import esa_snappy
from esa_snappy import GPF, HashMap, ProductIO, jpy

GPF.getDefaultInstance().getOperatorSpiRegistry().loadOperatorSpis()

BandDescriptor = jpy.get_type("org.esa.snap.core.gpf.common.BandMathsOp$BandDescriptor")


def read_product(path: str | Path):
    return ProductIO.readProduct(str(path))


def write_product(product, path: str | Path, fmt: str = "GeoTIFF") -> None:
    ProductIO.writeProduct(product, str(path), fmt)


def apply_orbit_file(product):
    params = HashMap()
    params.put("orbitType", "Sentinel Precise (Auto Download)")
    params.put("polyDegree", 3)
    params.put("continueOnFail", False)
    return GPF.createProduct("Apply-Orbit-File", params, product)


def topsar_split(
    product,
    subswath: str,
    polarization: str,
    first_burst_index: int | None = None,
    last_burst_index: int | None = None,
):
    params = HashMap()
    params.put("subswath", subswath)
    params.put("selectedPolarisations", polarization)
    if first_burst_index is not None:
        params.put("firstBurstIndex", int(first_burst_index))
    if last_burst_index is not None:
        params.put("lastBurstIndex", int(last_burst_index))
    return GPF.createProduct("TOPSAR-Split", params, product)


def thermal_noise_removal(product):
    params = HashMap()
    params.put("removeThermalNoise", True)
    return GPF.createProduct("ThermalNoiseRemoval", params, product)


def calibration(product, polarization: str):
    """RTC 흐름의 입력은 Beta0여야 하므로 Beta0만 출력한다."""
    params = HashMap()
    params.put("selectedPolarisations", polarization)
    params.put("outputBetaBand", True)
    params.put("outputSigmaBand", False)
    params.put("outputGammaBand", False)
    params.put("outputImageScaleInDb", False)
    return GPF.createProduct("Calibration", params, product)


def topsar_deburst(product):
    return GPF.createProduct("TOPSAR-Deburst", HashMap(), product)


def topsar_merge(products: list, polarization: str):
    """Deburst가 끝난 서브스와스(IW1/IW2/IW3) 산출물들을 하나의 연속된
    스와스 산출물로 합친다. 입력은 반드시 TOPSAR-Deburst 이후여야 한다.
    """
    params = HashMap()
    params.put("selectedPolarisations", polarization)
    source_products = jpy.array("org.esa.snap.core.datamodel.Product", len(products))
    for i, p in enumerate(products):
        source_products[i] = p
    return GPF.createProduct("TOPSAR-Merge", params, source_products)


def multilook(product, range_looks: int = 1, azimuth_looks: int = 4):
    params = HashMap()
    params.put("nRgLooks", int(range_looks))
    params.put("nAzLooks", int(azimuth_looks))
    return GPF.createProduct("Multilook", params, product)


def speckle_filter(product, filter_name: str = "Refined Lee", num_looks: int = 4):
    """SAR 스펙클(speckle) 잡음 제거. RTC(방사/기하보정)와는 별개의 단계이며,
    이후 dB 임계값 기반 수체 탐지에서 오탐을 줄이기 위해 Multilook 다음,
    Terrain-Flattening 이전에 적용한다. num_looks는 Multilook 적용 후의
    등가 룩 수(range_looks * azimuth_looks)를 넣는다.
    """
    params = HashMap()
    params.put("filter", filter_name)
    params.put("numLooksStr", str(num_looks))
    return GPF.createProduct("Speckle-Filter", params, product)


def terrain_flattening(product, dem_name: str = "Copernicus 30m"):
    """Beta0 입력 -> 지형 기인 radiometric 왜곡 보정 -> Gamma0(terrain-flattened)."""
    params = HashMap()
    params.put("demName", dem_name)
    # 로컬 DEM(dem.tif)을 쓰려면 위 demName 대신 아래 4줄의 주석을 풀어서 사용:
    # params.put("demName", "External DEM")
    # params.put("externalDEMFile", "/path/to/dem.tif")
    # params.put("externalDEMNoDataValue", -9999.0)
    # params.put("externalDEMApplyEGM", True)  # dem.tif가 타원체고가 아니라면 True
    params.put("demResamplingMethod", "BILINEAR_INTERPOLATION")
    return GPF.createProduct("Terrain-Flattening", params, product)


def terrain_correction(product, dem_name: str = "Copernicus 30m", pixel_spacing_m: float = 10.0):
    """기하보정(geocoding/orthorectification). RTC의 마지막 필수 단계."""
    params = HashMap()
    params.put("demName", dem_name)
    # 로컬 DEM(dem.tif)을 쓰려면 위 demName 대신 아래 4줄의 주석을 풀어서 사용:
    # params.put("demName", "External DEM")
    # params.put("externalDEMFile", "/path/to/dem.tif")
    # params.put("externalDEMNoDataValue", -9999.0)
    # params.put("externalDEMApplyEGM", True)  # dem.tif가 타원체고가 아니라면 True
    params.put("pixelSpacingInMeter", float(pixel_spacing_m))
    params.put("imgResamplingMethod", "BILINEAR_INTERPOLATION")
    params.put("demResamplingMethod", "BILINEAR_INTERPOLATION")
    params.put("saveSelectedSourceBand", True)
    return GPF.createProduct("Terrain-Correction", params, product)


def linear_to_db(product, source_band: str):
    params = HashMap()
    target = BandDescriptor()
    target.name = f"{source_band}_dB"
    target.type = "float32"
    target.expression = f"10 * log10(max({source_band}, 1e-10))"
    descriptors = jpy.array("org.esa.snap.core.gpf.common.BandMathsOp$BandDescriptor", 1)
    descriptors[0] = target
    params.put("targetBands", descriptors)
    return GPF.createProduct("BandMaths", params, product)


def find_band(product, *name_fragments: str) -> str:
    band_names = list(product.getBandNames())
    for band_name in band_names:
        if any(fragment.lower() in band_name.lower() for fragment in name_fragments):
            return band_name
    raise ValueError(f"{name_fragments}와(과) 일치하는 밴드를 찾을 수 없음: {band_names}")


def process_subswath(raw_product, subswath: str, polarization: str):
    """서브스와스 하나에 대해 Split -> ThermalNoiseRemoval -> Calibration(Beta0)
    -> Deburst 까지 처리한다 (Merge 이전 단계).
    """
    p = topsar_split(raw_product, subswath=subswath, polarization=polarization)
    p = thermal_noise_removal(p)
    p = calibration(p, polarization=polarization)
    p = topsar_deburst(p)
    return p


def process_s1_slc_to_rtc(
    slc_path: str | Path,
    out_dir: str | Path,
    *,
    subswaths: tuple[str, ...] = ("IW1", "IW2", "IW3"),
    polarization: str = "VV",
    dem_name: str = "Copernicus 30m",
    pixel_spacing_m: float = 10.0,
    range_looks: int = 1,
    azimuth_looks: int = 4,
    apply_speckle_filter: bool = True,
    speckle_filter_name: str = "Refined Lee",
):
    """Sentinel-1 IW SLC 한 장을 RTC(Gamma0, 지형보정+기하보정 완료) + dB로 변환.

    subswaths에 지정된 서브스와스(기본값: IW1/IW2/IW3 전체)를 각각 Split ->
    ThermalNoiseRemoval -> Calibration -> Deburst까지 처리한 뒤 TOPSAR-Merge로
    하나의 산출물로 합친다. AOI가 걸리는 서브스와스만 알고 있다면 예를 들어
    subswaths=("IW2",)처럼 좁혀서 처리 시간을 줄일 수 있다.

    Multilook 다음에는 기본적으로 Refined Lee 스펙클 필터를 적용한다 (이후
    dB 임계값 기반 수체 탐지에서 스펙클 노이즈로 인한 오탐을 줄이기 위함).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_product = read_product(slc_path)
    raw_product = apply_orbit_file(raw_product)

    subswath_products = [
        process_subswath(raw_product, subswath, polarization)
        for subswath in subswaths
    ]

    product = (
        topsar_merge(subswath_products, polarization=polarization)
        if len(subswath_products) > 1
        else subswath_products[0]
    )

    product = multilook(product, range_looks=range_looks, azimuth_looks=azimuth_looks)

    if apply_speckle_filter:
        product = speckle_filter(
            product,
            filter_name=speckle_filter_name,
            num_looks=range_looks * azimuth_looks,
        )

    product = terrain_flattening(product, dem_name=dem_name)
    product = terrain_correction(product, dem_name=dem_name, pixel_spacing_m=pixel_spacing_m)

    gamma0_band = find_band(product, "Gamma0")
    db_product = linear_to_db(product, source_band=gamma0_band)

    rtc_path = out_dir / "s1_rtc_gamma0"
    db_path = out_dir / "s1_rtc_gamma0_db"
    write_product(product, rtc_path, "GeoTIFF")
    write_product(db_product, db_path, "GeoTIFF")

    return product, db_product


if __name__ == "__main__":
    slc_candidates = sorted(Path("downloads/sentinel1").glob("*.zip"))
    if not slc_candidates:
        raise FileNotFoundError(
            "downloads/sentinel1 에 다운로드된 SLC(.zip)이 없습니다. "
            "main_s1_list.py로 먼저 다운로드하세요."
        )

    process_s1_slc_to_rtc(
        slc_path=slc_candidates[0],
        out_dir="downloads/rtc",
        subswaths=("IW1", "IW2", "IW3"),
        polarization="VV",
    )
