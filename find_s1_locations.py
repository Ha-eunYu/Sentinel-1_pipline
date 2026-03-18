from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


STAC_ROOT = "https://stac.dataspace.copernicus.eu/v1"
TIMEOUT = 60


PRODUCT_IDS_TEXT = """
S1A_IW_SLC__1SDV_20250108T092325_20250108T092355_057351_070ED6_4709
S1A_IW_SLC__1SDV_20250108T092353_20250108T092421_057351_070ED6_9B0C
S1A_IW_SLC__1SDV_20250108T092419_20250108T092446_057351_070ED6_822B
S1A_IW_SLC__1SDV_20250108T092443_20250108T092510_057351_070ED6_535C
S1A_IW_SLC__1SDV_20250113T093128_20250113T093158_057424_0711C2_2503
S1A_IW_SLC__1SDV_20250113T093156_20250113T093226_057424_0711C2_21FD
S1A_IW_SLC__1SDV_20250120T092324_20250120T092354_057526_0715C5_9931
S1A_IW_SLC__1SDV_20250120T092352_20250120T092420_057526_0715C5_0A96
S1A_IW_SLC__1SDV_20250120T092418_20250120T092445_057526_0715C5_41F0
S1A_IW_SLC__1SDV_20250120T092442_20250120T092509_057526_0715C5_5AF0
S1C_IW_SLC__1SDV_20251027T214030_20251027T214102_004753_00962A_B608
S1C_IW_SLC__1SDV_20260124T214739_20260124T214806_006051_00C224_7B38
S1C_IW_SLC__1SDV_20260217T214739_20260217T214806_006401_00CE20_4D9A
""".strip()


def parse_product_ids(text: str) -> List[str]:
    return [token.strip() for token in text.split() if token.strip()]


def stac_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def load_sentinel1_collections() -> List[Dict[str, str]]:
    """
    STAC /collections 에서 Sentinel-1 관련 컬렉션만 추림.
    collection id를 하드코딩하지 않고 title/description 기반으로 찾음.
    """
    data = stac_get_json(f"{STAC_ROOT}/collections")
    collections = data.get("collections", [])

    out: List[Dict[str, str]] = []
    for c in collections:
        cid = c.get("id", "")
        title = c.get("title", "") or ""
        desc = c.get("description", "") or ""
        text = f"{cid} {title} {desc}".lower()

        if "sentinel-1" in text:
            out.append(
                {
                    "id": cid,
                    "title": title,
                }
            )

    # SLC 쪽을 먼저 보게 정렬
    def score(item: Dict[str, str]) -> Tuple[int, str]:
        title_lower = item["title"].lower()
        cid_lower = item["id"].lower()
        slc_first = 0 if ("single look complex" in title_lower or "slc" in cid_lower) else 1
        return (slc_first, item["id"])

    out.sort(key=score)
    return out


def ring_centroid(coords: List[List[float]]) -> Tuple[float, float]:
    """
    간단한 polygon exterior ring centroid.
    마지막 점이 첫 점과 같아도 처리 가능.
    """
    if len(coords) < 3:
        raise ValueError("Polygon ring has too few points.")

    pts = coords[:]
    if pts[0] == pts[-1]:
        pts = pts[:-1]

    area2 = 0.0
    cx = 0.0
    cy = 0.0

    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    if math.isclose(area2, 0.0):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    cx /= (3.0 * area2)
    cy /= (3.0 * area2)
    return (cx, cy)


def geometry_center(geometry: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Polygon" and coords:
        return ring_centroid(coords[0])

    if gtype == "MultiPolygon" and coords:
        # 첫 polygon exterior 기준
        return ring_centroid(coords[0][0])

    return (None, None)


def fetch_item_by_exact_id(collection_id: str, product_id: str) -> Optional[Dict[str, Any]]:
    """
    정확한 item id endpoint 우선 시도:
    /collections/{collection_id}/items/{product_id}
    """
    url = f"{STAC_ROOT}/collections/{collection_id}/items/{product_id}"
    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def search_item_by_filter(collection_id: str, product_id: str) -> Optional[Dict[str, Any]]:
    """
    exact endpoint 실패 시 /search fallback
    """
    url = f"{STAC_ROOT}/search"
    payload = {
        "collections": [collection_id],
        "filter-lang": "cql2-json",
        "filter": {
            "op": "=",
            "args": [
                {"property": "id"},
                product_id
            ]
        },
        "limit": 1,
    }
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    feats = data.get("features", [])
    return feats[0] if feats else None


def find_product_item(product_id: str, s1_collections: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Sentinel-1 관련 컬렉션들에서 순차 탐색
    """
    for c in s1_collections:
        collection_id = c["id"]

        item = fetch_item_by_exact_id(collection_id, product_id)
        if item is None:
            item = search_item_by_filter(collection_id, product_id)

        if item is not None:
            item["_collection_id"] = collection_id
            item["_collection_title"] = c["title"]
            return item

    return None


def summarize_item(product_id: str, item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if item is None:
        return {
            "product_id": product_id,
            "found": False,
            "collection_id": None,
            "collection_title": None,
            "bbox": None,
            "center_lon": None,
            "center_lat": None,
            "datetime": None,
            "geometry": None,
        }

    geometry = item.get("geometry")
    bbox = item.get("bbox")
    props = item.get("properties", {})
    center_lon, center_lat = (None, None)

    if isinstance(geometry, dict):
        center_lon, center_lat = geometry_center(geometry)

    return {
        "product_id": product_id,
        "found": True,
        "collection_id": item.get("_collection_id"),
        "collection_title": item.get("_collection_title"),
        "bbox": bbox,
        "center_lon": center_lon,
        "center_lat": center_lat,
        "datetime": props.get("datetime"),
        "geometry": geometry,
    }


def main() -> None:
    product_ids = parse_product_ids(PRODUCT_IDS_TEXT)
    print(f"[INFO] input products: {len(product_ids)}")

    s1_collections = load_sentinel1_collections()
    print("[INFO] Sentinel-1 collections discovered:")
    for c in s1_collections:
        print(f"  - {c['id']}: {c['title']}")

    rows: List[Dict[str, Any]] = []
    features: List[Dict[str, Any]] = []

    for i, pid in enumerate(product_ids, start=1):
        print(f"[{i}/{len(product_ids)}] searching: {pid}")
        item = find_product_item(pid, s1_collections)
        row = summarize_item(pid, item)
        rows.append(row)

        if item is not None and item.get("geometry") is not None:
            features.append(
                {
                    "type": "Feature",
                    "geometry": item["geometry"],
                    "properties": {
                        "product_id": pid,
                        "collection_id": row["collection_id"],
                        "datetime": row["datetime"],
                        "center_lon": row["center_lon"],
                        "center_lat": row["center_lat"],
                    },
                }
            )

        time.sleep(0.1)

    out_dir = Path("stac_product_locations")
    out_dir.mkdir(exist_ok=True)

    json_path = out_dir / "product_locations.json"
    geojson_path = out_dir / "product_locations.geojson"
    csv_path = out_dir / "product_locations.csv"
    not_found_path = out_dir / "not_found.txt"

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
    }
    geojson_path.write_text(json.dumps(feature_collection, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV 직접 작성
    header = [
        "product_id",
        "found",
        "collection_id",
        "collection_title",
        "datetime",
        "center_lon",
        "center_lat",
        "bbox",
    ]

    lines = [",".join(header)]
    for r in rows:
        vals = [
            r["product_id"],
            str(r["found"]),
            "" if r["collection_id"] is None else str(r["collection_id"]),
            "" if r["collection_title"] is None else str(r["collection_title"]).replace(",", " "),
            "" if r["datetime"] is None else str(r["datetime"]),
            "" if r["center_lon"] is None else f"{r['center_lon']:.6f}",
            "" if r["center_lat"] is None else f"{r['center_lat']:.6f}",
            "" if r["bbox"] is None else json.dumps(r["bbox"], ensure_ascii=False),
        ]
        escaped = ['"' + v.replace('"', '""') + '"' for v in vals]
        lines.append(",".join(escaped))

    csv_path.write_text("\n".join(lines), encoding="utf-8")

    not_found = [r["product_id"] for r in rows if not r["found"]]
    not_found_path.write_text("\n".join(not_found), encoding="utf-8")

    found_count = sum(1 for r in rows if r["found"])
    print()
    print(f"[DONE] found: {found_count} / {len(rows)}")
    print(f"[DONE] JSON   : {json_path}")
    print(f"[DONE] GeoJSON: {geojson_path}")
    print(f"[DONE] CSV    : {csv_path}")
    print(f"[DONE] Missing: {not_found_path}")


if __name__ == "__main__":
    main()