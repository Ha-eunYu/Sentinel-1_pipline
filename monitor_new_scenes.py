# -*- coding: utf-8 -*-
"""
한반도 신규 Sentinel-1 촬영 감시 — Copernicus Data Space STAC를 조회해 아직
못 본 씬이 올라오면 알린다. 인증 불필요(STAC /v1/search는 공개), 표준 라이브러리
(urllib)만 사용하므로 conda 환경 없이 시스템 파이썬으로도 돈다.

동작
  1) 최근 --days 일 범위로 STAC 검색(sentinel-1-grd, 한반도 bbox).
  2) 상태파일(--state, 기본 downloads/monitor_state.json)의 "이미 본 씬 ID"와
     비교해 새 씬만 골라낸다.
  3) 새 씬이 있으면 콘솔 + 로그파일(--log)에 기록하고, 요약 마지막 줄에
     "NEW_SCENES=<n>" 을 출력한다(PowerShell 래퍼가 이 값으로 알림 여부 판단).
     새 씬이 없으면 "NEW_SCENES=0".
  4) 상태파일을 갱신한다.

첫 실행은 현재 카탈로그에 있는 씬들을 "이미 본 것"으로 baseline 등록만 하고
알리지 않는다(과거 씬으로 도배되는 것 방지). 그 이후부터 진짜 신규만 알린다.

실행(단발):
    python monitor_new_scenes.py
    python monitor_new_scenes.py --days 5 --collection sentinel-1-grd
    python monitor_new_scenes.py --bbox 124 32 131 40

백그라운드/주기 실행은 monitor_new_scenes.ps1 및 SCENE_MONITOR_KR.md 참고.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
STAC_URL = "https://stac.dataspace.copernicus.eu/v1/search"
KOREA_BBOX = [124.0, 32.0, 131.0, 40.0]  # lon_min, lat_min, lon_max, lat_max
DEFAULT_STATE = PROJECT_DIR / "downloads" / "monitor_state.json"
DEFAULT_LOG = PROJECT_DIR / "downloads" / "new_scenes.log"


def search_stac(bbox: list[float], collection: str, days: int, timeout: int = 60) -> list[dict]:
    """최근 days일 범위의 씬을 STAC에서 조회. 반환: [{id, datetime}] (관측시각 오름차순)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    body = json.dumps({
        "collections": [collection],
        "bbox": bbox,
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 500,
    }).encode("utf-8")
    req = urllib.request.Request(STAC_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    feats = [{"id": f["id"], "datetime": f.get("properties", {}).get("datetime", "")}
             for f in data.get("features", [])]
    feats.sort(key=lambda x: x["datetime"])
    return feats


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen_ids": [], "initialized": False, "last_check": ""}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def log_line(log_path: Path, msg: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="한반도 신규 Sentinel-1 촬영 감시(STAC)")
    parser.add_argument("--bbox", type=float, nargs=4, default=KOREA_BBOX,
                        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    parser.add_argument("--collection", default="sentinel-1-grd",
                        help="sentinel-1-grd 또는 sentinel-1-slc")
    parser.add_argument("--days", type=int, default=4, help="조회할 최근 일수")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--quiet", action="store_true", help="새 씬 없을 때 조용히")
    args = parser.parse_args()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    try:
        feats = search_stac(args.bbox, args.collection, args.days)
    except Exception as e:  # 네트워크/서버 오류 시 루프가 죽지 않게 경고만
        print(f"[{now_str}] STAC 조회 실패: {e}", file=sys.stderr)
        print("NEW_SCENES=-1")
        return 2

    state = load_state(args.state)
    seen = set(state.get("seen_ids", []))
    current_ids = [f["id"] for f in feats]
    new_feats = [f for f in feats if f["id"] not in seen]

    if not state.get("initialized"):
        # 첫 실행: 현재 카탈로그를 baseline으로만 등록, 알리지 않음
        state = {"seen_ids": current_ids, "initialized": True, "last_check": now_str}
        save_state(args.state, state)
        msg = (f"[{now_str}] 초기화: {args.collection} 최근 {args.days}일 "
               f"{len(current_ids)}개 씬을 baseline 등록(알림 없음).")
        print(msg)
        log_line(args.log, msg)
        print("NEW_SCENES=0")
        return 0

    if new_feats:
        header = f"[{now_str}] 신규 {args.collection} {len(new_feats)}개 발견:"
        print(header)
        log_line(args.log, header)
        for f in new_feats:
            line = f"  + {f['id']}  ({f['datetime']})"
            print(line)
            log_line(args.log, line)
    elif not args.quiet:
        print(f"[{now_str}] 신규 없음 (최근 {args.days}일 {len(current_ids)}개 확인).")

    # 상태 갱신(기존 seen에 현재 결과 합집합 — 조회창을 벗어난 과거 ID도 유지)
    state["seen_ids"] = sorted(seen | set(current_ids))
    state["last_check"] = now_str
    save_state(args.state, state)

    print(f"NEW_SCENES={len(new_feats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
