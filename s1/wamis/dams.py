# -*- coding: utf-8 -*-
"""WAMIS **댐 목록**과, 이 저장소가 쓰는 이름 → 댐코드 **매칭**.

왜 매칭이 필요한가
------------------
이 저장소는 댐을 세 가지 이름으로 부른다. 셋 다 WAMIS 의 이름과 다르다.

===================================== ==================== ==================
부르는 곳                              예                   WAMIS
===================================== ==================== ==================
``data/dam_points_kwater.csv``         소양강**댐**          소양강
같은 파일(보)                           강정고령              강정고령**보**
``reservoir_points.json``              소양**호**            소양강
===================================== ==================== ==================

앞의 둘은 접미사(댐/보) 차이뿐이라 :func:`normalize` 로 정리된다. 문제는 셋째다.
**담수호 이름은 댐 이름과 아예 다른 경우가 있다** — 옥정호를 만든 댐은 섬진강댐이고
파로호를 만든 댐은 화천댐이다. 규칙으로 유도할 수 없으므로 :data:`LAKE_ALIASES`
에 손으로 적었다.

⚠ **없는 댐코드를 물어도 WAMIS 는 ``success``/0 으로 답한다**(오류가 아니다).
그래서 오타는 "자료가 없는 댐"으로 둔갑해 조용히 빈 CSV 를 만든다. 코드를
쓰기 전에 :func:`resolve` 로 **목록에 있는지 먼저 확인**하는 이유다.

사용:
    from s1.wamis.dams import fetch_dams, resolve
    dams = fetch_dams()
    resolve("옥정호", dams)      # -> Dam(damcd='4001110', damnm='섬진강', ...)
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from s1.core.paths import DATA_DIR, PROJECT_DIR
from s1.wamis.client import rows

# 대권역 코드 — WAMIS 는 전체 목록을 한 번에 주지 않아 권역별로 5번 물어야 한다.
BASINS = ("1", "2", "3", "4", "5")   # 한강 낙동강 금강 섬진강 영산강

DAM_POINTS_CSV = DATA_DIR / "dam_points_kwater.csv"     # 다목적댐·보·용수댐 52곳
RESERVOIR_POINTS_JSON = PROJECT_DIR / "reservoir_points.json"   # 담수호 21곳

# 담수호 이름 → WAMIS 댐 이름. **규칙으로 안 되는 것만** 적는다.
# 2026-09-09 에 reservoir_points.json 의 좌표와 dam_points_kwater.csv 의 댐
# 좌표를 대조해 확인했다(전부 10 km 이내 — 호수 중심과 댐 축의 거리).
LAKE_ALIASES = {
    "옥정호": "섬진강",     # 섬진강댐이 만든 호수
    "파로호": "화천",       # 화천댐
    "진양호": "남강",       # 남강댐
    "소양호": "소양강",     # 소양강댐
    "주암호": "주암(본)",   # 주암댐 본댐 — 조절지댐(주암(조))과 별개다
}

# 지점명 → WAMIS 댐 이름. 접미사 정리로도 안 붙는 것만.
NAME_ALIASES = {
    "주암댐": "주암(본)",
    "주암조절지댐": "주암(조)",
}


@dataclass(frozen=True)
class Dam:
    """WAMIS ``mn_dammain`` 한 줄."""
    damcd: str          # 댐코드 (7자리)
    damnm: str          # 댐 이름
    bbsnnm: str | None  # 대권역 이름
    sbsncd: str | None  # 표준유역코드
    mggvnm: str | None  # 관리기관 (보·소규모 댐은 None 인 경우가 있다)

    @property
    def label(self) -> str:
        return f"{self.damnm}({self.damcd})"


def normalize(name: str) -> str:
    """이름 비교용 키. 괄호·공백·가운뎃점을 지우고 꼬리의 댐/보/호/저수지를 뗀다.

    ``소양강댐``·``소양호``·``소양강`` 이 같은 키(``소양강``/``소양``)로 가지는
    않는다 — 그건 :data:`LAKE_ALIASES` 의 몫이다. 여기서는 **접미사만** 다룬다.
    """
    s = re.sub(r"[()\s·]", "", name)
    return re.sub(r"(댐|보|호|저수지)$", "", s)


def fetch_dams(**kw) -> list[Dam]:
    """전국 댐·보 목록. 권역 5개를 순서대로 받아 합친다(2026-09-09 기준 79곳)."""
    out: list[Dam] = []
    for basin in BASINS:
        for r in rows("wkd", "mn_dammain", {"basin": basin}, **kw):
            out.append(Dam(
                damcd=str(r.get("damcd", "")).strip(),
                damnm=str(r.get("damnm", "")).strip(),
                bbsnnm=r.get("bbsnnm"),
                sbsncd=r.get("sbsncd"),
                mggvnm=r.get("mggvnm"),
            ))
    return out


def build_index(dams: list[Dam]) -> dict[str, Dam]:
    """정규화 이름 → Dam. 이름이 겹치면 **먼저 온 것**을 남긴다(권역 순)."""
    idx: dict[str, Dam] = {}
    for d in dams:
        idx.setdefault(normalize(d.damnm), d)
    return idx


def resolve(name: str, dams: list[Dam] | dict[str, Dam]) -> Dam | None:
    """이름 하나를 Dam 으로. 못 찾으면 ``None`` (호출자가 보고하도록 남긴다).

    순서: 댐코드 그대로 → 별칭표 → 정규화 이름.
    """
    idx = dams if isinstance(dams, dict) else build_index(dams)
    key = name.strip()

    if key.isdigit():                                   # 이미 댐코드로 준 경우
        for d in (dams.values() if isinstance(dams, dict) else dams):
            if d.damcd == key:
                return d
        return None

    for table in (LAKE_ALIASES, NAME_ALIASES):
        if key in table:
            return idx.get(normalize(table[key]))
    return idx.get(normalize(key))


def load_kwater_points() -> list[str]:
    """``data/dam_points_kwater.csv`` 의 지점명. 촬영계획·대시보드가 쓰는 그 52곳."""
    p = Path(DAM_POINTS_CSV)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return [row["지점명"] for row in csv.DictReader(fh) if row.get("지점명")]


def load_reservoir_points() -> list[str]:
    """``reservoir_points.json`` 의 담수호 이름. 가뭄 산출이 보는 그 21곳."""
    p = Path(RESERVOIR_POINTS_JSON)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return list((json.load(fh).get("lakes") or {}).keys())
