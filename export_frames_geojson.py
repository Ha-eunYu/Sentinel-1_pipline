# -*- coding: utf-8 -*-
"""
다운로드 완료/진행 중/예정인 Sentinel-1 프레임 footprint를 GeoJSON으로 내보낸다.

QGIS 보고용: 결과 파일(downloads/s1_frames_report.geojson)을 QGIS에 올리고
`status` 필드로 분류(categorized) 스타일을 주면 프레임별 상태가 색으로 구분된다.

상태 판정 기준 (downloads/sentinel1 폴더와 manifest 대조):
  - downloaded  : <씬ID>.zip 존재
  - downloading : <씬ID>.zip.part 존재 (이어받기 중)
  - planned     : manifest(검색 결과)에는 있으나 파일이 아직 없음
  - aoi         : 참고용으로 함께 넣는 검색 AOI 폴리곤

footprint는 CDSE STAC에서 씬 ID로 정확한 폴리곤을 조회하고,
조회 실패 시 manifest의 bbox 사각형으로 대체한다 (geometry_source 필드로 구분).

실행:
    conda run -n s1_pipeline python export_frames_geojson.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pystac_client

STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
COLLECTION = "sentinel-1-slc"

MANIFEST_PATH = Path("downloads/s1_stac_list_manifest.json")
DOWNLOAD_DIR = Path("downloads/sentinel1")
OUT_PATH = Path("downloads/s1_frames_report.geojson")

KST = timezone(timedelta(hours=9))


def to_kst_str(iso_utc: str | None) -> str | None:
    if not iso_utc:
        return None
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def bbox_to_polygon(bbox: list[float]) -> dict:
    min_lon, min_lat, max_lon, max_lat = bbox
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


def load_manifest_candidates() -> dict[str, dict]:
    """manifest의 모든 target에서 후보 씬을 모아 id로 dedup."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    candidates: dict[str, dict] = {}
    for target in manifest.get("targets", []):
        for cand in target.get("candidates_topk", []):
            candidates.setdefault(cand["id"], cand)

    aoi_geom = manifest.get("config", {}).get("intersects_geojson")
    return candidates, aoi_geom


def scan_download_dir() -> tuple[set[str], set[str]]:
    """다운로드 폴더에서 (완료 씬ID, 진행중 씬ID) 집합을 만든다."""
    done, partial = set(), set()
    for p in DOWNLOAD_DIR.glob("*.zip"):
        done.add(p.stem)
    for p in DOWNLOAD_DIR.glob("*.zip.part"):
        partial.add(p.name.removesuffix(".zip.part"))
    return done, partial


def fetch_stac_items(scene_ids: list[str], client) -> dict[str, dict]:
    """STAC에서 씬 ID들의 footprint 폴리곤과 주요 속성 조회 (실패한 ID는 빠짐).

    manifest에 없는 씬(예: 예전에 받아둔 파일)의 촬영시각/위성 정보도
    여기서 채워지도록 geometry와 properties를 함께 반환한다.
    """
    found: dict[str, dict] = {}
    if not scene_ids:
        return found
    try:
        search = client.search(collections=[COLLECTION], ids=scene_ids)
        for item in search.items():
            props = item.properties or {}
            found[item.id] = {
                "geometry": item.geometry,
                "datetime": props.get("datetime"),
                "platform": props.get("platform"),
                "orbit_state": props.get("sat:orbit_state"),
                "relative_orbit": props.get("sat:relative_orbit"),
                "product_type": props.get("product:type"),
            }
    except Exception as e:
        print(f"STAC 조회 실패 (manifest bbox로 대체): {e}")
    return found


def file_size_gb(scene_id: str) -> float | None:
    for suffix in (".zip", ".zip.part"):
        p = DOWNLOAD_DIR / f"{scene_id}{suffix}"
        if p.exists():
            return round(p.stat().st_size / 1024**3, 2)
    return None


def main() -> None:
    candidates, aoi_geom = load_manifest_candidates()
    done, partial = scan_download_dir()

    # 폴더에는 있지만 manifest에 없는 씬(예: 예전에 받은 파일)도 포함
    all_ids = sorted(set(candidates) | done | partial)

    client = pystac_client.Client.open(STAC_URL)
    stac_items = fetch_stac_items(all_ids, client)

    features = []
    counts = {"downloaded": 0, "downloading": 0, "planned": 0}

    for scene_id in all_ids:
        if scene_id in done:
            status = "downloaded"
        elif scene_id in partial:
            status = "downloading"
        else:
            status = "planned"
        counts[status] += 1

        # 속성은 manifest 우선, 없으면 STAC 조회 결과로 채움
        cand = candidates.get(scene_id, {})
        stac = stac_items.get(scene_id, {})

        def pick(key: str):
            return cand.get(key) if cand.get(key) is not None else stac.get(key)

        geometry = stac.get("geometry")
        geometry_source = "stac_footprint"
        if geometry is None:
            bbox = cand.get("bbox")
            if bbox is None:
                print(f"경고: {scene_id} 는 footprint도 bbox도 없어 건너뜀")
                continue
            geometry = bbox_to_polygon(bbox)
            geometry_source = "manifest_bbox"

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": scene_id,
                "status": status,
                "platform": pick("platform"),
                "datetime_utc": pick("datetime"),
                "datetime_kst": to_kst_str(pick("datetime")),
                "orbit_state": pick("orbit_state"),
                "relative_orbit": pick("relative_orbit"),
                "product_type": pick("product_type"),
                "file_size_gb": file_size_gb(scene_id),
                "geometry_source": geometry_source,
            },
        })

    # 참고용 AOI 폴리곤도 한 피처로 추가
    if aoi_geom:
        features.append({
            "type": "Feature",
            "geometry": aoi_geom,
            "properties": {"id": "search_AOI", "status": "aoi"},
        })

    collection = {"type": "FeatureCollection", "features": features}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)

    print(f"저장: {OUT_PATH}  (피처 {len(features)}개)")
    print(f"  완료 {counts['downloaded']} / 진행중 {counts['downloading']} / 예정 {counts['planned']}")


if __name__ == "__main__":
    main()
