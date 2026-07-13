# -*- coding: utf-8 -*-
"""
Sentinel-1 IW SLC -> RTC 전처리 (snapista + gpt 실행 버전).

prepro.py와 같은 처리 체인이지만, esa_snappy의 GPF를 파이썬 프로세스 안에서
직접 실행하는 대신 SNAP 12+에 통합된 SNAPISTA(esa_snappy.snapista)로
그래프 XML을 만들어 SNAP 공식 처리기 gpt.exe로 실행한다.

이렇게 바꾼 이유: esa_snappy로 파이썬 JVM 안에서 Terrain-Flattening /
Terrain-Correction을 실행하면 DEM 자동 다운로드 모듈이 초기화되지 않아
"The DEM ... is not supported" 에러와 함께 깨진 GeoTIFF가 나온다.
gpt.exe는 SNAP 모듈 전체가 정상 로드되는 공식 실행 경로라서
Copernicus 30m DEM 자동 다운로드가 그대로 동작한다.

흐름:
  Read -> Apply-Orbit-File -> ThermalNoiseRemoval -> Calibration(Beta0)
  -> TOPSAR-Deburst -> [Subset(AOI)] -> Multilook -> Speckle-Filter(Refined Lee)
  -> Terrain-Flattening -> Terrain-Correction -> LinearToFromdB -> Write(dB GeoTIFF)

속도 관련:
  - Subset(AOI): Deburst 직후 AOI 주변만 잘라 이후 연산량을 수십 배 줄인다 (기본 사용).
  - 출력은 dB GeoTIFF 하나만 쓴다 (GeoTIFF 쓰기는 단일 스레드 병목이라 이중 쓰기 금지).
  - 입력 SLC가 HDD(F: 등)에 있으면 SSD(C:)로 복사한 뒤 그 경로로 실행하는 것이 빠르다.

gpt에서는 TOPSAR-Deburst가 SLC 전체(IW1/IW2/IW3)를 한 번에 처리하며
서브스와스 병합까지 해주므로 prepro.py의 TOPSAR-Split / TOPSAR-Merge
단계가 필요 없다.

실행:
    conda run -n s1_snappy python prepro_gpt.py [SLC.zip 경로]
    (경로 생략 시 downloads/sentinel1 의 첫 번째 .zip)
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


def build_rtc_graph(
    slc_path: str | Path,
    out_dir: str | Path,
    *,
    polarization: str = "VV",
    dem_name: str = "Copernicus 30m Global DEM",
    pixel_spacing_m: float = 10.0,
    range_looks: int = 1,
    azimuth_looks: int = 4,
    apply_speckle_filter: bool = True,
    speckle_filter_name: str = "Refined Lee",
    aoi_wkt: str | None = None,
) -> Graph:
    """Sentinel-1 IW SLC 한 장을 RTC(Gamma0) + dB GeoTIFF로 만드는 gpt 그래프."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    g = Graph()

    g.add_node(
        Operator("Read", file=str(slc_path)),
        node_id="Read",
    )

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

    g.add_node(
        Operator(
            "ThermalNoiseRemoval",
            selectedPolarisations=polarization,
            removeThermalNoise="true",
        ),
        node_id="ThermalNoiseRemoval",
        source="Apply-Orbit-File",
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

    g.add_node(
        Operator("TOPSAR-Deburst", selectedPolarisations=polarization),
        node_id="TOPSAR-Deburst",
        source="Calibration",
    )

    prev = "TOPSAR-Deburst"

    # AOI가 주어지면 Deburst 직후 공간 서브셋. 이후 모든 연산(Multilook,
    # Speckle, Terrain-*)이 AOI 타일만 계산하므로 전체 씬 대비 수십 배 빠르다.
    if aoi_wkt:
        g.add_node(
            Operator("Subset", geoRegion=aoi_wkt, copyMetadata="true"),
            node_id="Subset",
            source=prev,
        )
        prev = "Subset"

    g.add_node(
        Operator(
            "Multilook",
            nRgLooks=str(int(range_looks)),
            nAzLooks=str(int(azimuth_looks)),
        ),
        node_id="Multilook",
        source=prev,
    )

    prev = "Multilook"
    if apply_speckle_filter:
        # dB 임계값 기반 수체 탐지에서 스펙클로 인한 오탐을 줄이기 위해
        # Terrain-Flattening 이전에 적용 (prepro.py와 동일)
        g.add_node(
            Operator(
                "Speckle-Filter",
                filter=speckle_filter_name,
                numLooksStr=str(int(range_looks) * int(azimuth_looks)),
            ),
            node_id="Speckle-Filter",
            source=prev,
        )
        prev = "Speckle-Filter"

    g.add_node(
        Operator(
            "Terrain-Flattening",
            demName=dem_name,
            demResamplingMethod="BILINEAR_INTERPOLATION",
        ),
        node_id="Terrain-Flattening",
        source=prev,
    )

    g.add_node(
        Operator(
            "Terrain-Correction",
            demName=dem_name,
            pixelSpacingInMeter=str(float(pixel_spacing_m)),
            imgResamplingMethod="BILINEAR_INTERPOLATION",
            demResamplingMethod="BILINEAR_INTERPOLATION",
            saveSelectedSourceBand="true",
        ),
        node_id="Terrain-Correction",
        source="Terrain-Flattening",
    )

    # 산출물: dB 변환본만 출력 (수체 탐지 입력).
    # 선형 Gamma0도 같이 쓰면 GeoTIFF 쓰기(단일 스레드 병목)가 2배가 되어
    # 전체 시간이 크게 늘어나므로 dB 하나만 쓴다.
    # 파일명은 씬 ID 기반으로 만들어 여러 프레임을 처리해도 겹치지 않게 한다.
    g.add_node(
        Operator("LinearToFromdB"),
        node_id="LinearToFromdB",
        source="Terrain-Correction",
    )
    g.add_node(
        Operator(
            "Write",
            file=str(out_dir / f"{Path(slc_path).stem}_rtc_db.tif"),
            formatName="GeoTIFF-BigTIFF",
        ),
        node_id="Write-dB",
        source="LinearToFromdB",
    )

    return g


def _iter_lonlat(node):
    """중첩된 GeoJSON coordinates 배열에서 [lon, lat] 쌍을 재귀적으로 뽑는다.

    Point/LineString/Polygon/MultiPolygon 등 어떤 깊이의 좌표 구조든
    지원하기 위해, 숫자 2개짜리 리스트를 만나면 좌표로 간주한다.
    """
    if (
        isinstance(node, (list, tuple))
        and len(node) >= 2
        and all(isinstance(v, (int, float)) for v in node[:2])
    ):
        yield node[0], node[1]
        return
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _iter_lonlat(child)


def aoi_wkt_from_geojson(geojson_path: str | Path, margin_deg: float = 0.1) -> str:
    """AOI geojson의 bbox에 여유(margin)를 더한 WKT POLYGON 문자열 생성.

    Feature / FeatureCollection / 순수 geometry, 그리고 Polygon /
    MultiPolygon 등 어떤 형태든 모든 좌표를 모아 bbox를 계산한다.
    """
    import json

    with open(geojson_path, encoding="utf-8") as f:
        gj = json.load(f)

    if gj.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in gj.get("features", []) if f.get("geometry")]
    elif gj.get("type") == "Feature":
        geoms = [gj["geometry"]]
    else:
        geoms = [gj]

    lons, lats = [], []
    for geom in geoms:
        for lon, lat in _iter_lonlat(geom.get("coordinates", [])):
            lons.append(lon)
            lats.append(lat)

    if not lons:
        raise ValueError(f"좌표를 찾을 수 없습니다: {geojson_path}")

    min_lon, max_lon = min(lons) - margin_deg, max(lons) + margin_deg
    min_lat, max_lat = min(lats) - margin_deg, max(lats) + margin_deg
    return (
        f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    )


def main() -> None:
    if len(sys.argv) > 1:
        slc_path = Path(sys.argv[1])
    else:
        candidates = sorted(Path("downloads/sentinel1").glob("*.zip"))
        if not candidates:
            raise FileNotFoundError(
                "downloads/sentinel1 에 다운로드된 SLC(.zip)이 없습니다. "
                "main_s1_list.py로 먼저 다운로드하세요."
            )
        slc_path = candidates[0]

    if not slc_path.exists():
        raise FileNotFoundError(slc_path)

    print(f"입력 SLC: {slc_path}")

    # 홍수 AOI 주변만 처리 (전체 씬을 처리하려면 aoi_wkt=None으로)
    aoi_wkt = aoi_wkt_from_geojson(Path(__file__).resolve().parent / "Korea_flood_AOI.geojson")
    print(f"AOI 서브셋: {aoi_wkt}")

    graph = build_rtc_graph(slc_path, out_dir="downloads/rtc", aoi_wkt=aoi_wkt)
    graph.view()

    # SNAP Desktop(Graph Builder)이나 gpt CLI에서 그대로 쓸 수 있게 XML로도 저장
    graph_xml = Path(__file__).resolve().parent / "graphs" / "s1_slc_to_rtc_db.xml"
    graph_xml.parent.mkdir(parents=True, exist_ok=True)
    graph.save_graph(str(graph_xml))
    print(f"그래프 XML 저장: {graph_xml}")

    # -q: 병렬 타일 처리 스레드 수(논리 코어 수에 맞춤)
    # -c: 타일 캐시 크기 (gpt.vmoptions의 힙 22G 안에서 여유 있게)
    # 주의: -x(노드 캐시 해제)는 이웃 타일 재계산을 유발해 오히려 느려지므로 뺐다.
    graph.run(gpt_options=["-q", str(os.cpu_count() or 8), "-c", "14G"])


if __name__ == "__main__":
    main()
