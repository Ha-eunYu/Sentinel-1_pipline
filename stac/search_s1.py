from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from stac.models import S1ItemSummary, S1SearchConfig, make_datetime_range, to_dt_utc


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


def _extract_s1_summary(item) -> S1ItemSummary:
    props = item.properties or {}
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
        assets=sorted(list((item.assets or {}).keys())),
    )


def _score_item(item, target_dt: datetime) -> Tuple[float, datetime]:
    dt = to_dt_utc(item.properties["datetime"])
    dt_diff_hours = abs((dt - target_dt).total_seconds()) / 3600.0
    return (dt_diff_hours, dt)


def _build_query(cfg: S1SearchConfig) -> Dict[str, Any]:
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


def list_s1_items_for_date(
    client,
    target_date: str,
    cfg: S1SearchConfig,
    k: int = 20,
) -> Dict[str, Any]:
    target_dt = datetime.fromisoformat(target_date).replace(tzinfo=timezone.utc)
    datetime_range = make_datetime_range(target_date, cfg.window_days)

    query = _build_query(cfg)

    search = client.search(
        collections=[cfg.collection],
        bbox=cfg.bbox,
        datetime=datetime_range,
        query=query if query else None,
        limit=min(cfg.max_items, 100),
    )

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
                "datetime": datetime_range,
                "query": query,
            },
        }

    if cfg.sort_by_time_diff:
        items = sorted(items, key=lambda x: _score_item(x, target_dt))
    else:
        items = sorted(items, key=lambda x: x.properties.get("datetime", ""))

    topk = [_extract_s1_summary(it).__dict__ for it in items[:k]]

    return {
        "target_date": target_date,
        "status": "ok",
        "search_used": {
            "collection": cfg.collection,
            "bbox": cfg.bbox,
            "datetime": datetime_range,
            "query": query,
        },
        "count_found": len(items),
        "candidates_topk": topk,
    }