# -*- coding: utf-8 -*-
"""
한반도 신규 Sentinel-1 촬영 감시 — Copernicus Data Space STAC를 조회해 아직
못 본 씬이 올라오면 알린다.

**의존성 없음**: 인증 불필요(STAC /v1/search는 공개), **표준 라이브러리만** 쓴다.
numpy·shapely는 물론 이 저장소의 다른 모듈도 import하지 않으므로, 이 파일 하나만
있으면 시스템 파이썬으로도 돈다(경계 폴리곤 파일은 필요 — --boundary 참고).

왜 footprint로 거르나
---------------------
bbox(외접 사각형)로만 판정하면 **중국·일본 프레임이 신규로 잡힌다.** Sentinel-1
IW 프레임은 궤도 방위각만큼 기울어진 평행사변형이라, 상자에 걸리는 것과 한반도를
찍은 것은 다르다. 2026-08-18 실측에서 알림 3건이 전부 한반도 교집합 0.00%인
규슈·산둥 프레임이었다. 그래서 STAC이 주는 실제 footprint(`geometry`)를
`geojson/Korea_Peninsula.geojson`과 대조해 겹침 비율을 재고, `--min-overlap`
미만은 버린다(저장소 표준과 같은 1%).

겹침 비율은 **격자 표본**으로 잰다. shapely 없이 면적 교집합을 정확히 구하려면
폴리곤 클리핑을 구현해야 하는데 감시에는 그만한 정밀도가 필요 없다. footprint
안에 일정 간격(--step, 기본 0.04° ≈ 4 km) 격자점을 뿌리고 그중 몇 %가 경계
안인지 세면 충분하다.

동작
  1) 최근 --days 일 범위로 STAC 검색(sentinel-1-grd, 한반도 bbox).
  2) footprint 겹침이 --min-overlap 미만인 프레임 제외(--no-filter로 끌 수 있다).
  3) 상태파일(--state)의 "이미 본 씬 ID"와 비교해 새 씬만 골라낸다.
  4) 새 씬이 있으면 콘솔 + 로그파일(--log)에 기록하고, 마지막 줄에
     "NEW_SCENES=<n>"을 출력한다(PowerShell 래퍼가 이 값으로 알림 여부 판단).
  5) 상태파일을 갱신한다.

첫 실행은 현재 카탈로그를 "이미 본 것"으로 baseline 등록만 하고 알리지 않는다
(과거 씬 도배 방지). 이후부터 진짜 신규만 알린다.

⚠ 시각은 STAC 그대로 UTC다. 하강궤도는 UTC 21시대라 **KST로는 다음 날 새벽**이라
   양쪽을 같이 찍는다(ORBIT_CALENDAR_202607_08_KR.md 1-1절).

실행(단발):
    python -m s1.tools.monitor.monitor_new_scenes
    python -m s1.tools.monitor.monitor_new_scenes --days 5 --min-overlap 1
    python monitor_new_scenes.py --no-filter          # 옛 동작(bbox만)

백그라운드/주기 실행은 scripts/monitor_new_scenes.ps1 및 SCENE_MONITOR_KR.md 참고.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 이 파일은 <저장소루트>/s1/tools/monitor/monitor_new_scenes.py 다.
# s1.core.paths 를 import 하면 패키지 의존이 생기므로 파일 위치로 루트를 찾는다.
PROJECT_DIR = Path(__file__).resolve().parents[3]

STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
# 한반도(제주~북한 최북단)를 넉넉히 감싸는 검색 상자. 북한은 북위 43.0°까지
# 올라가므로 예전 기본값(40°)으로는 북부를 통째로 놓쳤다. 넓힌 만큼 들어오는
# 중국·러시아·일본 프레임은 아래 footprint 필터가 걷어낸다.
KOREA_BBOX = [123.5, 32.0, 131.5, 43.5]
DEFAULT_STATE = PROJECT_DIR / "downloads" / "monitor_state.json"
DEFAULT_LOG = PROJECT_DIR / "downloads" / "new_scenes.log"
DEFAULT_BOUNDARY = PROJECT_DIR / "geojson" / "Korea_Peninsula.geojson"
KST = timezone(timedelta(hours=9))


# --- 순수 파이썬 point-in-polygon -------------------------------------------

def load_rings(path: Path) -> list[list[tuple[float, float]]]:
    """(Multi)Polygon 외곽 링을 [(lon, lat), ...] 목록으로. 구멍은 무시한다
    (해안선 판정에 충분하고, 내륙 호수를 '한반도 아님'으로 셀 이유도 없다)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        geoms = [data["geometry"]]
    else:
        geoms = [data]
    rings: list[list[tuple[float, float]]] = []
    for g in geoms:
        if not g:
            continue
        if g["type"] == "Polygon":
            rings.append([(float(p[0]), float(p[1])) for p in g["coordinates"][0]])
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                rings.append([(float(p[0]), float(p[1])) for p in poly[0]])
    return rings


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    """even-odd ray casting. 링 하나에 대한 내부 판정."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            denom = yj - yi or 1e-12
            if x < (xj - xi) * (y - yi) / denom + xi:
                inside = not inside
        j = i
    return inside


class Boundary:
    """경계 폴리곤 묶음. 1도 격자 색인으로 링 후보를 좁혀 빠르게 판정한다.

    Korea_Peninsula.geojson은 링 1,766개·꼭짓점 9,711개다. 점마다 전 링을
    훑으면 느리므로, 링의 bbox가 걸치는 격자칸에만 등록해 두고 조회할 때
    그 칸의 링만 본다. 바다 위 점은 빈 칸이라 즉시 False가 된다.
    """

    def __init__(self, rings: list[list[tuple[float, float]]]) -> None:
        self.rings = rings
        self.index: dict[tuple[int, int], list[int]] = {}
        for k, ring in enumerate(rings):
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            for cx in range(int(min(xs) // 1), int(max(xs) // 1) + 1):
                for cy in range(int(min(ys) // 1), int(max(ys) // 1) + 1):
                    self.index.setdefault((cx, cy), []).append(k)

    def contains(self, x: float, y: float) -> bool:
        for k in self.index.get((int(x // 1), int(y // 1)), ()):
            if point_in_ring(x, y, self.rings[k]):
                return True
        return False


def overlap_percent(geom: dict, boundary: Boundary, step: float = 0.04) -> float:
    """footprint 면적 대비 경계와의 겹침(%) — 격자 표본 근사.

    footprint bbox에 step 간격 격자를 뿌려 footprint 내부 점만 남기고, 그중
    경계 내부 비율을 센다. 표본이 하나도 없으면(아주 작은 폴리곤) 0.0.
    """
    if not geom:
        return 0.0
    if geom.get("type") == "Polygon":
        polys = [geom["coordinates"]]
    elif geom.get("type") == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return 0.0
    rings = [[(float(p[0]), float(p[1])) for p in poly[0]] for poly in polys]
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    n_in = n_hit = 0
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if any(point_in_ring(x, y, r) for r in rings):
                n_in += 1
                if boundary.contains(x, y):
                    n_hit += 1
            x += step
        y += step
    return 100.0 * n_hit / n_in if n_in else 0.0


# --- STAC --------------------------------------------------------------------

def search_stac(bbox: list[float], collection: str, days: int,
                timeout: int = 60) -> list[dict]:
    """최근 days일 범위의 씬 조회. 반환: [{id, datetime, geometry, rel, sat}]."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    body = json.dumps({
        "collections": [collection],
        "bbox": bbox,
        "datetime": (f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
                     f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"),
        "limit": 500,
    }).encode("utf-8")
    req = urllib.request.Request(STAC_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    feats = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        feats.append({
            "id": f["id"],
            "datetime": p.get("datetime", ""),
            "geometry": f.get("geometry"),
            "rel": p.get("sat:relative_orbit"),
            # 상승/하강. 감시 알림에는 쓰지 않지만 scene_dashboard 가 궤도 방향을
            # 표시하는 데 쓴다(같은 조회를 두 번 하지 않으려고 여기서 넘긴다).
            "state": p.get("sat:orbit_state"),
            "sat": (p.get("platform") or "")[-2:].upper(),
        })
    feats.sort(key=lambda x: x["datetime"])
    return feats


def kst_str(iso: str) -> str:
    """UTC ISO 문자열 → 'MM-DD HH:MM'(KST). 하강궤도는 날짜가 하루 넘어간다."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%m-%d %H:%M")
    except Exception:                                        # noqa: BLE001
        return "?"


# --- 상태·로그 ---------------------------------------------------------------

def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen_ids": [], "initialized": False, "last_check": ""}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def log_line(log_path: Path, msg: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="한반도 신규 Sentinel-1 촬영 감시(STAC)")
    ap.add_argument("--bbox", type=float, nargs=4, default=KOREA_BBOX,
                    metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    ap.add_argument("--collection", default="sentinel-1-grd",
                    help="sentinel-1-grd 또는 sentinel-1-slc")
    ap.add_argument("--days", type=int, default=4, help="조회할 최근 일수")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY,
                    help="한반도 경계 GeoJSON. 없으면 footprint 필터를 끄고 진행한다")
    ap.add_argument("--min-overlap", type=float, default=1.0,
                    help="한반도 교집합 하한(%%). 미만이면 제외. 기본 1")
    ap.add_argument("--step", type=float, default=0.04,
                    help="겹침 표본 격자 간격(도). 작을수록 정밀·느림. 기본 0.04")
    ap.add_argument("--no-filter", action="store_true",
                    help="footprint 필터를 끄고 bbox 결과를 그대로 쓴다(옛 동작)")
    ap.add_argument("--quiet", action="store_true", help="새 씬 없을 때 조용히")
    args = ap.parse_args()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    try:
        feats = search_stac(args.bbox, args.collection, args.days)
    except Exception as e:      # 네트워크·서버 오류로 루프가 죽지 않게 경고만
        print(f"[{now_str}] STAC 조회 실패: {e}", file=sys.stderr)
        print("NEW_SCENES=-1")
        return 2

    # --- footprint 필터 ------------------------------------------------------
    n_raw = len(feats)
    dropped: list[str] = []
    if not args.no_filter:
        if not Path(args.boundary).exists():
            print(f"[{now_str}] ⚠ 경계 파일 없음({args.boundary}) — "
                  f"footprint 필터를 끄고 진행합니다.", file=sys.stderr)
        else:
            boundary = Boundary(load_rings(args.boundary))
            kept = []
            for f in feats:
                pct = overlap_percent(f["geometry"], boundary, args.step)
                f["overlap"] = pct
                if pct >= args.min_overlap:
                    kept.append(f)
                else:
                    dropped.append(f"{f['id'][-14:]}({pct:.1f}%)")
            feats = kept

    state = load_state(args.state)
    seen = set(state.get("seen_ids", []))
    current_ids = [f["id"] for f in feats]
    new_feats = [f for f in feats if f["id"] not in seen]

    if dropped:
        print(f"  [footprint 제외] 한반도 교집합 {args.min_overlap}% 미만 "
              f"{len(dropped)}개: {', '.join(dropped[:5])}"
              + (" ..." if len(dropped) > 5 else ""))

    if not state.get("initialized"):
        state = {"seen_ids": current_ids, "initialized": True,
                 "last_check": now_str}
        save_state(args.state, state)
        msg = (f"[{now_str}] 초기화: {args.collection} 최근 {args.days}일 "
               f"{len(current_ids)}개 씬을 baseline 등록(알림 없음). "
               f"조회 {n_raw} → 한반도 {len(current_ids)}")
        print(msg)
        log_line(args.log, msg)
        print("NEW_SCENES=0")
        return 0

    if new_feats:
        header = f"[{now_str}] 신규 {args.collection} {len(new_feats)}개 발견:"
        print(header)
        log_line(args.log, header)
        for f in new_feats:
            ov = f.get("overlap")
            line = (f"  + {f['id']}  (UTC {f['datetime'][:16]} / "
                    f"KST {kst_str(f['datetime'])}"
                    + (f" / rel{f['rel']}" if f["rel"] is not None else "")
                    + (f" / 한반도 {ov:.1f}%" if ov is not None else "") + ")")
            print(line)
            log_line(args.log, line)
    elif not args.quiet:
        print(f"[{now_str}] 신규 없음 (최근 {args.days}일, 조회 {n_raw} → "
              f"한반도 {len(current_ids)}개 확인).")

    # 상태 갱신(조회창을 벗어난 과거 ID도 유지하려고 합집합)
    state["seen_ids"] = sorted(seen | set(current_ids))
    state["last_check"] = now_str
    save_state(args.state, state)

    print(f"NEW_SCENES={len(new_feats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
