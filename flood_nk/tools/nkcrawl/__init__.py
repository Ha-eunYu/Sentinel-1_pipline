# -*- coding: utf-8 -*-
"""nkcrawl — 북한 홍수·기상 크롤링 재사용 툴킷 (stdlib only).

라이브러리로 import 하거나 CLI로 실행할 수 있다.

라이브러리 예::

    from nkcrawl import spn_latest, fetch_spn, check_image, SOURCES
    for w in spn_latest(3):
        print(w.date, w.md_row())

CLI 예::

    python -m nkcrawl latest -n 3 --md --check-images
    python -m nkcrawl scan --from 109257 --to 109300 --md
    python -m nkcrawl verify <img_url> ...

표준 라이브러리만 사용하므로 별도 설치가 필요 없다. 자세한 절차는
상위 폴더의 ``CRAWL_GUIDE_KR.md`` 및 ``README_KR.md`` 참조.
"""
from __future__ import annotations

from .http import check_image, http_get
from .sources import ACCESS_ICON, SOURCES, UA
from .spn import (
    SpnWeather,
    collect_spn_weather,
    fetch_spn,
    is_weather,
    parse_spn_weather,
    spn_latest,
    spn_site_max_idxno,
    spn_url,
)

__version__ = "1.0.0"

__all__ = [
    "SOURCES", "ACCESS_ICON", "UA",
    "http_get", "check_image",
    "SpnWeather", "parse_spn_weather", "fetch_spn", "spn_url",
    "spn_site_max_idxno", "is_weather", "collect_spn_weather", "spn_latest",
    "__version__",
]
