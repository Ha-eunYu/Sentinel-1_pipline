from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class S1SearchConfig:
    bbox: List[float]                     # [minLon, minLat, maxLon, maxLat]
    # collection: str = "sentinel-1-grd"   # or "sentinel-1-slc"
    collection: str = "sentinel-1-slc"   # or "sentinel-1-slc"
    window_days: int = 3                 # ±N days
    max_items: int = 200
    instrument_mode: Optional[str] = "IW"
    orbit_state: Optional[str] = None    # "ascending" / "descending"
    product_type: Optional[str] = None   # e.g. GRD, SLC family filter if needed
    polarization: Optional[str] = None   # e.g. DV, DH, SV, SH
    sort_by_time_diff: bool = True

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


def make_datetime_range(target_date: str, window_days: int) -> str:
    target_dt = datetime.fromisoformat(target_date).replace(tzinfo=timezone.utc)
    start = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00Z")
    end = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%dT23:59:59Z")
    return f"{start}/{end}"