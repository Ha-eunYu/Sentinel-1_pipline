# -*- coding: utf-8 -*-
"""
Sentinel-1 IW GRD -> RTC(dB) 전처리 (snapista + gpt 실행).

prepro_gpt.py(SLC용)의 GRD 버전. GRD는 이미 디버스트+멀티룩+진폭 변환이 끝난
제품이라 TOPSAR-Split/Deburst/Merge, Multilook 단계가 필요 없어 체인이 짧고,
전체 씬을 돌려도 SLC RTC보다 훨씬 빠르다. 용도: 전체 씬(광역) 수체 탐지/확인.
AOI 정밀 분석은 SLC RTC(prepro_gpt.py)를 사용.

흐름 (전체 씬 기준):
  Read -> Apply-Orbit-File -> [Remove-GRD-Border-Noise] -> ThermalNoiseRemoval
  -> Calibration(Beta0) -> [Subset(AOI)] -> Speckle-Filter(Refined Lee)
  -> Terrain-Flattening -> Terrain-Correction -> LinearToFromdB -> Write(dB GeoTIFF)

참고:
  - Terrain-Flattening 입력은 Beta0여야 하며, GRD도 캘리브레이션 LUT가 있어
    Calibration에서 Beta0 출력이 그대로 된다 (SLC와 동일 조건).
  - Remove-GRD-Border-Noise는 구형 IPF(<2.9) 제품의 씬 가장자리 노이즈 제거용.
    요즘 제품은 기본 생략(False).
  - CDSE의 GRD는 COG 포맷 SAFE(zip, 씬 ID가 _COG로 끝남)이며 SNAP이 그대로 읽는다.
  - 입력이 HDD(F: 등)에 있으면 SSD(C:)로 복사 후 그 경로로 실행하면 더 빠르다.

실행:
    conda run -n s1_snappy python prepro_grd_gpt.py [GRD.zip 경로] [--aoi]
    # 경로 생략 시 downloads/sentinel1_grd 의 첫 zip
    # --aoi 를 붙이면 전체 씬 대신 Korea_flood_AOI 주변만 처리
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# snapista의 Graph.get_gpt_cmd()가 PATH에서 gpt.exe를 찾으므로 먼저 등록
SNAP_BIN = r"C:\Program Files\snap\bin"
if SNAP_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = SNAP_BIN + os.pathsep + os.environ.get("PATH", "")

from esa_snappy.snapista import Graph, Operator  # noqa: E402  (PATH 설정 이후 import)

from prepro_gpt import aoi_wkt_from_geojson  # noqa: E402


def _terrain_dem_params(
    dem_name: str,
    external_dem_file: str | Path | None,
    external_dem_nodata: float,
    external_dem_apply_egm: bool,
) -> dict:
    """Terrain-Flattening/Correction 공용 DEM 파라미터.

    external_dem_file이 주어지면 SNAP의 External DEM 모드를 쓴다. NGII DEM처럼
    정표고(orthometric) 기준 DEM은 apply_egm=True로 EGM96 지오이드 보정을 켜서
    SNAP이 기대하는 타원체고로 변환해야 한다 (TERRAIN_AUX_DATA_KR.md 참고).
    """
    if external_dem_file is None:
        return {"demName": dem_name}
    return {
        "demName": "External DEM",
        "externalDEMFile": str(external_dem_file),
        "externalDEMNoDataValue": str(float(external_dem_nodata)),
        "externalDEMApplyEGM": "true" if external_dem_apply_egm else "false",
    }


def build_grd_rtc_graph(
    grd_path: str | Path,
    out_dir: str | Path,
    *,
    polarization: str = "VV",
    dem_name: str = "Copernicus 30m Global DEM",
    external_dem_file: str | Path | None = None,
    external_dem_nodata: float = -9999.0,
    external_dem_apply_egm: bool = True,
    out_tag: str = "",
    pixel_spacing_m: float = 10.0,
    apply_border_noise_removal: bool = False,
    apply_speckle_filter: bool = True,
    speckle_filter_name: str = "Refined Lee",
    aoi_wkt: str | None = None,
) -> Graph:
    """Sentinel-1 IW GRD 한 장을 RTC(Gamma0) dB GeoTIFF로 만드는 gpt 그래프.

    out_tag: 산출물 파일명 접미사. 같은 씬을 다른 DEM으로 처리할 때 구분용
    (예: "_ngiidem" -> <씬ID>_rtc_db_ngiidem.tif).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dem_params = _terrain_dem_params(
        dem_name, external_dem_file, external_dem_nodata, external_dem_apply_egm
    )

    g = Graph()

    g.add_node(Operator("Read", file=str(grd_path)), node_id="Read")

    g.add_node(
        Operator(
            "Apply-Orbit-File",
            orbitType="Sentinel Precise (Auto Download)",
            polyDegree="3",
            continueOnFail="false",
        ),
        node_id="Apply-Orbit-File",
        source="Read",
    )

    prev = "Apply-Orbit-File"

    # 구형 IPF 제품의 씬 가장자리 노이즈 제거 (원시 GRD 밝기값 기준으로 동작하므로
    # ThermalNoiseRemoval/Calibration 이전에 넣어야 한다)
    if apply_border_noise_removal:
        g.add_node(
            Operator("Remove-GRD-Border-Noise", selectedPolarisations=polarization),
            node_id="Remove-GRD-Border-Noise",
            source=prev,
        )
        prev = "Remove-GRD-Border-Noise"

    g.add_node(
        Operator(
            "ThermalNoiseRemoval",
            selectedPolarisations=polarization,
            removeThermalNoise="true",
        ),
        node_id="ThermalNoiseRemoval",
        source=prev,
    )

    # RTC(Terrain-Flattening) 입력은 Beta0여야 하므로 Beta0만 출력
    g.add_node(
        Operator(
            "Calibration",
            selectedPolarisations=polarization,
            outputBetaBand="true",
            outputSigmaBand="false",
            outputGammaBand="false",
            outputImageScaleInDb="false",
        ),
        node_id="Calibration",
        source="ThermalNoiseRemoval",
    )

    prev = "Calibration"

    # AOI가 주어지면 여기서 잘라 이후 연산량을 줄인다 (GRD는 버스트 구조가
    # 없어 SLC처럼 Deburst를 기다릴 필요 없이 바로 자를 수 있다)
    if aoi_wkt:
        g.add_node(
            Operator("Subset", geoRegion=aoi_wkt, copyMetadata="true"),
            node_id="Subset",
            source=prev,
        )
        prev = "Subset"

    if apply_speckle_filter:
        g.add_node(
            Operator("Speckle-Filter", filter=speckle_filter_name),
            node_id="Speckle-Filter",
            source=prev,
        )
        prev = "Speckle-Filter"

    g.add_node(
        Operator(
            "Terrain-Flattening",
            demResamplingMethod="BILINEAR_INTERPOLATION",
            **dem_params,
        ),
        node_id="Terrain-Flattening",
        source=prev,
    )

    g.add_node(
        Operator(
            "Terrain-Correction",
            pixelSpacingInMeter=str(float(pixel_spacing_m)),
            imgResamplingMethod="BILINEAR_INTERPOLATION",
            demResamplingMethod="BILINEAR_INTERPOLATION",
            saveSelectedSourceBand="true",
            **dem_params,
        ),
        node_id="Terrain-Correction",
        source="Terrain-Flattening",
    )

    g.add_node(
        Operator("LinearToFromdB"),
        node_id="LinearToFromdB",
        source="Terrain-Correction",
    )

    # SLC RTC(downloads/rtc)와 섞이지 않게 별도 폴더에 저장.
    # (build_rtc_mosaic.py가 날짜별로 묶을 때 SLC/GRD가 섞이는 것 방지)
    g.add_node(
        Operator(
            "Write",
            file=str(out_dir / f"{Path(grd_path).stem}_rtc_db{out_tag}.tif"),
            formatName="GeoTIFF-BigTIFF",
        ),
        node_id="Write-dB",
        source="LinearToFromdB",
    )

    return g


def main() -> None:
    raw_args = sys.argv[1:]
    use_aoi = "--aoi" in raw_args

    # --dem <경로>: Copernicus 30m 대신 로컬 DEM(External DEM) 사용
    external_dem = None
    if "--dem" in raw_args:
        dem_idx = raw_args.index("--dem")
        external_dem = Path(raw_args[dem_idx + 1])
        if not external_dem.exists():
            raise FileNotFoundError(external_dem)
        raw_args = raw_args[:dem_idx] + raw_args[dem_idx + 2:]

    args = [a for a in raw_args if a != "--aoi"]

    if args:
        grd_path = Path(args[0])
    else:
        candidates = sorted(Path("downloads/sentinel1_grd").glob("*.zip"))
        if not candidates:
            raise FileNotFoundError(
                "downloads/sentinel1_grd 에 다운로드된 GRD(.zip)이 없습니다. "
                "main_s1_list_grd.py로 먼저 다운로드하세요."
            )
        grd_path = candidates[0]

    if not grd_path.exists():
        raise FileNotFoundError(grd_path)

    print(f"입력 GRD: {grd_path}")

    aoi_wkt = None
    if use_aoi:
        aoi_wkt = aoi_wkt_from_geojson(Path(__file__).resolve().parent / "Korea_flood_AOI.geojson")
        print(f"AOI 서브셋: {aoi_wkt}")
    else:
        print("전체 씬 처리 (AOI 서브셋을 쓰려면 --aoi)")

    out_tag = ""
    if external_dem is not None:
        out_tag = "_ngiidem"
        print(f"External DEM 사용: {external_dem} (산출물 접미사 {out_tag})")

    graph = build_grd_rtc_graph(
        grd_path,
        out_dir="downloads/rtc_grd",
        external_dem_file=external_dem,
        out_tag=out_tag,
        aoi_wkt=aoi_wkt,
    )
    graph.view()

    # SNAP Desktop(Graph Builder)이나 gpt CLI에서 그대로 쓸 수 있게 XML로도 저장
    graph_xml = Path(__file__).resolve().parent / "graphs" / "s1_grd_to_rtc_db.xml"
    graph_xml.parent.mkdir(parents=True, exist_ok=True)
    graph.save_graph(str(graph_xml))
    print(f"그래프 XML 저장: {graph_xml}")

    # -q: 병렬 타일 처리 스레드 수, -c: 타일 캐시 (힙 22G 기준)
    graph.run(gpt_options=["-q", str(os.cpu_count() or 8), "-c", "14G"])


if __name__ == "__main__":
    main()
