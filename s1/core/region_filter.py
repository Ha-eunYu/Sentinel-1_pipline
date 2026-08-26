# -*- coding: utf-8 -*-
"""전처리 **직전**에 타국 프레임을 걸러내는 마지막 방어선.

왜 전처리에도 필요한가
----------------------
모니터링·다운로드 단계에 footprint 판정이 있어도, zip 은 그 단계를 **거치지 않고**
들어온다.

- NAS `rsync --ignore-existing` — 로컬에서 지운 파일을 매번 복원한다
- 판정이 없는 다운로더(`download_aug_pair` 등)와 수동 복사
- 다른 세션의 작업

배치는 "zip 이 있으면 처리한다"가 전부라 제외 이력을 모른다. 실제로 `754B` 는
7/22 에 한반도 0% 로 판정해 지웠는데 7/23 NAS 재유입 → 8/19 배치가 집어
1.25 GB 산출물을 만들었다(FOREIGN_FRAME_COST_KR.md ②).

**앞단은 새로 들어오는 것을, 여기는 이미 들어와 있는 것을 막는다.**

2단계 판정 — 빠른 것 먼저
--------------------------
1. **STAC 메타 대조**(즉시): `data/relative_orbits_*.csv` 에 그 관측이 있고
   한반도 교집합이 기준 이상이면 통과. 조사 CSV 는 한반도 교차분만 담고 있다.
2. **KML 실측**(씬당 수 분): 1단계로 확정 못 한 것만. STAC 의 공칭 geometry 는
   대마도 프레임을 통과시키므로, 경계선 판정은 원본 zip 의 실측 footprint 로 한다.

CSV 는 특정 기간(2022~2026년 7·8월)만 담으므로 **행이 없다고 타국이 아니다.**
없으면 2단계로 넘긴다.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from s1.core.aoi import classify_region
from s1.core.paths import DATA_DIR

# 관측 식별 키 = 시작시각 + 절대궤도. 씬 ID 끝 4hex 는 제품 해시라 쓰면 안 된다
# (ISSUES_KR #16 — 같은 촬영을 다른 씬으로 센다).
KEY_RE = re.compile(r"_(\d{8}T\d{6})_\d{8}T\d{6}_(\d{6})_")

DEFAULT_CSV = DATA_DIR / "relative_orbits_sentinel-1-grd.csv"


def acquisition_key(name: str) -> tuple[str, str] | None:
    m = KEY_RE.search(name)
    return (m.group(1), m.group(2)) if m else None


def _load_csv(csv_path: Path) -> dict[tuple[str, str], dict]:
    if not csv_path.exists():
        return {}
    out: dict[tuple[str, str], dict] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = acquisition_key(row.get("id", ""))
            if k:
                out[k] = row
    return out


def filter_peninsula(
    zips,
    *,
    min_pct: float = 1.0,
    csv_path: Path | None = None,
    verbose: bool = True,
) -> tuple[list[Path], list[tuple[Path, str, float]]]:
    """한반도를 찍은 zip 만 남긴다. 반환 `(통과, 제외[(경로, 구분, 한반도%)])`.

    판정이 불가능한 제품은 **통과**시킨다 — 거르는 쪽으로 틀리면 멀쩡한 씬을
    조용히 빠뜨린다(같은 규약: `s1.core.aoi.classify_region`).
    """
    meta = _load_csv(csv_path or DEFAULT_CSV)
    keep: list[Path] = []
    dropped: list[tuple[Path, str, float]] = []
    checked = 0

    for z in zips:
        z = Path(z)
        row = meta.get(acquisition_key(z.name) or ("", ""))
        if row is not None:
            try:
                if float(row["kp_pct"]) >= min_pct:
                    keep.append(z)          # 1단계로 확정 — 실측 생략
                    continue
            except (KeyError, ValueError):
                pass

        zone, pen, _ = classify_region(z)    # 2단계 실측
        checked += 1
        if zone == "제3국":
            dropped.append((z, zone, pen))
        else:
            keep.append(z)

    if verbose:
        print(f"[지역 판정] 통과 {len(keep)} / 제외 {len(dropped)} "
              f"(KML 실측 {checked}건, 나머지는 STAC 메타로 확정)")
        for p, zone, pen in dropped:
            print(f"  제외({zone}, 한반도 {pen:.2f}%): {p.name}")
    return keep, dropped
