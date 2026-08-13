# -*- coding: utf-8 -*-
"""Sentinel-1 파일명 파싱을 한 곳으로 모은다.

왜 필요한가
-----------
`S1C_IW_GRDH_1SDV_20260727T212332_20260727T212357_008734_0114F4_9B8B_COG.zip`
같은 이름에서 날짜·절대궤도·씬ID를 뽑는 정규식이 스크립트마다 따로 있었고,
미묘하게 달랐다. 특히 **씬 ID를 `split("_")[-2]`로 뽑는 코드**는 파일명에
`_COG`가 붙는지, `_rtc_db.tif`로 끝나는지에 따라 엉뚱한 필드를 집는다.
실제로 그 방식이 take ID를 씬 ID로 착각한 사고가 있었다.

명명 규약
---------
```text
S1C_IW_GRDH_1SDV_20260727T212332_20260727T212357_008734_0114F4_9B8B_COG.zip
 │                    │                             │      │      │    └ 제품 형식(선택)
 │                    │                             │      │      └ 씬 ID(4 hex)
 │                    │                             │      └ take ID(6 hex)
 │                    │                             └ 절대궤도(6자리)
 │                    └ 관측 시작(UTC)
 └ 위성
```
산출물은 여기에 `_rtc_db` / `_gtc_db` 같은 접미사가 더 붙는다.

사용:
    from s1.core.scene import scene_date, scene_orbit, scene_id, parse_scene
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

# 날짜만 필요한 경우(zip·tif 공통)
DATE_RE = re.compile(r"_(\d{8})T\d{6}_")

# 날짜 + 절대궤도 + take + 씬ID를 한 번에. 산출물 접미사가 붙어도 매칭된다.
FULL_RE = re.compile(
    r"_(?P<date>\d{8})T\d{6}_\d{8}T\d{6}_(?P<orbit>\d{6})_"
    r"(?P<take>[0-9A-Fa-f]{6})_(?P<sid>[0-9A-Fa-f]{4})"
)

# 위성 식별자(S1A/S1B/S1C/S1D)
PLATFORM_RE = re.compile(r"^(S1[A-D])_")


class SceneKey(NamedTuple):
    """파일명에서 뽑은 씬 식별 정보."""

    date: str        # YYYYMMDD (UTC)
    orbit: str       # 절대궤도 6자리 (문자열 — 앞의 0을 잃지 않게)
    take: str        # take ID
    sid: str         # 씬 ID 4 hex
    platform: str    # S1A / S1B / S1C / S1D ('' 이면 미상)


def _name(path: Path | str) -> str:
    return path.name if isinstance(path, Path) else str(path)


def parse_scene(path: Path | str) -> SceneKey | None:
    """파일명에서 (날짜, 절대궤도, take, 씬ID, 위성)을 뽑는다. 실패하면 None."""
    name = _name(path)
    m = FULL_RE.search(name)
    if not m:
        return None
    p = PLATFORM_RE.match(name)
    return SceneKey(
        date=m.group("date"),
        orbit=m.group("orbit"),
        take=m.group("take"),
        sid=m.group("sid").upper(),
        platform=p.group(1) if p else "",
    )


def scene_date(path: Path | str) -> str | None:
    """관측일 YYYYMMDD. 궤도 정보가 없는 이름에서도 날짜만은 뽑는다."""
    m = DATE_RE.search(_name(path))
    return m.group(1) if m else None


def scene_orbit(path: Path | str) -> str | None:
    """절대궤도 6자리 문자열. **앞의 0을 잃지 않도록 문자열로 다룬다.**"""
    k = parse_scene(path)
    return k.orbit if k else None


def scene_id(path: Path | str) -> str | None:
    """씬 ID 4 hex(대문자). split('_') 위치 계산 대신 이 함수를 쓸 것."""
    k = parse_scene(path)
    return k.sid if k else None


def scene_platform(path: Path | str) -> str | None:
    """위성 식별자(S1A~S1D)."""
    k = parse_scene(path)
    return k.platform if k else None


def group_key(path: Path | str) -> tuple[str, str] | None:
    """(날짜, 절대궤도) — 궤도별·날짜별 처리에서 그룹을 나누는 키.

    같은 날짜라도 궤도가 다르면 입사각·촬영기하가 달라 후방산란 분포가
    다르므로, 수체 판별은 반드시 이 키로 나눠서 한다.
    """
    k = parse_scene(path)
    return (k.date, k.orbit) if k else None


def normalize_orbit(value: str) -> str:
    """궤도번호를 6자리 0채움으로 정규화.

    셸이 "008632"를 숫자로 해석해 앞의 0을 떨구는 사고가 있어, 인자로 받은
    궤도번호는 반드시 이걸 통과시킨다.
    """
    return value.strip().zfill(6)


def matches_scene_id(path: Path | str, wanted: set[str]) -> bool:
    """파일명이 주어진 씬 ID 집합에 속하는지. 대소문자 무시."""
    sid = scene_id(path)
    return sid is not None and sid in {w.strip().upper() for w in wanted}
