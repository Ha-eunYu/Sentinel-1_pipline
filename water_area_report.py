# -*- coding: utf-8 -*-
"""
수체 GeoTIFF(0=비수체 / 1=수체 / 255=미관측)의 면적을 여러 방식으로 산출·비교한다.

배경: build_water_per_date_otsu.py 등 프로젝트의 기존 면적 통계는
  "수체 픽셀 수 × (장면 중심위도 하나로 계산한) 픽셀 1개 면적"
이다(EPSG:4326 지리좌표에서의 근사). 이 스크립트는 그 근사의 정확도를
확인하고, 필요하면 더 정확한 값(위도별 보정·폴리곤 측지면적)을 제공한다.

세 가지 면적
  1) pixel_centerlat : 기존 방식 — 중심위도 하나로 픽셀면적 상수 취급(참고/재현용)
  2) pixel_perrow    : **행(위도)별 픽셀면적**으로 가중합. 경도길이가 cos(위도)로
                       줄어드는 걸 행마다 반영 → 남북으로 넓은 장면에서 (1)보다 정확.
                       벡터화 없이 numpy만으로 계산(빠르고 사실상 정확).
  3) polygon_geodesic: 수체(=1)를 폴리곤으로 벡터화(rasterio.features.shapes) 후
                       **구면 폴리곤 면적 공식**(geojson-area 방식, numpy만 사용)
                       으로 합산. (2)와 교차검증용이며, --geojson-dir 로 QGIS용
                       폴리곤 레이어도 내보낼 수 있다.

폴리곤 방식 주의: 큰 장면(수백만 화소)은 벡터화가 무거워 창(window) 단위로
처리한다. 창 경계에서 폴리곤이 잘리지만 **면적 합계는 보존**된다(인접 폴리곤이
따로 잡혀도 합은 같음). 따라서 GeoJSON 레이어는 경계에서 조각날 수 있어
"면적 산출용"으로는 정확하되 "깔끔한 도형"은 아니다. --min-area-m2 로 speckle
(작은 오탐 조각)을 걸러낼 수 있다.

실행:
    conda run -n s1_snappy python water_area_report.py            # water_otsu 전체
    conda run -n s1_snappy python water_area_report.py --water downloads/water_otsu/flood_water_total_20260703_o008384.tif
    conda run -n s1_snappy python water_area_report.py --polygon
    conda run -n s1_snappy python water_area_report.py --polygon --geojson-dir downloads/water_otsu/geojson --min-area-m2 900
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_GLOB = "downloads/water_otsu/flood_water_total_*.tif"
CHUNK_ROWS = 1024
M_PER_DEG = 111_320.0  # 위도 1도 ≈ 111.32 km


def _pixel_areas_km2(src) -> tuple[float, np.ndarray]:
    """(중심위도 상수 픽셀면적, 행별 픽셀면적 배열[height]) 을 km^2 로 반환.
    EPSG:4326 정사각 픽셀 가정: 면적 = (res*111320)^2 * cos(위도)."""
    res_x = abs(src.transform.a)  # 픽셀 가로 크기(도, 경도방향)
    res_y = abs(src.transform.e)  # 픽셀 세로 크기(도, 위도방향)
    top = src.bounds.top
    # 각 행 중심의 위도
    rows = np.arange(src.height)
    row_lats = top - (rows + 0.5) * res_y
    # 위도별 cos 곱하기 전 면적(m^2): N-S 길이 × E-W 길이(cos 미적용)
    base = (res_y * M_PER_DEG) * (res_x * M_PER_DEG)
    perrow_km2 = base * np.cos(np.radians(row_lats)) / 1e6
    center_lat = (src.bounds.bottom + src.bounds.top) / 2
    center_km2 = base * np.cos(np.radians(center_lat)) / 1e6
    return center_km2, perrow_km2


def pixel_areas(path: Path) -> dict:
    """방식 1·2 (픽셀 기반)을 창 단위로 계산."""
    with rasterio.open(path) as src:
        center_km2, perrow_km2 = _pixel_areas_km2(src)
        n_water = n_valid = 0
        area_centerlat = area_perrow = 0.0
        for row0 in range(0, src.height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, src.height - row0)
            win = Window(0, row0, src.width, nrows)
            a = src.read(1, window=win)
            water = a == 1
            valid = a != 255
            # 행별 수체 화소 수 * 그 행의 픽셀면적
            per_row_counts = water.sum(axis=1)
            area_perrow += float((per_row_counts * perrow_km2[row0:row0 + nrows]).sum())
            nw = int(water.sum())
            n_water += nw
            n_valid += int(valid.sum())
            area_centerlat += nw * center_km2
    return {
        "n_water_px": n_water, "n_valid_px": n_valid,
        "area_pixel_centerlat_km2": round(area_centerlat, 3),
        "area_pixel_perrow_km2": round(area_perrow, 3),
    }


WGS84_RADIUS_M = 6_378_137.0  # geojson-area와 동일(WGS84 적도반경)


def _ring_area_m2(ring: list) -> float:
    """구면 폴리곤 링의 부호있는 면적(m^2). geojson-area(Chamberlain & Duquette)
    알고리즘: Σ (lon_{i+2} - lon_i)·sin(lat_{i+1}) · R²/2. lon/lat은 도(°) 입력.
    pyproj/shapely 없이 numpy만 사용."""
    a = np.asarray(ring, dtype="float64")
    if a.shape[0] < 4:  # 닫힌 링은 최소 4점(고유 3점 + 폐합점)
        return 0.0
    lon = np.radians(a[:, 0])
    lat = np.radians(a[:, 1])
    total = np.sum((np.roll(lon, -2) - lon) * np.sin(np.roll(lat, -1)))
    return float(total * WGS84_RADIUS_M ** 2 / 2.0)


def _polygon_area_m2(coords: list) -> float:
    """GeoJSON Polygon 좌표(coords[0]=외곽, 이후=구멍)의 순면적(m^2)."""
    if not coords:
        return 0.0
    area = abs(_ring_area_m2(coords[0]))
    for hole in coords[1:]:
        area -= abs(_ring_area_m2(hole))
    return area


def polygon_area(path: Path, min_area_m2: float, geojson_path: Path | None) -> dict:
    """방식 3 (폴리곤 구면면적). 무거우므로 --polygon 일 때만 호출.
    수체(=1)를 벡터화(rasterio.features.shapes)한 뒤 구면 폴리곤 면적을 합산."""
    from rasterio.features import shapes

    total_m2 = 0.0
    n_poly = 0
    features = []
    with rasterio.open(path) as src:
        transform = src.transform
        for row0 in range(0, src.height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, src.height - row0)
            win = Window(0, row0, src.width, nrows)
            a = src.read(1, window=win)
            mask = a == 1
            if not mask.any():
                continue
            win_transform = rasterio.windows.transform(win, transform)
            for geom, val in shapes(a, mask=mask, transform=win_transform, connectivity=8):
                if val != 1:
                    continue
                area_m2 = _polygon_area_m2(geom["coordinates"])
                if area_m2 < min_area_m2:
                    continue
                total_m2 += area_m2
                n_poly += 1
                if geojson_path is not None:
                    features.append({
                        "type": "Feature",
                        "properties": {"area_m2": round(area_m2, 2)},
                        "geometry": geom,
                    })

    if geojson_path is not None:
        geojson_path.parent.mkdir(parents=True, exist_ok=True)
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection",
                       "crs": {"type": "name",
                               "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                       "features": features}, f)
    return {
        "n_polygons": n_poly,
        "area_polygon_geodesic_km2": round(total_m2 / 1e6, 3),
        "geojson": str(geojson_path) if geojson_path else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="수체 지도 면적 산출·비교 (픽셀/폴리곤)")
    parser.add_argument("--water", default=None,
                        help="수체 tif 경로 하나. 생략 시 downloads/water_otsu/*.tif 전체")
    parser.add_argument("--polygon", action="store_true",
                        help="폴리곤 측지면적도 계산(느림)")
    parser.add_argument("--geojson-dir", default=None,
                        help="폴리곤 GeoJSON 출력 폴더 (지정 시 --polygon 자동 활성)")
    parser.add_argument("--min-area-m2", type=float, default=0.0,
                        help="이 면적 미만 폴리곤(조각/ speckle) 제외")
    parser.add_argument("--csv", default=None, help="결과를 CSV로도 저장할 경로")
    args = parser.parse_args()

    do_polygon = args.polygon or args.geojson_dir is not None

    if args.water:
        paths = [Path(args.water)]
    else:
        paths = sorted(PROJECT_DIR.glob(DEFAULT_GLOB))
    if not paths:
        raise SystemExit("대상 tif가 없습니다.")

    rows = []
    for p in paths:
        if not p.exists():
            print(f"[건너뜀] 없음: {p}")
            continue
        rec = {"file": p.name}
        rec.update(pixel_areas(p))
        if do_polygon:
            gj = (Path(args.geojson_dir) / (p.stem + ".geojson")
                  if args.geojson_dir else None)
            rec.update(polygon_area(p, args.min_area_m2, gj))
        rows.append(rec)

        line = (f"{p.name}: 수체 {rec['n_water_px']:,}px | "
                f"중심위도근사 {rec['area_pixel_centerlat_km2']:,.2f} km² | "
                f"행별보정 {rec['area_pixel_perrow_km2']:,.2f} km²")
        if do_polygon:
            line += (f" | 폴리곤측지 {rec['area_polygon_geodesic_km2']:,.2f} km² "
                     f"({rec['n_polygons']:,}개)")
        print(line)

    if args.csv and rows:
        # 방식별로 키가 다를 수 있으니 전체 키의 합집합을 헤더로 사용
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV 저장: {args.csv}")


if __name__ == "__main__":
    main()
