# -*- coding: utf-8 -*-
"""ESA **촬영 계획**(acquisition plan)에서 한반도 통과 예정을 뽑는다.

카탈로그 감시([monitor_new_scenes.py](monitor_new_scenes.py))는 **이미 찍힌 것**만
본다. 등재까지 3~6시간 걸리므로 "오늘 저녁에 찍히나?"에는 답하지 못한다. 그
답은 ESA가 3주치 미리 공개하는 계획 KML에 있다.

    https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans

하는 일
-------
1. 위 페이지에서 위성별 최신 계획 KML 주소를 긁는다(`s1c_mp_user_<시작>_<끝>`).
2. 내려받아 `downloads/plans/`에 캐시한다(같은 파일은 다시 받지 않는다).
3. Placemark(=datatake)마다 시각·궤도·폴리곤을 읽어 **한반도와 겹치는 것만**
   남기고, 겹치는 구간의 **시도 이름**과 **관심 지점(댐·보 51곳) 포함 여부**를
   붙인다.

의존성 없음 — `urllib`·`xml.etree`·`csv` 등 표준 라이브러리만. 점-다각형 판정은
`footprint_label`(그 아래로는 `monitor_new_scenes`의 ray-casting)을 쓴다.

⚠ **계획은 계획이다.** ESA는 수시로 갱신하고, 실제 촬영이 빠지기도 한다
(2026-07-08 S1C 공백이 그랬다). 이 도구의 출력은 "예정"이지 보장이 아니다.

실행
----
    python -m s1.tools.monitor.acquisition_plan                # 앞으로 7일
    python -m s1.tools.monitor.acquisition_plan --days 14      # 더 멀리
    python -m s1.tools.monitor.acquisition_plan --dams-only    # 댐·보가 드는 것만
    python -m s1.tools.monitor.acquisition_plan --json         # 대시보드가 쓰는 형식

자세한 설명은 docs/pipeline/ACQUISITION_PLAN_KR.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree as ET

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from s1.core.paths import DOWNLOADS_DIR, KOREA_PENINSULA           # noqa: E402
from s1.tools.monitor.footprint_label import (SIDO_GEOJSON, SidoIndex,  # noqa: E402
                                              load_points, points_inside)
from s1.tools.monitor.monitor_new_scenes import (Boundary, KOREA_BBOX,  # noqa: E402
                                                 load_rings, point_in_ring)

PLAN_PAGE = "https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans"
PLAN_HOST = "https://sentinels.copernicus.eu"
PLAN_DIR = DOWNLOADS_DIR / "plans"
PLAN_CACHE = DOWNLOADS_DIR / "plan_cache.json"
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (S1 scene monitor)"}

# 링크 이름이 곧 계획 기간이다: s1c_mp_user_20260814t181556_20260905t200400
LINK_RE = re.compile(
    r'href="([^"]*?/documents/d/sentinel/(s1[a-d])_mp_user_'
    r'(\d{8}t\d{6})_(\d{8}t\d{6}))"', re.I)


def plan_links(timeout: int = 60) -> dict[str, tuple[str, datetime, datetime]]:
    """위성별 **가장 최신** 계획 링크. 반환: {'s1c': (url, 시작, 끝)}."""
    req = urllib.request.Request(PLAN_PAGE, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "replace")

    best: dict[str, tuple[str, datetime, datetime]] = {}
    for href, sat, start, end in LINK_RE.findall(html):
        url = href if href.startswith("http") else PLAN_HOST + href
        t0 = datetime.strptime(start, "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc)
        t1 = datetime.strptime(end, "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc)
        sat = sat.lower()
        # 계획은 겹쳐 가며 여러 번 올라온다 — 시작이 가장 늦은 것이 최신 판이다.
        if sat not in best or t0 > best[sat][1]:
            best[sat] = (url, t0, t1)

    # 링크를 HTML에서 정규식으로 긁는다. ESA가 페이지 구조나 파일명 규칙을 바꾸면
    # 여기서 0개가 되는데, 그대로 두면 "예정 없음"으로 보여 **촬영이 없는 것과
    # 구별되지 않는다.** 그래서 조용히 빈 목록을 돌려주지 않고 소리내어 실패한다
    # (창은 이 메시지를 상태줄에 띄우고, CLI 는 그대로 죽는다).
    if not best:
        raise RuntimeError(
            f"계획 링크를 찾지 못했습니다({len(html):,}바이트 응답). ESA 페이지 "
            f"구조나 파일명 규칙이 바뀌었을 수 있습니다 — LINK_RE 를 확인하세요: "
            f"{PLAN_PAGE}")
    return best


def orbit_dir(begin: datetime) -> str:
    """상행/하행. 계획 KML에는 이 값이 없어 **관측 시각으로** 판정한다.

    Sentinel-1은 태양동기 궤도라 지역시각이 고정이다 — 한반도 경도에서 상승
    궤도는 KST 18시대, 하강 궤도는 KST 06시대에 지난다
    (ORBIT_CALENDAR_202607_08_KR.md 1-1절의 환산표와 같은 규칙).
    """
    return "상행" if begin.astimezone(KST).hour >= 12 else "하행"


def download_plan(url: str, out_dir: Path = PLAN_DIR, timeout: int = 180) -> Path:
    """계획 KML을 캐시에 받아 둔다(이미 있으면 그대로 쓴다). 3 MB 안팎."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / (url.rstrip("/").rsplit("/", 1)[-1] + ".kml")
    if path.exists() and path.stat().st_size > 0:
        return path
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    path.write_bytes(data)
    # 오래된 계획은 남겨 둘 이유가 없다(같은 기간을 새 판이 덮는다).
    for old in sorted(out_dir.glob("*.kml"))[:-6]:
        old.unlink(missing_ok=True)
    return path


def _ns(tag: str) -> str:
    return "{http://www.opengis.net/kml/2.2}" + tag


def parse_plan(path: Path) -> list[dict]:
    """계획 KML → datatake 목록.

    Placemark 하나가 datatake 하나다. `ExtendedData`에 위성·모드·궤도가,
    `LinearRing`에 발자국이 들어 있다. 시각은 **UTC**(접미사 없이 적혀 있다).
    """
    out: list[dict] = []
    for _event, pm in ET.iterparse(str(path), events=("end",)):
        if pm.tag != _ns("Placemark"):
            continue
        data = {d.get("name"): (d.findtext(_ns("value")) or "")
                for d in pm.iter(_ns("Data"))}
        coords = pm.findtext(f".//{_ns('coordinates')}") or ""
        ring = []
        for token in coords.split():
            parts = token.split(",")
            if len(parts) >= 2:
                ring.append((float(parts[0]), float(parts[1])))
        if len(ring) >= 3:
            out.append({
                "sat": (data.get("SatelliteId") or "").upper(),
                "mode": data.get("Mode") or "",
                "pol": data.get("Polarisation") or "",
                "abs": data.get("OrbitAbsolute") or "",
                "rel": data.get("OrbitRelative") or "",
                "datatake": data.get("DatatakeId") or "",
                "begin": pm.findtext(f".//{_ns('begin')}") or "",
                "end": pm.findtext(f".//{_ns('end')}") or "",
                "ring": ring,
            })
        pm.clear()                      # 3 MB 파일을 통째로 들고 있지 않는다
    return out


def bbox_overlaps(ring: list[tuple[float, float]], bbox: list[float]) -> bool:
    """싼 1차 필터. 지구 반대편 datatake까지 표본할 이유가 없다."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return not (max(xs) < bbox[0] or min(xs) > bbox[2]
                or max(ys) < bbox[1] or min(ys) > bbox[3])


class KoreaGrid:
    """한반도 **육지 표본 점**을 한 번만 만들어 두고 재사용한다.

    왜 이렇게 하나 — 계획 datatake는 위도 10°를 넘는 긴 띠라, 촬영된 프레임처럼
    건건이 격자를 뿌리면 한 건에 수만 점이 든다(실측: 35건 50초). 육지 점
    6천 개를 미리 만들어 두고 "그중 몇 개가 이 띠 안에 드나"만 세면 같은 일이
    0.5초에 끝난다.

    덤으로 숫자의 뜻이 분명해진다. 띠 안에서 육지가 차지하는 비율(대부분 바다라
    작게 나온다)이 아니라 **한반도 육지의 몇 %를 덮나**가 된다.
    """

    def __init__(self, boundary: Boundary | None, sido: SidoIndex | None,
                 bbox: list[float], step: float = 0.05) -> None:
        self.points: list[tuple[float, float, str]] = []
        if boundary is None:
            return
        y = bbox[1]
        while y <= bbox[3]:
            x = bbox[0]
            while x <= bbox[2]:
                if boundary.contains(x, y):
                    self.points.append((x, y, (sido.at(x, y) if sido else "") or ""))
                x += step
            y += step

    def cover(self, rings: list[list[tuple[float, float]]],
              min_share: float = 8.0, max_names: int = 3) -> tuple[float, str]:
        """(한반도 육지 커버%, "충남·전북")."""
        if not self.points:
            return 0.0, ""
        counts: dict[str, int] = {}
        n_hit = 0
        for x, y, name in self.points:
            if any(point_in_ring(x, y, r) for r in rings):
                n_hit += 1
                if name:
                    counts[name] = counts.get(name, 0) + 1
        pct = 100.0 * n_hit / len(self.points)
        names = ""
        if counts:
            ranked = sorted(counts.items(), key=lambda kv: -kv[1])
            keep = [n for n, c in ranked if 100.0 * c / n_hit >= min_share]
            names = "·".join(keep[:max_names]) or ranked[0][0]
        return pct, names


class PlanResult(NamedTuple):
    """`korea_passes` 결과. `until`을 같이 돌려주는 이유는 아래 참고."""

    rows: list[dict]
    until: str          # 계획 파일이 덮는 마지막 시각(UTC ISO). 없으면 ""
    plans: dict         # {'s1c': (파일명, 시작, 끝)} — 어떤 판을 봤는지


def korea_passes(days: int = 7, mode: str = "IW", step: float = 0.1,
                 bbox: list[float] | None = None) -> PlanResult:
    """앞으로 `days`일 안에 한반도를 지나는 계획 datatake 목록(가까운 순).

    각 항목: 시작·끝(UTC), 위성, 상대궤도, 상행/하행, 시도 이름, 댐·보 이름.

    **`until`(계획이 덮는 끝)을 같이 돌려준다.** 계획 파일은 약 3주치라
    `--days 30`을 줘도 그 뒤는 알 수 없는데, 결과만 보면 "예정 없음"과
    "계획이 아직 없음"이 똑같이 빈 목록으로 보인다. 둘을 구별하려면 호출한
    쪽이 이 값을 같이 보여 줘야 한다.
    """
    bbox = bbox or KOREA_BBOX
    boundary = Boundary(load_rings(KOREA_PENINSULA)) if KOREA_PENINSULA.exists() else None
    sido = SidoIndex(SIDO_GEOJSON) if SIDO_GEOJSON.exists() else None
    grid = KoreaGrid(boundary, sido, bbox, step)
    points = load_points()

    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    rows: list[dict] = []

    links = plan_links()
    plans: dict = {}
    for sat, (url, t0, t1) in sorted(links.items()):
        if sat == "s1a":
            continue                       # 2026-06-29 퇴역
        path = download_plan(url)
        plans[sat] = (path.name, t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      t1.strftime("%Y-%m-%dT%H:%M:%SZ"))
        for dt in parse_plan(path):
            if mode and dt["mode"] != mode:
                continue
            try:
                begin = datetime.fromisoformat(dt["begin"]).replace(tzinfo=timezone.utc)
                end = datetime.fromisoformat(dt["end"]).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if begin < now or begin > until:
                continue
            if not bbox_overlaps(dt["ring"], bbox):
                continue
            rings = [dt["ring"]]
            pct, where = grid.cover(rings)
            if pct <= 0:
                continue                   # 상자에는 걸쳐도 한반도는 안 스친다
            dams = points_inside(rings, points)
            rows.append({
                "begin": begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sat": dt["sat"], "rel": dt["rel"], "abs": dt["abs"],
                "dir": orbit_dir(begin),
                "pol": dt["pol"], "datatake": dt["datatake"],
                "where": where, "cover_pct": round(pct, 1),
                "dams": dams,
            })

    rows.sort(key=lambda r: r["begin"])
    # 계획이 덮는 끝은 위성별 끝 중 **가장 이른 것**이다 — 그 뒤로는 한쪽
    # 위성만 알고 있어 "예정 없음"이라고 말할 수 없다.
    ends = [v[2] for v in plans.values()]
    return PlanResult(rows, min(ends) if ends else "", plans)


def save_cache(result: "PlanResult", fetched: str) -> None:
    try:
        PLAN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PLAN_CACHE.write_text(json.dumps({"fetched": fetched,
                                          "until": result.until,
                                          "plans": result.plans,
                                          "rows": result.rows},
                                         ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass


def load_cache() -> dict:
    try:
        return json.loads(PLAN_CACHE.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def kst_str(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.astimezone(KST):%m-%d %H:%M}"
    except ValueError:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser(description="ESA 촬영계획에서 한반도 통과 예정 뽑기")
    ap.add_argument("--days", type=int, default=7, help="앞으로 며칠. 기본 7")
    ap.add_argument("--mode", default="IW", help="관측 모드. 빈 문자열이면 전부")
    ap.add_argument("--step", type=float, default=0.1,
                    help="한반도 육지 표본 격자 간격(도). 기본 0.1(≈10 km) — "
                         "촬영된 프레임(0.05)보다 성긴 이유는 KoreaGrid 주석 참고")
    ap.add_argument("--dams-only", action="store_true",
                    help="댐·보가 하나라도 드는 통과만")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass

    result = korea_passes(days=args.days, mode=args.mode, step=args.step)
    rows = [r for r in result.rows if r["dams"]] if args.dams_only else result.rows
    save_cache(result, datetime.now(KST).strftime("%m-%d %H:%M"))

    if args.json:
        print(json.dumps({"until": result.until, "plans": result.plans,
                          "rows": rows}, ensure_ascii=False, indent=1))
        return 0

    print(f"■ 앞으로 {args.days}일 한반도 촬영 계획 — {len(rows)}건 "
          f"(ESA 계획 KML, 갱신 {datetime.now(KST):%m-%d %H:%M} KST)")
    for r in rows:
        dams = f"  댐·보 {len(r['dams'])}곳: {', '.join(r['dams'][:4])}" if r["dams"] else ""
        print(f"  {kst_str(r['begin'])} KST  {r['sat']} rel{r['rel']:>3} {r['dir']}  "
              f"{r['where'] or '-':<22} 한반도 {r['cover_pct']:>5.1f}%{dams}")

    # 계획이 어디까지 덮는지 반드시 같이 말한다 — 안 그러면 "예정 없음"과
    # "계획이 아직 안 나옴"이 똑같이 빈 목록으로 보인다.
    for sat, (fname, _t0, t1) in sorted(result.plans.items()):
        print(f"\n  {sat.upper()} 계획: {kst_str(t1)} KST 까지  ({fname})")
    if not rows:
        print("  → 위 기간 안에는 한반도 통과가 없다. 그 뒤는 계획이 아직 없다.")
    print("\n⚠ 계획은 수시로 바뀐다. 촬영 후 카탈로그 등재까지 3~6시간 더 걸린다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
