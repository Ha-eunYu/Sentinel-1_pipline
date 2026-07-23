from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from stac.models import (
    S1ItemSummary,
    S1SearchConfig,
    make_datetime_range,
    parse_target_datetime_utc,
    to_dt_utc,
)

# 한반도 실경계(NK+SK, 제주 포함) — 검색 AOI(느슨한 bbox)로 걸러진 후보의 실제
# footprint를 이것과 대조해 중국/일본 전용 프레임(교집합 0%)만 제외한다.
# 2026-07-23: 검색 AOI로 쓰던 geojson/Korea.geojson이 제주(33.1~33.6°N)를 빼먹어
# 진짜 한반도 프레임(예: 93DD, 제주 인근 5.27% 겹침)이 검색에서 통째로 누락되는
# 문제를 발견 -> 검색은 느슨한 bbox로, 정확한 한반도 여부 판정은 이 실경계로
# 분리했다(SCENE_FOOTPRINT_REAUDIT_KR.md와 동일한 검증 방법).
_KOREA_PENINSULA_GEOJSON = Path(__file__).resolve().parent.parent / "geojson" / "Korea_Peninsula.geojson"
_korea_union_cache = None


def _korea_union():
    """geojson/Korea_Peninsula.geojson(NK+SK)의 shapely union. 지연 로드 후 캐시."""
    global _korea_union_cache
    if _korea_union_cache is None:
        from shapely.geometry import shape
        from shapely.ops import unary_union

        data = json.loads(_KOREA_PENINSULA_GEOJSON.read_text(encoding="utf-8"))
        geoms = [shape(f["geometry"]) for f in data["features"]]
        _korea_union_cache = unary_union(geoms)
    return _korea_union_cache


def touches_korea(item) -> bool:
    """STAC item의 실제 footprint(item.geometry)가 한반도 실경계와 겹치는지.
    교집합이 전혀 없으면(=완전히 중국/일본/공해) False."""
    from shapely.geometry import shape

    geom = getattr(item, "geometry", None)
    if not geom:
        return True  # geometry 정보가 없으면 판단 불가 -> 안전하게 통과시킴
    return shape(geom).intersects(_korea_union())


def _safe_get_str(properties: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = properties.get(k)
        if v is not None:
            return str(v)
    return None


def _safe_get_int(properties: Dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        v = properties.get(k)
        if v is None:
            continue
        try:
            return int(v)
        except Exception:
            continue
    return None


def extract_product_id(product_href: str, *, strict: bool = True) -> str | None:
    '''
    strict=True (강제 모드): 
        product_href에서 product_id를 추출하지 못하면 ValueError 발생 → 프로그램 중단 (다운로드 URL 생성 실패 방지)
    strict=False (유연 모드): 
        product_href에서 product_id를 추출하지 못하면 product_id = None(STAC 검색 결과 요약에서 product_id 누락) 
        → product_id 없음 → zipper_url 없음 → 다운로드 자체 불가능
    '''
    match = re.search(r"Products\(([^)]+)\)", product_href)
    if not match:
        if strict:
            raise ValueError(f"Cannot extract product id from: {product_href}")
        return None
    return match.group(1)


def build_zipper_url(product_id: str | None) -> str | None:
    if not product_id:
        return None
    return f"https://zipper.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"


def to_zipper_url(product_href: str) -> str:
    '''
    OData product URL에서 product_id를 추출하여 Zipper 다운로드 URL로 변환
    zipper_url = to_zipper_url(product_href)
    '''
    product_id = extract_product_id(product_href, strict=True)
    return build_zipper_url(product_id)


def extract_s1_summary(item) -> S1ItemSummary:
    props = item.properties or {}
    assets = item.assets or {}

    product_href = None
    product_id = None
    zipper_url = None

    # SLC 컬렉션은 asset 키가 "product"(소문자), GRD 컬렉션은 "Product"(대문자)
    product_asset = assets.get("product") or assets.get("Product")
    if product_asset is not None:
        product_href = product_asset.href
        product_id = extract_product_id(product_href, strict=False)
        zipper_url = build_zipper_url(product_id)

    return S1ItemSummary(
        id=item.id,
        datetime=props.get("datetime"),
        platform=_safe_get_str(props, "platform", "sat:platform_international_designator"),
        orbit_state=_safe_get_str(props, "sat:orbit_state"),
        relative_orbit=_safe_get_int(props, "sat:relative_orbit", "relativeOrbitNumber"),
        instrument_mode=_safe_get_str(props, "sar:instrument_mode"),
        polarization=_safe_get_str(props, "s1:polarization", "polarization"),
        product_type=_safe_get_str(props, "product:type", "productType"),
        bbox=getattr(item, "bbox", None),
        assets=sorted(list(assets.keys())),
        product_href=product_href,
        product_id=product_id,
        zipper_url=zipper_url,   
    )


def build_query(cfg: S1SearchConfig) -> Dict[str, Any]:
    query: Dict[str, Any] = {}

    if cfg.instrument_mode:
        query["sar:instrument_mode"] = {"eq": cfg.instrument_mode}

    # 아래 필드들은 collection/item별로 없을 수 있으므로 선택적 사용
    if cfg.orbit_state:
        query["sat:orbit_state"] = {"eq": cfg.orbit_state}

    if cfg.product_type:
        # STAC 구현별로 키가 다를 수 있어 후속 검증 필요
        query["product:type"] = {"eq": cfg.product_type}

    if cfg.polarization:
        query["s1:polarization"] = {"eq": cfg.polarization}

    return query

def score_item(item, target_dt: datetime) -> tuple[int, datetime]:
    """지정 날짜와의 **일(day) 근접도**로 정렬하기 위한 키.
    1순위: 촬영일과 지정일의 날짜 차이(일). 2순위: 실제 촬영 시각(오름차순)으로
    같은 근접도끼리 안정 정렬."""
    dt_str = (item.properties or {}).get("datetime")
    if not dt_str:
        return (10**9, datetime.max.replace(tzinfo=timezone.utc))

    dt = to_dt_utc(dt_str)
    day_diff = abs((dt.date() - target_dt.date()).days)
    return (day_diff, dt)

def list_s1_items_for_date(
    client,
    target_date: str,
    cfg: S1SearchConfig,
    exclude_non_korea: bool = True,
    ) -> Dict[str, Any]:
    """지정 날짜(target_date) 주변(±cfg.window_days)에서 검색한 뒤, **지정 날짜에
    가까운 촬영일 순**으로 정렬한 후보 전체를 반환한다. 몇 개를 실제로 받을지는
    호출부의 max_downloads로 정한다(이 함수는 개수를 자르지 않는다).

    exclude_non_korea(기본 True): 검색 AOI(cfg.bbox/intersects_geojson, 보통
    느슨한 사각형)를 통과했더라도, 실제 footprint가 한반도(NK+SK, 제주 포함)와
    전혀 겹치지 않는 프레임(중국/일본/공해 전용)은 후보에서 제외한다
    (touches_korea, 2026-07-23 도입 — SCENE_FOOTPRINT_REAUDIT_KR.md에서 반복
    확인된 문제의 재발 방지)."""
    target_dt = parse_target_datetime_utc(target_date)
    datetime_range = make_datetime_range(target_date, cfg.window_days)

    query = build_query(cfg)

    search_kwargs = {
        "collections": [cfg.collection],
        "datetime": datetime_range,
        "query": query if query else None,
        "limit": min(cfg.max_items, 100),
    }

    if cfg.intersects_geojson is not None:
        search_kwargs["intersects"] = cfg.intersects_geojson
    elif cfg.bbox is not None:
        search_kwargs["bbox"] = cfg.bbox
    else:
        raise ValueError("Either cfg.intersects_geojson or cfg.bbox must be provided.")

    search = client.search(**search_kwargs)

    items = []
    for it in search.items():
        items.append(it)
        if len(items) >= cfg.max_items:
            break

    n_before_korea_filter = len(items)
    excluded_ids: list[str] = []
    if exclude_non_korea:
        kept = []
        for it in items:
            if touches_korea(it):
                kept.append(it)
            else:
                excluded_ids.append(it.id)
        items = kept
        if excluded_ids:
            print(f"  [footprint 제외] 한반도 교집합 0%(중국/일본 등) {len(excluded_ids)}개: "
                  f"{', '.join(excluded_ids)}")

    if not items:
        return {
            "target_date": target_date,
            "status": "no_items",
            "reason": "No Sentinel-1 items found for the given conditions.",
            "search_used": {
                "collection": cfg.collection,
                "bbox": cfg.bbox,
                "intersects_geojson": cfg.intersects_geojson,
                "datetime": datetime_range,
                "query": query,
            },
            "excluded_non_korea": excluded_ids,
        }

    # 지정 날짜에 가까운 촬영일 순으로 후보 전체를 정렬(개수 제한은 호출부에서).
    ranked = sorted(items, key=lambda x: score_item(x, target_dt))
    candidates = [extract_s1_summary(it).__dict__ for it in ranked]

    return {
        "target_date": target_date,
        "status": "ok",
        "search_used": {
            "collection": cfg.collection,
            "bbox": cfg.bbox,
            "intersects_geojson": cfg.intersects_geojson,
            "datetime": datetime_range,
            "query": query,
        },
        "count_found": len(items),
        "count_found_before_footprint_filter": n_before_korea_filter,
        "excluded_non_korea": excluded_ids,
        "candidates": candidates,
    }