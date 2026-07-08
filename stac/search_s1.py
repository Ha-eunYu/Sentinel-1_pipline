from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from stac.models import (
    S1ItemSummary,
    S1SearchConfig,
    make_datetime_range,
    parse_target_datetime_utc,
    to_dt_utc,
)
import re

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

    if "product" in assets:
        product_href = assets["product"].href
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

def score_item(item, target_dt: datetime) -> tuple[float, datetime]:
    dt_str = (item.properties or {}).get("datetime")
    if not dt_str:
        return (float("inf"), datetime.max.replace(tzinfo=timezone.utc))

    dt = to_dt_utc(dt_str)
    dt_diff_hours = abs((dt - target_dt).total_seconds()) / 3600.0
    return (dt_diff_hours, dt)

def list_s1_items_for_date(
    client,
    target_date: str,
    cfg: S1SearchConfig,
    k: int = 20,
    ) -> Dict[str, Any]:
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
        }

    if cfg.sort_by_time_diff:
        ranked = sorted(items, key=lambda x: score_item(x, target_dt))

        # 목표 시각에 가장 가까운 순으로 상위 k개를 고르되, 검색 결과에 등장한
        # 위성(platform, 예: S1A/S1C/S1D)이 상위 k에 들지 못해 통째로 누락되는
        # 일이 없도록 위성별 최근접 후보를 최소 1개씩 보장한다.
        topk_items = ranked[:k]
        covered_platforms = {
            extract_s1_summary(it).platform for it in topk_items
        }
        for it in ranked:
            platform = extract_s1_summary(it).platform
            if platform not in covered_platforms:
                topk_items.append(it)
                covered_platforms.add(platform)
        topk_items.sort(key=lambda x: score_item(x, target_dt))
    else:
        topk_items = sorted(items, key=lambda x: x.properties.get("datetime", ""))[:k]

    topk = [extract_s1_summary(it).__dict__ for it in topk_items]

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
        "candidates_topk": topk,
    }