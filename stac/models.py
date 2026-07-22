from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class S1SearchConfig:
    # bbox: List[float]                     # [minLon, minLat, maxLon, maxLat]
    bbox: Optional[List[float]] = None
    intersects_geojson: Optional[Dict[str, Any]] = None
    # collection: str = "sentinel-1-grd"   # or "sentinel-1-slc"
    collection: str = "sentinel-1-slc"   # or "sentinel-1-slc"
    window_days: int = 3                 # ±N days
    max_items: int = 200
    instrument_mode: Optional[str] = "IW"
    orbit_state: Optional[str] = None    # "ascending" / "descending"
    product_type: Optional[str] = None   # e.g. GRD, SLC family filter if needed
    polarization: Optional[str] = None   # e.g. DV, DH, SV, SH

    def __post_init__(self) -> None:
        if self.bbox is None and self.intersects_geojson is None:
            raise ValueError("Either bbox or intersects_geojson must be provided.")
        
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class S1ItemSummary:
    id: str
    datetime: Optional[str]
    platform: Optional[str]
    orbit_state: Optional[str]
    relative_orbit: Optional[int]
    instrument_mode: Optional[str]
    polarization: Optional[str]
    product_type: Optional[str]
    bbox: Optional[List[float]]
    assets: List[str]
    product_href: Optional[str] = None
    product_id: Optional[str] = None
    zipper_url: Optional[str] = None  

def to_dt_utc(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def parse_target_datetime_utc(s: str) -> datetime:
    """
    ISO 날짜/일시 문자열을 UTC datetime으로 변환.
    타임존 오프셋이 있으면(예: KST "+09:00") 그대로 UTC로 환산하고,
    없으면 이미 UTC로 간주한다. (오프셋을 버리고 덮어쓰지 않음)
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def make_datetime_range(target_date: str, window_days: int) -> str:
    target_dt = parse_target_datetime_utc(target_date)
    start = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00Z")
    end = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%dT23:59:59Z")
    return f"{start}/{end}"