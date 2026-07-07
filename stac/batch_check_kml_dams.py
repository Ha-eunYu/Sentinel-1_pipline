# batch_check_kml_dams.py
# -*- coding: utf-8 -*-
# E:\~K-water_지상국\~용역_활용기술\2_활용_알고리즘\dam_AOI
# python check_kml_dam_korea.py dam_locations.kml -o dam_korea_check.xlsx --only-dam-keyword

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from check_kml_dam_korea import (
    kml_to_geodataframe,
    load_korea_boundaries,
    dam_keyword_check,
    classify_country,
    representative_lonlat,
)


def classify_one_kml(
    kml_path: Path,
    korea: gpd.GeoDataFrame,
    korea_metric: gpd.GeoDataFrame,
    only_dam_keyword: bool = False,
) -> pd.DataFrame:
    """
    Process one KML/KMZ file and return classification result as DataFrame.
    """
    features = kml_to_geodataframe(kml_path)
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
                "source_file": kml_path.name,
                "source_path": str(kml_path),
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

    return pd.DataFrame(rows)


def batch_check_kml_folder(
    input_dir: str | Path,
    output_path: str | Path,
    recursive: bool = False,
    only_dam_keyword: bool = False,
) -> pd.DataFrame:
    """
    Process all KML/KMZ files in a folder.
    """
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")

    if recursive:
        kml_files = sorted(input_dir.rglob("*.kml")) + sorted(input_dir.rglob("*.kmz"))
    else:
        kml_files = sorted(input_dir.glob("*.kml")) + sorted(input_dir.glob("*.kmz"))

    if not kml_files:
        raise FileNotFoundError(f"No KML/KMZ files found in: {input_dir}")

    print(f"Found {len(kml_files)} KML/KMZ files.")

    korea = load_korea_boundaries()

    try:
        korea_metric = korea.to_crs("EPSG:5179")
    except Exception:
        korea_metric = korea.to_crs("EPSG:3857")

    all_results = []
    error_rows = []

    for i, kml_path in enumerate(kml_files, start=1):
        print(f"[{i}/{len(kml_files)}] Processing: {kml_path.name}")

        try:
            df = classify_one_kml(
                kml_path=kml_path,
                korea=korea,
                korea_metric=korea_metric,
                only_dam_keyword=only_dam_keyword,
            )
            all_results.append(df)

        except Exception as e:
            print(f"  ERROR: {kml_path.name}: {e}")
            error_rows.append(
                {
                    "source_file": kml_path.name,
                    "source_path": str(kml_path),
                    "error": str(e),
                }
            )

    if all_results:
        result = pd.concat(all_results, ignore_index=True)
    else:
        result = pd.DataFrame()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() in [".xlsx", ".xls"]:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            result.to_excel(writer, sheet_name="kml_country_check", index=False)

            if error_rows:
                pd.DataFrame(error_rows).to_excel(
                    writer,
                    sheet_name="errors",
                    index=False,
                )
    else:
        result.to_csv(output_path, index=False, encoding="utf-8-sig")

        if error_rows:
            error_path = output_path.with_name(output_path.stem + "_errors.csv")
            pd.DataFrame(error_rows).to_csv(
                error_path,
                index=False,
                encoding="utf-8-sig",
            )

    print(f"Done. Saved: {output_path}")

    if error_rows:
        print(f"Warning: {len(error_rows)} files had errors. Check the errors sheet or CSV.")

    return result


if __name__ == "__main__":
    input_folder = r"E:\~K-water_지상국\~용역_활용기술\2_활용_알고리즘\dam_AOI"
    output_file = r"E:\~K-water_지상국\~용역_활용기술\2_활용_알고리즘\dam_AOI_country_check.xlsx"

    batch_check_kml_folder(
        input_dir=input_folder,
        output_path=output_file,
        recursive=False,
        only_dam_keyword=False,
    )