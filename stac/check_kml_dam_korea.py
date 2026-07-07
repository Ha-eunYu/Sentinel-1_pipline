# check_kml_dam_korea.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
import zipfile
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, Polygon, GeometryCollection
from shapely.geometry.base import BaseGeometry


NATURAL_EARTH_URL = (
    "https://naturalearth.s3.amazonaws.com/"
    "10m_cultural/ne_10m_admin_0_countries.zip"
)

DAM_KEYWORDS = [
    "dam",
    "reservoir",
    "barrage",
    "weir",
    "hydroelectric",
    "hydropower",
    "댐",
    "저수지",
    "보",
    "수력",
    "발전소",
]


def read_kml_text(kml_or_kmz_path: str | Path) -> str:
    """
    Read .kml or .kmz and return KML XML text.
    """
    path = Path(kml_or_kmz_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError(f"No .kml file found inside KMZ: {path}")
            # Usually doc.kml is the main file.
            main_kml = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
            return zf.read(main_kml).decode("utf-8", errors="replace")

    if path.suffix.lower() == ".kml":
        return path.read_text(encoding="utf-8", errors="replace")

    raise ValueError("Input must be .kml or .kmz")


def find_text(parent: ET.Element, tag_name: str) -> str:
    """
    Find first text by local tag name, ignoring namespace.
    """
    elem = parent.find(f".//{{*}}{tag_name}")
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def parse_coordinates(coord_text: str) -> list[tuple[float, float]]:
    """
    Parse KML coordinate text:
    lon,lat[,alt] lon,lat[,alt] ...
    """
    coords: list[tuple[float, float]] = []

    for token in re.split(r"\s+", coord_text.strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue

        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue

        coords.append((lon, lat))

    return coords


def close_ring(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if coords and coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    return coords


def extract_point_geometries(pm: ET.Element) -> list[BaseGeometry]:
    geoms = []

    for point in pm.findall(".//{*}Point"):
        coord_elem = point.find(".//{*}coordinates")
        if coord_elem is None or not coord_elem.text:
            continue

        coords = parse_coordinates(coord_elem.text)
        if coords:
            geoms.append(Point(coords[0]))

    return geoms


def extract_linestring_geometries(pm: ET.Element) -> list[BaseGeometry]:
    geoms = []

    for line in pm.findall(".//{*}LineString"):
        coord_elem = line.find(".//{*}coordinates")
        if coord_elem is None or not coord_elem.text:
            continue

        coords = parse_coordinates(coord_elem.text)
        if len(coords) >= 2:
            geoms.append(LineString(coords))

    return geoms


def extract_polygon_geometries(pm: ET.Element) -> list[BaseGeometry]:
    geoms = []

    for poly in pm.findall(".//{*}Polygon"):
        outer_elem = poly.find(".//{*}outerBoundaryIs//{*}coordinates")
        if outer_elem is None or not outer_elem.text:
            continue

        outer = close_ring(parse_coordinates(outer_elem.text))
        if len(outer) < 4:
            continue

        holes = []
        for inner_elem in poly.findall(".//{*}innerBoundaryIs//{*}coordinates"):
            if inner_elem.text:
                inner = close_ring(parse_coordinates(inner_elem.text))
                if len(inner) >= 4:
                    holes.append(inner)

        geom = Polygon(outer, holes)
        if not geom.is_valid:
            geom = geom.buffer(0)

        if not geom.is_empty:
            geoms.append(geom)

    return geoms


def extract_placemark_geometry(pm: ET.Element) -> BaseGeometry | None:
    """
    Extract Point / LineString / Polygon geometries from one Placemark.
    Multiple geometries are returned as GeometryCollection.
    """
    geoms: list[BaseGeometry] = []
    geoms.extend(extract_point_geometries(pm))
    geoms.extend(extract_linestring_geometries(pm))
    geoms.extend(extract_polygon_geometries(pm))

    if not geoms:
        return None

    if len(geoms) == 1:
        return geoms[0]

    return GeometryCollection(geoms)


def extract_extended_data(pm: ET.Element) -> dict:
    """
    Extract simple KML ExtendedData/Data/name/value fields.
    """
    result = {}

    for data in pm.findall(".//{*}Data"):
        key = data.attrib.get("name", "").strip()
        value_elem = data.find(".//{*}value")
        value = value_elem.text.strip() if value_elem is not None and value_elem.text else ""

        if key:
            result[key] = value

    return result


def kml_to_geodataframe(kml_or_kmz_path: str | Path) -> gpd.GeoDataFrame:
    """
    Convert KML/KMZ Placemarks to GeoDataFrame in EPSG:4326.
    """
    xml_text = read_kml_text(kml_or_kmz_path)
    root = ET.fromstring(xml_text.encode("utf-8"))

    rows = []

    for i, pm in enumerate(root.findall(".//{*}Placemark"), start=1):
        name = find_text(pm, "name")
        description = find_text(pm, "description")
        extended = extract_extended_data(pm)
        geom = extract_placemark_geometry(pm)

        if geom is None or geom.is_empty:
            continue

        rows.append(
            {
                "placemark_id": i,
                "name": name,
                "description": description,
                "extended_data": json.dumps(extended, ensure_ascii=False),
                "geometry": geom,
            }
        )

    if not rows:
        raise ValueError("No readable Placemark geometry found in KML/KMZ.")

    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def download_natural_earth(cache_dir: str | Path = "cache") -> Path:
    """
    Download Natural Earth country boundary zip if not already cached.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    out_path = cache_dir / "ne_10m_admin_0_countries.zip"

    if not out_path.exists():
        print(f"Downloading country boundary: {out_path}")
        urllib.request.urlretrieve(NATURAL_EARTH_URL, out_path)

    return out_path


def load_korea_boundaries(cache_dir: str | Path = "cache") -> gpd.GeoDataFrame:
    """
    Load North Korea and South Korea country polygons.
    """
    ne_zip = download_natural_earth(cache_dir)
    countries = gpd.read_file(ne_zip)

    # Natural Earth commonly has ISO_A3 and ADM0_A3.
    iso_col = None
    for candidate in ["ISO_A3", "ADM0_A3", "SOV_A3"]:
        if candidate in countries.columns:
            iso_col = candidate
            break

    if iso_col is None:
        raise ValueError("Could not find ISO country code column in boundary file.")

    korea = countries[countries[iso_col].isin(["KOR", "PRK"])].copy()

    if korea.empty:
        raise ValueError("Could not find KOR/PRK polygons in Natural Earth boundary.")

    korea["country_code"] = korea[iso_col]
    korea["country"] = korea["country_code"].map(
        {
            "KOR": "South Korea",
            "PRK": "North Korea",
        }
    )

    return korea[["country_code", "country", "geometry"]].to_crs("EPSG:4326")


def dam_keyword_check(row: pd.Series) -> bool:
    text = " ".join(
        [
            str(row.get("name", "")),
            str(row.get("description", "")),
            str(row.get("extended_data", "")),
        ]
    ).lower()

    return any(keyword.lower() in text for keyword in DAM_KEYWORDS)


def metric_measure(geom: BaseGeometry) -> float:
    """
    Geometry measure for choosing dominant country when geometry intersects both.
    Polygon: area
    LineString: length
    Point: 0
    """
    if geom.is_empty:
        return 0.0

    if geom.area > 0:
        return float(geom.area)

    if geom.length > 0:
        return float(geom.length)

    return 0.0


def classify_country(
    geom: BaseGeometry,
    korea: gpd.GeoDataFrame,
    korea_metric: gpd.GeoDataFrame,
) -> dict:
    """
    Classify geometry as South Korea, North Korea, outside, or ambiguous.
    """
    hits = korea[korea.geometry.intersects(geom)]

    if hits.empty:
        return {
            "country_code": None,
            "country": "Outside Korea",
            "decision": "OUTSIDE_KOREA",
            "intersection_note": "No intersection with South Korea or North Korea boundary.",
        }

    if len(hits) == 1:
        hit = hits.iloc[0]
        return {
            "country_code": hit["country_code"],
            "country": hit["country"],
            "decision": f"IN_{hit['country_code']}",
            "intersection_note": "Single-country intersection.",
        }

    # If geometry intersects both countries, choose dominant overlap only if measurable.
    geom_metric = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(korea_metric.crs).iloc[0]

    overlap_records = []
    for idx, row in hits.iterrows():
        inter = geom_metric.intersection(korea_metric.loc[idx, "geometry"])
        measure = metric_measure(inter)
        overlap_records.append(
            {
                "country_code": row["country_code"],
                "country": row["country"],
                "measure": measure,
            }
        )

    overlap_records = sorted(overlap_records, key=lambda x: x["measure"], reverse=True)

    # For polygons/lines, choose dominant side if there is a clear measurable overlap.
    if overlap_records[0]["measure"] > 0:
        top = overlap_records[0]
        second = overlap_records[1] if len(overlap_records) > 1 else None

        if second is None or top["measure"] > second["measure"] * 1.01:
            return {
                "country_code": top["country_code"],
                "country": top["country"],
                "decision": f"DOMINANTLY_IN_{top['country_code']}",
                "intersection_note": f"Intersects multiple countries; dominant overlap selected: {overlap_records}",
            }

    return {
        "country_code": None,
        "country": "Border or Ambiguous",
        "decision": "BORDER_OR_AMBIGUOUS",
        "intersection_note": f"Intersects multiple countries and cannot choose dominant side: {overlap_records}",
    }


def representative_lonlat(geom: BaseGeometry) -> tuple[float | None, float | None]:
    """
    Return representative lon/lat for reporting.
    """
    if geom is None or geom.is_empty:
        return None, None

    p = geom.representative_point()
    return float(p.x), float(p.y)


def check_kml_dams(
    kml_or_kmz_path: str | Path,
    output_path: str | Path,
    only_dam_keyword: bool = False,
) -> pd.DataFrame:
    features = kml_to_geodataframe(kml_or_kmz_path)
    korea = load_korea_boundaries()

    # EPSG:5179 is Korea 2000 / Unified CS.
    # Good for area/length comparison around the Korean Peninsula.
    try:
        korea_metric = korea.to_crs("EPSG:5179")
    except Exception:
        korea_metric = korea.to_crs("EPSG:3857")

    features["is_dam_keyword"] = features.apply(dam_keyword_check, axis=1)

    if only_dam_keyword:
        features = features[features["is_dam_keyword"]].copy()

    rows = []

    for _, row in features.iterrows():
        geom = row.geometry
        cls = classify_country(geom, korea, korea_metric)
        lon, lat = representative_lonlat(geom)

        rows.append(
            {
                "placemark_id": row["placemark_id"],
                "name": row["name"],
                "is_dam_keyword": bool(row["is_dam_keyword"]),
                "country": cls["country"],
                "country_code": cls["country_code"],
                "decision": cls["decision"],
                "lon": lon,
                "lat": lat,
                "geometry_type": geom.geom_type,
                "intersection_note": cls["intersection_note"],
                "description": row["description"],
                "extended_data": row["extended_data"],
            }
        )

    result = pd.DataFrame(rows)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() in [".xlsx", ".xls"]:
        result.to_excel(output_path, index=False)
    else:
        result.to_csv(output_path, index=False, encoding="utf-8-sig")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Check whether KML/KMZ dam features are in South Korea or North Korea."
    )
    parser.add_argument("kml", help="Input .kml or .kmz file")
    parser.add_argument(
        "-o",
        "--output",
        default="dam_korea_check.xlsx",
        help="Output .xlsx or .csv file",
    )
    parser.add_argument(
        "--only-dam-keyword",
        action="store_true",
        help="Export only Placemarks whose text contains dam/reservoir keywords.",
    )

    args = parser.parse_args()

    result = check_kml_dams(
        kml_or_kmz_path=args.kml,
        output_path=args.output,
        only_dam_keyword=args.only_dam_keyword,
    )

    print(f"Done. Saved: {args.output}")
    print(result[["placemark_id", "name", "is_dam_keyword", "country", "decision", "lon", "lat"]])


if __name__ == "__main__":
    main()