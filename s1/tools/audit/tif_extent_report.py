#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tree.txt에 기록된 모든 *_db.tif 파일의 공간 범위(촬영/관측 영역)를 조사합니다.

기본 출력
---------
1) tif_extent_wgs84.csv
   - 파일별 CRS, 픽셀 크기, WGS84 경위도 범위, 중심점, 관측시각
2) tif_footprints_wgs84.geojson
   - 파일별 실제 래스터 모서리 기반 footprint
3) overall_extent_wgs84.geojson
   - 전체 파일을 포함하는 WGS84 경계상자
4) 콘솔
   - 파일 수, 누락 파일, 전체 min/max 경위도

선택 출력
---------
--admin-boundary 경계파일.shp 또는 .gpkg
   - 영상 footprint와 행정경계를 중첩하여 촬영 지역 목록을 저장합니다.
   - admin_overlap.csv

설치
----
conda install -c conda-forge rasterio pyproj
# 행정구역 중첩까지 사용할 경우:
conda install -c conda-forge geopandas shapely pyogrio
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import rasterio
    from rasterio.warp import transform_geom
except ImportError as exc:
    raise SystemExit(
        "rasterio가 필요합니다.\n"
        "설치: conda install -c conda-forge rasterio pyproj"
    ) from exc


DB_TIF_RE = re.compile(r"(?i)([^\\/:*?\"<>|\r\n]+_db\.tif)\s*$")
S1_TIME_RE = re.compile(
    r"^(?P<platform>S1[A-Z])_.*?_(?P<start>\d{8}T\d{6})_"
    r"(?P<end>\d{8}T\d{6})_"
)


def read_text_auto(path: Path) -> str:
    """Windows tree 명령 출력의 UTF-16을 포함해 여러 인코딩을 처리합니다."""
    raw = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "cp949", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeError:
            continue
    raise UnicodeError(f"문자 인코딩을 판별하지 못했습니다: {path}")


def parse_db_tif_names(tree_path: Path) -> list[str]:
    """tree.txt에서 파일명이 정확히 *_db.tif로 끝나는 항목만 추출합니다."""
    text = read_text_auto(tree_path)
    names: list[str] = []

    for line in text.splitlines():
        match = DB_TIF_RE.search(line.strip())
        if match:
            names.append(match.group(1).strip())

    # 순서를 유지하며 중복 제거
    unique_names = list(dict.fromkeys(names))
    if not unique_names:
        raise ValueError(f"{tree_path}에서 *_db.tif 파일명을 찾지 못했습니다.")
    return unique_names


def build_file_index(root_dir: Path, recursive: bool) -> dict[str, Path]:
    """
    파일명 -> 실제 경로 색인.
    tree.txt가 하위 폴더 구조를 포함하지 않으면 recursive=False가 빠릅니다.
    """
    pattern = "**/*_db.tif" if recursive else "*_db.tif"
    index: dict[str, Path] = {}
    for path in root_dir.glob(pattern):
        if path.is_file():
            index.setdefault(path.name.lower(), path)
    return index


def parse_s1_metadata(filename: str) -> dict[str, str]:
    """Sentinel-1 표준 파일명에서 플랫폼과 UTC 관측시각을 추출합니다."""
    match = S1_TIME_RE.match(filename)
    if not match:
        return {
            "platform": "",
            "acquisition_start_utc": "",
            "acquisition_end_utc": "",
            "acquisition_date_utc": "",
        }

    start = datetime.strptime(match.group("start"), "%Y%m%dT%H%M%S")
    end = datetime.strptime(match.group("end"), "%Y%m%dT%H%M%S")
    return {
        "platform": match.group("platform"),
        "acquisition_start_utc": start.isoformat(timespec="seconds") + "Z",
        "acquisition_end_utc": end.isoformat(timespec="seconds") + "Z",
        "acquisition_date_utc": start.date().isoformat(),
    }


def raster_corner_polygon(ds: rasterio.io.DatasetReader) -> dict[str, Any]:
    """
    회전된 GeoTIFF도 처리할 수 있도록 단순 bounds가 아니라
    네 모서리 픽셀 좌표를 지리좌표로 변환해 polygon을 만듭니다.
    """
    transform = ds.transform
    pixel_corners = [
        (0, 0),
        (ds.width, 0),
        (ds.width, ds.height),
        (0, ds.height),
        (0, 0),
    ]
    coordinates = [transform * (col, row) for col, row in pixel_corners]
    return {
        "type": "Polygon",
        "coordinates": [[list(xy) for xy in coordinates]],
    }


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    """GeoJSON geometry에서 모든 좌표쌍을 순회합니다."""
    if (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        yield float(value[0]), float(value[1])
        return

    if isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_positions(item)


def geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coords = list(iter_positions(geometry.get("coordinates", [])))
    if not coords:
        raise ValueError("GeoJSON geometry에 좌표가 없습니다.")

    xs = [xy[0] for xy in coords]
    ys = [xy[1] for xy in coords]
    return min(xs), min(ys), max(xs), max(ys)


def geodesic_area_km2(geometry_wgs84: dict[str, Any]) -> float | None:
    """pyproj가 있으면 WGS84 타원체 기준 footprint 면적을 계산합니다."""
    try:
        from pyproj import Geod
        from shapely.geometry import shape
    except ImportError:
        return None

    geom = shape(geometry_wgs84)
    geod = Geod(ellps="WGS84")
    area_m2, _ = geod.geometry_area_perimeter(geom)
    return abs(area_m2) / 1_000_000.0


def inspect_tif(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """GeoTIFF 헤더만 읽어 공간 메타데이터와 WGS84 footprint를 반환합니다."""
    with rasterio.open(path) as ds:
        if ds.crs is None:
            raise ValueError("CRS가 정의되어 있지 않습니다.")

        source_geometry = raster_corner_polygon(ds)
        geometry_wgs84 = transform_geom(
            ds.crs,
            "EPSG:4326",
            source_geometry,
            antimeridian_cutting=True,
            precision=8,
        )

        min_lon, min_lat, max_lon, max_lat = geometry_bounds(geometry_wgs84)
        time_meta = parse_s1_metadata(path.name)
        area_km2 = geodesic_area_km2(geometry_wgs84)

        record: dict[str, Any] = {
            "filename": path.name,
            "full_path": str(path),
            **time_meta,
            "source_crs": ds.crs.to_string(),
            "width_pixels": ds.width,
            "height_pixels": ds.height,
            "band_count": ds.count,
            "pixel_size_x": abs(ds.transform.a),
            "pixel_size_y": abs(ds.transform.e),
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "center_lon": (min_lon + max_lon) / 2.0,
            "center_lat": (min_lat + max_lat) / 2.0,
            "footprint_area_km2": (
                round(area_km2, 3) if area_km2 is not None else ""
            ),
        }

        feature = {
            "type": "Feature",
            "properties": {
                "filename": path.name,
                **time_meta,
                "source_crs": ds.crs.to_string(),
            },
            "geometry": geometry_wgs84,
        }

    return record, feature


def bbox_polygon(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> dict[str, Any]:
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


def write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    if not records:
        return
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def write_geojson(
    features: list[dict[str, Any]],
    output_path: Path,
) -> None:
    collection = {
        "type": "FeatureCollection",
        "name": output_path.stem,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    output_path.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_admin_name_columns(columns: Iterable[str]) -> list[str]:
    """국내외 행정경계에서 자주 쓰는 명칭 필드를 자동 선택합니다."""
    candidates = [
        "CTP_KOR_NM",
        "SIG_KOR_NM",
        "EMD_KOR_NM",
        "ADM_NM",
        "ADM_NM_KO",
        "NAME_0",
        "NAME_1",
        "NAME_2",
        "NAME_3",
        "NAME_KOR",
        "NAME",
    ]
    available = set(columns)
    return [column for column in candidates if column in available]


def overlay_admin_regions(
    footprint_geojson: Path,
    boundary_path: Path,
    output_csv: Path,
) -> None:
    """
    영상 footprint와 행정구역을 중첩합니다.
    경계파일에는 대한민국·북한·일본 등 필요한 범위가 모두 들어 있어야 합니다.
    """
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError(
            "행정구역 중첩에는 geopandas가 필요합니다.\n"
            "설치: conda install -c conda-forge geopandas shapely pyogrio"
        ) from exc

    footprints = gpd.read_file(footprint_geojson).to_crs("EPSG:4326")
    admin = gpd.read_file(boundary_path)

    if admin.crs is None:
        raise ValueError(f"행정경계 CRS가 없습니다: {boundary_path}")
    admin = admin.to_crs("EPSG:4326")

    name_columns = detect_admin_name_columns(admin.columns)
    if not name_columns:
        raise ValueError(
            "행정구역명 필드를 자동으로 찾지 못했습니다. "
            f"경계파일 필드: {list(admin.columns)}"
        )

    admin = admin[name_columns + ["geometry"]].copy()
    admin["_admin_id"] = range(len(admin))

    # 공간 후보 검색 후 실제 교차면적 계산
    joined = gpd.sjoin(
        footprints[["filename", "geometry"]],
        admin,
        how="inner",
        predicate="intersects",
    ).reset_index(drop=True)

    if joined.empty:
        output_csv.write_text(
            "filename,admin_region,overlap_area_km2\n",
            encoding="utf-8-sig",
        )
        print("행정경계와 중첩되는 영상이 없습니다.")
        return

    admin_geom = admin.geometry
    joined["admin_geometry"] = joined["index_right"].map(admin_geom)
    joined["intersection_geometry"] = joined.apply(
        lambda row: row.geometry.intersection(row.admin_geometry),
        axis=1,
    )

    # 면적 계산용 한반도 중심 Albers Equal Area
    joined_area = gpd.GeoSeries(
        joined["intersection_geometry"],
        crs="EPSG:4326",
    ).to_crs("EPSG:6933")
    joined["overlap_area_km2"] = joined_area.area / 1_000_000.0

    def combine_region(row: Any) -> str:
        values = []
        for column in name_columns:
            value = row.get(column)
            if value is not None and str(value).strip() not in ("", "nan", "None"):
                values.append(str(value).strip())
        return " ".join(dict.fromkeys(values))

    joined["admin_region"] = joined.apply(combine_region, axis=1)
    result = joined[
        ["filename", "admin_region", "overlap_area_km2"]
    ].copy()
    result = result[result["overlap_area_km2"] > 0]
    result = result.sort_values(
        ["filename", "overlap_area_km2"],
        ascending=[True, False],
    )
    result["overlap_area_km2"] = result["overlap_area_km2"].round(3)
    result.to_csv(output_csv, index=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tree.txt의 모든 *_db.tif 촬영/관측 범위를 계산합니다."
    )
    parser.add_argument(
        "--tree",
        type=Path,
        default=Path("F:/tree.txt"),
        help="Windows tree 명령 결과 파일. 기본값: F:/tree.txt",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("F:/"),
        help="실제 *_db.tif 파일이 있는 루트 폴더. 기본값: F:/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("F:/tif_extent_result"),
        help="결과 저장 폴더. 기본값: F:/tif_extent_result",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="루트 폴더의 하위 폴더까지 재귀적으로 검색합니다.",
    )
    parser.add_argument(
        "--admin-boundary",
        type=Path,
        default=None,
        help="선택: 행정구역 SHP/GPKG/GeoJSON 경계파일",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.tree.exists():
        print(f"[오류] tree.txt를 찾을 수 없습니다: {args.tree}", file=sys.stderr)
        return 2
    if not args.root.exists():
        print(f"[오류] TIFF 루트 폴더를 찾을 수 없습니다: {args.root}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)

    listed_names = parse_db_tif_names(args.tree)
    print(f"tree.txt에서 찾은 *_db.tif: {len(listed_names)}개")

    file_index = build_file_index(args.root, args.recursive)
    print(f"실제 폴더에서 찾은 *_db.tif: {len(file_index)}개")

    records: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    missing: list[str] = []
    failed: list[tuple[str, str]] = []

    for number, name in enumerate(listed_names, start=1):
        path = file_index.get(name.lower())

        # 재귀 검색을 끈 경우 가장 빠른 직접 경로도 확인
        if path is None:
            direct_path = args.root / name
            if direct_path.exists():
                path = direct_path

        if path is None:
            missing.append(name)
            print(f"[누락] {name}")
            continue

        try:
            record, feature = inspect_tif(path)
            records.append(record)
            features.append(feature)
            print(
                f"[{number:03d}/{len(listed_names):03d}] {name}\n"
                f"    lon: {record['min_lon']:.6f} ~ {record['max_lon']:.6f}, "
                f"lat: {record['min_lat']:.6f} ~ {record['max_lat']:.6f}"
            )
        except Exception as exc:
            failed.append((name, str(exc)))
            print(f"[실패] {name}: {exc}", file=sys.stderr)

    if not records:
        print("[오류] 정상적으로 읽은 GeoTIFF가 없습니다.", file=sys.stderr)
        return 1

    records.sort(
        key=lambda row: (
            row.get("acquisition_start_utc", ""),
            row["filename"],
        )
    )
    feature_by_name = {
        feature["properties"]["filename"]: feature for feature in features
    }
    features = [
        feature_by_name[record["filename"]]
        for record in records
    ]

    csv_path = args.output / "tif_extent_wgs84.csv"
    footprint_path = args.output / "tif_footprints_wgs84.geojson"
    overall_path = args.output / "overall_extent_wgs84.geojson"
    missing_path = args.output / "missing_or_failed.txt"

    write_csv(records, csv_path)
    write_geojson(features, footprint_path)

    overall_min_lon = min(float(row["min_lon"]) for row in records)
    overall_min_lat = min(float(row["min_lat"]) for row in records)
    overall_max_lon = max(float(row["max_lon"]) for row in records)
    overall_max_lat = max(float(row["max_lat"]) for row in records)

    overall_feature = {
        "type": "Feature",
        "properties": {
            "file_count": len(records),
            "min_lon": overall_min_lon,
            "min_lat": overall_min_lat,
            "max_lon": overall_max_lon,
            "max_lat": overall_max_lat,
            "center_lon": (overall_min_lon + overall_max_lon) / 2.0,
            "center_lat": (overall_min_lat + overall_max_lat) / 2.0,
        },
        "geometry": bbox_polygon(
            overall_min_lon,
            overall_min_lat,
            overall_max_lon,
            overall_max_lat,
        ),
    }
    write_geojson([overall_feature], overall_path)

    issue_lines = [
        "[tree.txt에는 있으나 실제 파일이 없는 항목]",
        *missing,
        "",
        "[읽기 실패 항목]",
        *[f"{name}\t{message}" for name, message in failed],
    ]
    missing_path.write_text("\n".join(issue_lines), encoding="utf-8-sig")

    print("\n========== 전체 촬영/관측 범위 (EPSG:4326) ==========")
    print(f"정상 처리 파일: {len(records)}개")
    print(f"누락 파일: {len(missing)}개")
    print(f"읽기 실패: {len(failed)}개")
    print(f"경도: {overall_min_lon:.8f} ~ {overall_max_lon:.8f}")
    print(f"위도: {overall_min_lat:.8f} ~ {overall_max_lat:.8f}")
    print(
        "중심점: "
        f"{(overall_min_lon + overall_max_lon) / 2.0:.8f}, "
        f"{(overall_min_lat + overall_max_lat) / 2.0:.8f}"
    )
    print(f"\nCSV: {csv_path}")
    print(f"Footprints: {footprint_path}")
    print(f"Overall extent: {overall_path}")
    print(f"Missing/failed: {missing_path}")

    if args.admin_boundary is not None:
        if not args.admin_boundary.exists():
            print(
                f"[오류] 행정경계 파일이 없습니다: {args.admin_boundary}",
                file=sys.stderr,
            )
            return 2

        admin_output = args.output / "admin_overlap.csv"
        overlay_admin_regions(
            footprint_geojson=footprint_path,
            boundary_path=args.admin_boundary,
            output_csv=admin_output,
        )
        print(f"행정구역 중첩 결과: {admin_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
