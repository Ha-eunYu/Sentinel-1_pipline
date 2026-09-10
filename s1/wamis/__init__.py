# -*- coding: utf-8 -*-
"""WAMIS(국가수자원관리종합정보시스템) OpenAPI 로 **댐 저수위**를 받아 온다.

인증키가 필요 없다. 세 층으로 나뉜다.

* :mod:`s1.wamis.client` — HTTP·재시도·오류 판정
* :mod:`s1.wamis.dams`   — 댐 목록과 이름 매칭
* :mod:`s1.wamis.series` — 시계열 수집(청크·중복 제거)

CLI 는 :mod:`s1.tools.wamis.collect_dam_level`, 설명은
docs/water/WAMIS_DAM_LEVEL_KR.md.
"""

from s1.wamis.client import WamisError, WamisUnavailable
from s1.wamis.dams import Dam, fetch_dams, resolve
from s1.wamis.series import daily, daily_from_hourly, hourly

__all__ = ["WamisError", "WamisUnavailable", "Dam", "fetch_dams", "resolve",
           "daily", "hourly", "daily_from_hourly"]
