# -*- coding: utf-8 -*-
"""한반도 Sentinel-1 파이프라인 **현황 창** — 회사 PC에 띄워 두는 작은 대시보드.

표 두 개로 본다.

1. **최근 촬영** — 최근 며칠간 Copernicus 카탈로그에 올라온 한반도 프레임을
   **촬영 하나당 한 줄**로. 관측시각(KST), 상대궤도·상승/하강, **대략적인
   위치(충남·전남 …)**, 한반도 겹침%, 원본 크기, 그리고 이 PC에서의 단계
   (미수신 → 받는중 → 대기 → 전처리중 → 완료).
2. **전처리** — 지금 굽는 씬(경과·기록된 GB), 대기 목록, 최근 완료.

카탈로그와 다운로드를 표 두 개로 나눠 두면 같은 촬영이 양쪽에 나와 눈이 두 번
간다. 어차피 둘을 잇는 것은 촬영시각이라 한 줄로 합치고, "어디까지 왔나"는
`상태` 칸 하나로 말한다.

감시 도구([monitor_new_scenes.py](monitor_new_scenes.py))는 "새 게 올라왔다"를
**알림 한 번**으로 알려 준다. 이 대시보드는 그 다음 질문 — "그래서 지금 어디까지
됐나" — 에 답한다. 상태를 따로 저장하지 않는다. 갱신할 때마다 파일 시스템과
STAC를 다시 읽어 **실제 상태 그대로** 그린다(기록을 따로 남기면 그 기록이
언젠가 실제와 어긋난다).

의존성
------
표준 라이브러리만. tkinter는 윈도우 파이썬에 기본 포함이다. 저장소 모듈은
`s1.core.paths`·`s1.core.scene`·`monitor_new_scenes` 셋만 쓰는데 모두 순수
파이썬이라 conda 환경(`s1_snappy` 등) 없이도 뜬다.

상태를 어떻게 판정하나
----------------------
| 단계 | 근거 |
| --- | --- |
| 미수신 | STAC에는 있는데 로컬에 zip이 없다 |
| 받는중 | `sentinel1_grd/*.part` (다운로더가 이어받기용으로 남기는 임시 파일) |
| 대기 | zip은 있는데 산출물 tif가 없다 |
| 전처리중 | **임시폴더**(`%TEMP%/frostrtc_*` 등)에 그 씬의 zip이 복사돼 있다 |
| 완료 | 산출물 tif가 있고 전처리중이 아니다 |

⚠ **tif가 있다고 완료가 아니다.** SNAP `gpt`는 출력 tif를 **처리하는 내내 쓴다**
(2026-08-18 실측: 처리 중이던 `0868`은 이미 2.32 GB짜리 tif를 갖고 있었고, 갓
시작한 `8E47`은 0 바이트였다). 그래서 완료 판정은 **임시폴더가 우선**이다.
배치 러너(`s1/preprocess/batch_runner.py`)가 씬마다 zip을 SSD 임시 하위폴더로
복사해 두고 끝나면 지우므로, 그 폴더가 곧 "지금 굽는 중"이라는 증거다.

배치가 비정상 종료하면 임시폴더가 남는다. `gpt.exe`가 하나도 없고 그 폴더가
`--stale-minutes`(기본 30분)보다 오래됐으면 **중단?** 으로 표시한다.

씬 대조 키
----------
**(관측 시작시각, 절대궤도)**. 씬 ID 끝 4hex는 제품 생성 해시라 같은 촬영도
재처리본마다 다르다(PREPROCESSING_SPEC_KR.md 4절, ISSUES #16).

실행
----
    python s1/tools/monitor/scene_dashboard.py             # 창 띄우기
    python s1/tools/monitor/scene_dashboard.py --once      # 콘솔에 한 번만 출력
    powershell -File scripts/scene_dashboard.ps1           # 콘솔 없이 띄우기

자세한 설명·작업 스케줄러 등록은 docs/pipeline/SCENE_DASHBOARD_KR.md 참고.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:            # 파일 경로로 직접 실행할 때
    sys.path.insert(0, str(PROJECT_DIR))

from s1.core.paths import (DOWNLOADS_DIR, GRD_DIR,               # noqa: E402
                           KOREA_PENINSULA, RTC_FROST_VH_DIR, rel)
from s1.core.scene import parse_scene                            # noqa: E402
from s1.tools.monitor import acquisition_plan                    # noqa: E402
from s1.tools.monitor.footprint_label import (SIDO_GEOJSON, SidoIndex,  # noqa: E402
                                              describe_footprint)
from s1.tools.monitor.monitor_new_scenes import (KOREA_BBOX, Boundary,  # noqa: E402
                                                 load_rings, search_stac)

KST = timezone(timedelta(hours=9))
CACHE_PATH = DOWNLOADS_DIR / "dashboard_cache.json"

# 배치 러너가 쓰는 임시폴더 접두사(s1/preprocess/batch_runner.py 호출부들).
TMP_PREFIXES = ("frostrtc_", "rtc_", "gtc_", "slcrtc_", "snapbatch_")

# 관측 시작시각(YYYYMMDDTHHMMSS). 절대궤도·씬ID는 s1.core.scene 이 뽑는다.
START_RE = re.compile(r"_(\d{8}T\d{6})_\d{8}T\d{6}_")


def scene_key(name: str) -> tuple[str, str] | None:
    """(관측 시작시각, 절대궤도) — STAC id·zip·tif를 잇는 키.

    씬 ID 4hex를 키로 쓰면 안 된다(제품 생성 해시라 재처리본마다 다르다).
    파일명 파싱은 규약을 한곳에 모아 둔 s1.core.scene 을 쓴다.
    """
    k = parse_scene(name)
    m = START_RE.search(name)
    if not k or not m:
        return None
    return (m.group(1), k.orbit)


def sat_label(name: str) -> str:
    """위성(S1A~S1D). 표마다 같은 자리·같은 이름의 칸으로 쓴다."""
    k = parse_scene(name)
    return k.platform if k else "-"


def sid_label(name: str) -> str:
    """씬 ID 4hex(예: `D635`). 문서·명령에서 씬을 부르는 이름이다."""
    k = parse_scene(name)
    return k.sid if k else "-"


def kst_of(name: str) -> str:
    """파일명에서 촬영시각을 KST `MM-DD HH:MM`으로."""
    m = START_RE.search(name)
    if not m:
        return "-"
    dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return f"{dt.astimezone(KST):%m-%d %H:%M}"


def short_id(name: str) -> str:
    """표시용 짧은 이름: 위성 + 촬영시각(KST) + 씬ID (예: `S1C 08-07 06:39 0868`).

    콘솔(--once) 전용이다. 창에서는 씬·촬영시각을 각각의 칸에 나눠 적는다.
    """
    k = parse_scene(name)
    if not k:
        return name[:28]
    return f"{k.platform} {kst_of(name)} {k.sid}"


# --- 로컬 상태 ---------------------------------------------------------------

@dataclass
class LocalState:
    """이 PC의 파일 상태 스냅샷. 키는 전부 (관측 시작시각, 절대궤도)."""

    zips: dict = field(default_factory=dict)        # key -> (Path, mtime, size)
    outs: dict = field(default_factory=dict)        # key -> (Path, mtime, size)
    busy: dict = field(default_factory=dict)        # key -> (파일명, 시작시각, stale)
    parts: dict = field(default_factory=dict)       # key -> (Path, mtime, size)
    gpt_procs: int = 0                              # -1 = 확인 실패
    scanned: float = 0.0

    def state_of(self, key) -> str:
        if key in self.busy:
            return "중단?" if self.busy[key][2] else "전처리중"
        if key in self.outs:
            return "완료"
        if key in self.zips:
            return "대기"
        if key in self.parts:
            return "받는중"
        return "미수신"

    def size_of(self, key) -> int | None:
        """원본 zip 크기. 받는 중이면 지금까지 받은 크기."""
        if key in self.zips:
            return self.zips[key][2]
        if key in self.parts:
            return self.parts[key][2]
        return None


def gpt_process_count() -> int:
    """돌고 있는 SNAP gpt 프로세스 수. tasklist는 어디에나 있어 의존성이 없다."""
    try:
        out = subprocess.run(["tasklist", "/fi", "imagename eq gpt.exe", "/nh"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return sum(1 for line in out.stdout.splitlines() if "gpt.exe" in line.lower())
    except Exception:                                        # noqa: BLE001
        return -1                                            # 확인 불가


def scan_local(out_dir: Path, out_suffix: str, stale_minutes: int = 30) -> LocalState:
    """다운로드·산출물·임시폴더를 훑어 현재 상태를 만든다."""
    st = LocalState(scanned=time.time())
    st.gpt_procs = gpt_process_count()

    if GRD_DIR.exists():
        for z in GRD_DIR.glob("*.zip"):
            key = scene_key(z.name)
            if key:
                s = z.stat()
                st.zips[key] = (z, s.st_mtime, s.st_size)
        for p in GRD_DIR.glob("*.part"):
            key = scene_key(p.name)
            if key:
                s = p.stat()
                st.parts[key] = (p, s.st_mtime, s.st_size)

    if out_dir.exists():
        for t in out_dir.glob(f"*{out_suffix}.tif"):
            key = scene_key(t.name)
            if key:
                s = t.stat()
                st.outs[key] = (t, s.st_mtime, s.st_size)

    # 전처리 중 — 배치 러너의 씬별 임시폴더가 근거(모듈 주석 참고).
    tmp_root = Path(tempfile.gettempdir())
    now = time.time()
    try:
        tmp_dirs = [d for d in tmp_root.iterdir()
                    if d.name.startswith(TMP_PREFIXES) and d.is_dir()]
    except OSError:
        tmp_dirs = []
    for d in tmp_dirs:
        try:
            copies = list(d.glob("*.zip"))
            # 시작 시각은 **임시폴더 생성시각**이다. 복사본 zip의 mtime을 보면
            # 안 된다 — shutil.copy2 가 원본 시각을 그대로 물려주므로 며칠 전
            # 값이 나온다(2026-08-18: "20시간 전 시작"으로 잘못 찍혔다).
            started = d.stat().st_ctime
        except OSError:
            continue
        for z in copies:
            key = scene_key(z.name)
            if not key:
                continue
            stale = st.gpt_procs == 0 and now - started > stale_minutes * 60
            st.busy[key] = (z.name, started, stale)
            st.outs.pop(key, None)      # 쓰는 중인 tif는 완료가 아니다
    return st


# --- CDSE 조회 ---------------------------------------------------------------

def fetch_cdse(days: int, collection: str, min_overlap: float,
               step: float) -> list[dict]:
    """STAC 조회 + footprint 요약. 화면에 그대로 그릴 수 있는 dict 목록을 준다."""
    feats = search_stac(KOREA_BBOX, collection, days)
    boundary = Boundary(load_rings(KOREA_PENINSULA)) if KOREA_PENINSULA.exists() else None
    sido = SidoIndex(SIDO_GEOJSON) if SIDO_GEOJSON.exists() else None

    rows = []
    for f in feats:
        pct, where = describe_footprint(f["geometry"], boundary, sido, step)
        if boundary is not None and pct < min_overlap:
            continue
        rows.append({
            "id": f["id"],
            "datetime": f["datetime"],
            "rel": f.get("rel"),
            "dir": {"ascending": "상행", "descending": "하행"}.get(f.get("state") or "", ""),
            "overlap": round(pct, 1),
            "where": where,
        })
    rows.sort(key=lambda r: r["datetime"], reverse=True)
    return rows


def merge_rows(cdse: list[dict], st: LocalState, days: int) -> list[dict]:
    """CDSE 목록과 로컬 보유분을 **씬 하나당 한 줄**로 합친다.

    카탈로그와 다운로드를 표 두 개로 나눠 두면 같은 촬영이 양쪽에 나와 눈이 두
    번 간다. 어차피 두 표를 잇는 것은 촬영시각이므로 한 줄에 합치고 `상태`
    칸으로 어디까지 왔는지를 말한다.

    CDSE에 없는데 로컬에는 있는 씬(조회 실패, 또는 카탈로그에서 내려간 옛 제품)도
    조회창 안이면 끼워 넣는다. 그런 줄은 궤도·위치를 알 수 없어 `-`로 둔다.
    """
    rows: list[dict] = []
    seen: set = set()
    for r in cdse:
        key = scene_key(r["id"])
        seen.add(key)
        zip_path = st.zips.get(key)
        # 이름은 로컬 파일이 있으면 그쪽을 쓴다 — 재처리본이면 씬 ID 4hex가
        # 카탈로그와 다를 수 있고, 명령에 붙여 넣을 것은 손에 있는 파일이다.
        name = zip_path[0].name if zip_path else r["id"]
        rows.append({
            "key": key,
            "when": r["datetime"],
            "sat": sat_label(name),
            "sid": sid_label(name),
            "rel": r["rel"],
            "orbit": f"rel{r['rel'] or '?'} {r['dir']}".strip(),
            "where": r["where"] or "-",
            "overlap": r["overlap"],
            "size": st.size_of(key),
            "state": st.state_of(key),
            "name": name,
        })

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    local_keys = set(st.zips) | set(st.parts) | set(st.outs) | set(st.busy)
    for key in local_keys - seen:
        try:
            dt = datetime.strptime(key[0], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue                       # 조회창 밖 — 전처리 표에서 본다
        src = st.zips.get(key) or st.parts.get(key) or st.outs.get(key)
        name = src[0].name if src else ""
        rows.append({
            "key": key,
            "when": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sat": sat_label(name) if name else "-",
            "sid": sid_label(name) if name else "-",
            "rel": None, "orbit": "-", "where": "-", "overlap": None,
            "size": st.size_of(key),
            "state": st.state_of(key),
            "name": name,
        })

    rows.sort(key=lambda r: r["when"], reverse=True)
    return rows


# 상태를 파이프라인 진행 순서로 매긴다. 오름차순으로 정렬하면 **손 볼 것이 위로**
# 온다(아직 안 받음 → 받는 중 → 대기 → 굽는 중 → 완료).
STATE_RANK = {"미수신": 0, "받는중": 1, "대기": 2, "전처리중": 3, "중단?": 4,
              "완료": 5}

# 머리글 클릭 정렬에서 쓸 열별 정렬값. 화면에 찍힌 문자열이 아니라 **원래 값**으로
# 정렬한다 — "1.12 GB"를 문자열로 세우면 9 GB가 10 GB보다 뒤로 간다.
SCENE_SORT = {
    "time": lambda row: row["raw"]["when"],
    "sat": lambda row: row["raw"]["sat"],
    "sid": lambda row: row["raw"]["sid"],
    "orbit": lambda row: (row["raw"]["rel"] if isinstance(row["raw"]["rel"], int)
                          else -1),
    "where": lambda row: row["raw"]["where"],
    "ov": lambda row: (row["raw"]["overlap"] if row["raw"]["overlap"] is not None
                       else -1.0),
    "size": lambda row: row["raw"]["size"] or -1,
    "st": lambda row: STATE_RANK.get(row["raw"]["state"], 9),
}

PROC_SORT = {
    "st": lambda row: STATE_RANK.get(row["state"], 9),
    "sat": lambda row: row["sat"],
    "sid": lambda row: row["sid"],
    "time": lambda row: row["obs"],
}

PLAN_SORT = {
    "time": lambda row: row["raw"]["begin"],
    "sat": lambda row: row["raw"]["sat"],
    "orbit": lambda row: int(row["raw"]["rel"] or 0),
    "where": lambda row: row["raw"]["where"],
    "cover": lambda row: row["raw"]["cover_pct"],
    "dams": lambda row: len(row["raw"]["dams"]),
}


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def save_cache(rows: list[dict], fetched: str) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"fetched": fetched, "rows": rows},
                                         ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass                                                 # 캐시는 있으면 좋은 것


# --- 표시용 도우미 -----------------------------------------------------------

def kst_hm(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.astimezone(KST):%m-%d %H:%M}"
    except Exception:                                        # noqa: BLE001
        return "?"


def ago(ts: float) -> str:
    """경과시간을 사람 말로. 초 단위는 이 화면에 필요 없다.

    이틀 안쪽은 분까지 붙인다 — 전처리 한 씬이 40~80분이라 "1시간 전"으로
    뭉개면 방금 시작한 것과 곧 끝날 것이 같아 보인다.
    """
    mins = max(0, int((time.time() - ts) / 60))
    if mins < 60:
        return f"{mins}분 전"
    if mins < 60 * 48:
        h, m = divmod(mins, 60)
        return f"{h}시간 {m}분 전" if m else f"{h}시간 전"
    return f"{mins // 1440}일 전"


def gb(size: int) -> str:
    return f"{size / 1024 ** 3:.2f} GB"


# --- 콘솔 출력(--once) -------------------------------------------------------

def plan_rows_for_once(args) -> tuple[list[dict], str]:
    """`--once`용 촬영 계획. 캐시가 `--plan-hours`보다 오래됐을 때만 새로 뽑는다.

    계획 조회는 KML 6 MB를 받아 훑는 일이라 10초 남짓 걸린다. 콘솔에서 상태만
    보려는데 매번 그걸 하게 두지 않는다.
    """
    def cached() -> tuple[list[dict], str]:
        c = acquisition_plan.load_cache()
        return c.get("rows", []), c.get("until", "")

    if args.plan_hours <= 0:
        return [], ""
    cache_path = acquisition_plan.PLAN_CACHE
    fresh = (cache_path.exists()
             and time.time() - cache_path.stat().st_mtime < args.plan_hours * 3600)
    if fresh:
        return cached()
    try:
        result = acquisition_plan.korea_passes(days=args.plan_days)
        acquisition_plan.save_cache(result, datetime.now(KST).strftime("%m-%d %H:%M"))
        return result.rows, result.until
    except Exception as e:                                   # noqa: BLE001
        print(f"  (촬영계획 조회 실패: {e} — 캐시를 씁니다)", file=sys.stderr)
        return cached()



def render_text(rows: list[dict], st: LocalState, fetched: str, args) -> str:
    out: list[str] = []
    add = out.append

    merged = merge_rows(rows, st, args.days)
    n_new = sum(1 for r in merged if r["state"] == "미수신")
    busy = [k for k in st.busy if not st.busy[k][2]]
    stalled = [k for k in st.busy if st.busy[k][2]]
    pending = [k for k in st.zips if k not in st.outs and k not in st.busy]

    add(f"■ 최근 촬영 {args.days}일 (CDSE 조회 {fetched}) — {len(merged)}개, "
        f"미수신 {n_new} · 보유 {len(st.zips)}")
    if not merged:
        add("  (조회창 안에 한반도 촬영이 없습니다)")
    else:
        add(f"  {'촬영(KST)':<12} {'위성':<5} {'씬':<6} {'궤도':<10} {'위치':<22} "
            f"{'한반도':>6} {'크기':>9}  상태")
    for r in merged[:args.scene_rows]:
        ov = f"{r['overlap']:.1f}%" if r["overlap"] is not None else "-"
        size = gb(r["size"]) if r["size"] else "-"
        add(f"  {kst_hm(r['when']):<12} {r['sat']:<5} {r['sid']:<6} "
            f"{r['orbit']:<10} {r['where']:<22} {ov:>6} {size:>9}  {r['state']}")

    add("")
    plan, until = plan_rows_for_once(args)
    add(f"■ 촬영 예정 {args.plan_days}일 (ESA 계획) — {len(plan)}건"
        + (f" · 계획은 {acquisition_plan.kst_str(until)} KST 까지" if until else ""))
    if not plan and args.plan_hours > 0:
        add("  (그 기간에 한반도 통과 없음 — 계획이 덮는 끝을 위에서 확인할 것)")
    for p in plan[:args.plan_rows]:
        dams = f"  댐·보 {len(p['dams'])}곳" if p["dams"] else ""
        add(f"  {acquisition_plan.kst_str(p['begin'])} KST  {p['sat']} "
            f"rel{p['rel']:>3} {p.get('dir', '')}  "
            f"{p['where'] or '-':<22} 한반도 {p['cover_pct']:>5.1f}%{dams}")

    add("")
    add(f"■ 전처리({rel(args.out_dir)}) — 대기 {len(pending)} · 처리중 {len(busy)}"
        f" · 완료 {len(st.outs)}"
        + (f" · 중단? {len(stalled)}" if stalled else "")
        + (f"   [gpt {st.gpt_procs}개 실행 중]" if st.gpt_procs > 0 else ""))
    for key in sorted(st.busy, key=lambda k: st.busy[k][1]):
        name, started, stale = st.busy[key]
        out_tif = args.out_dir / (Path(name).stem + args.out_suffix + ".tif")
        written = gb(out_tif.stat().st_size) if out_tif.exists() else "-"
        add(f"  {'중단?' if stale else '처리중'}  {short_id(name)}  "
            f"{ago(started)} 시작 · {written} 기록")
    for key in sorted(pending, key=lambda k: k[0], reverse=True)[:args.proc_rows]:
        add(f"  대기    {short_id(st.zips[key][0].name)}")
    done = sorted(st.outs.items(), key=lambda kv: -kv[1][1])[:args.proc_rows]
    for key, (path, mtime, size) in done:
        add(f"  완료    {short_id(path.name)}  {gb(size)}  ({ago(mtime)})")
    return "\n".join(out)


# --- Tk 창 -------------------------------------------------------------------

class Dashboard:
    """작은 상시 창. 무거운 일(STAC·파일 스캔)은 전부 작업 스레드에서 하고
    결과만 큐로 넘겨 그린다 — tkinter 객체를 다른 스레드에서 만지면 죽는다."""

    def __init__(self, args) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.args = args
        self.q: queue.Queue = queue.Queue()
        self.rows: list[dict] = []
        self.local = LocalState()
        self.fetched = "-"
        self.next_cdse = 0.0
        self.busy_cdse = False
        self.names: dict = {}          # (표, 줄) -> 씬 파일명 (더블클릭 복사용)
        self.headings: dict = {}       # 표 -> {열: 머리글 원문} (▲▼ 표시용)
        self.sort: dict = {}           # 표 -> (열, 내림차순) — 없으면 기본 순서
        self.plan: list[dict] = []     # 촬영 예정(ESA 계획 KML)
        self.plan_fetched = "-"
        self.plan_until = ""           # 계획이 덮는 끝(UTC ISO)
        self.next_plan = 0.0

        cache = load_cache()
        if cache.get("rows"):
            self.rows = cache["rows"]
            self.fetched = cache.get("fetched", "-") + " (캐시)"
        plan_cache = acquisition_plan.load_cache()
        if plan_cache.get("rows") is not None:
            self.plan = plan_cache["rows"]
            self.plan_until = plan_cache.get("until", "")
            self.plan_fetched = plan_cache.get("fetched", "-") + " (캐시)"

        self.root = tk.Tk()
        self.root.title("S1 한반도 현황")
        self.root.geometry(args.geometry)
        self.root.minsize(430, 320)
        self.root.attributes("-topmost", args.topmost)

        font = (args.font, args.font_size)
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Treeview", font=font, rowheight=args.font_size * 2 + 2)
        style.configure("Treeview.Heading", font=(args.font, args.font_size))
        style.configure("TLabel", font=font)
        style.configure("TButton", font=font)
        style.configure("TCheckbutton", font=font)
        style.configure("TLabelframe.Label", font=(args.font, args.font_size, "bold"))

        top = ttk.Frame(self.root, padding=(6, 4, 6, 0))
        top.pack(fill="x")
        self.status = ttk.Label(top, text="시작 중…")
        self.status.pack(side="left")
        self.btn_refresh = ttk.Button(top, text="새로고침", width=8,
                                      command=self.refresh_now)
        self.btn_refresh.pack(side="right")
        self.var_top = tk.BooleanVar(value=args.topmost)
        ttk.Checkbutton(top, text="항상 위", variable=self.var_top,
                        command=lambda: self.root.attributes(
                            "-topmost", self.var_top.get())).pack(side="right", padx=4)

        self.summary = ttk.Label(self.root, text="", padding=(8, 2))
        self.summary.pack(fill="x")

        # 촬영 하나당 한 줄 — 카탈로그(궤도·위치)와 로컬(크기·상태)을 한 표에서.
        self.tv_scene = self._table(
            "최근 촬영",
            [("time", "촬영(KST)", 84), ("sat", "위성", 46), ("sid", "씬", 50),
             ("orbit", "궤도", 74), ("where", "위치", 116),
             ("ov", "한반도", 50, "e"), ("size", "크기", 60, "e"),
             ("st", "상태", 58)],
            args.scene_rows, grow=False,
            sortable=("time", "sat", "sid", "orbit", "where", "ov", "size", "st"))
        # 앞으로 찍을 것 — 카탈로그가 아니라 ESA 촬영계획 KML 이 출처다.
        self.tv_plan = self._table(
            "촬영 예정 (ESA 계획)",
            [("time", "촬영(KST)", 84), ("sat", "위성", 46), ("orbit", "궤도", 74),
             ("where", "위치", 166), ("cover", "한반도", 50, "e"),
             ("dams", "댐·보", 50, "e")],
            args.plan_rows, grow=False,
            sortable=("time", "sat", "orbit", "where", "cover", "dams"))
        # 위 표와 같은 순서·같은 이름으로 — 두 표를 눈으로 잇는 것은 씬 이름이다.
        # '비고'는 줄마다 담는 값이 달라(경과·크기·완료시각) 정렬 대상이 아니다.
        self.tv_proc = self._table(
            "전처리",
            [("time", "촬영(KST)", 84), ("sat", "위성", 46), ("sid", "씬", 50),
             ("st", "상태", 58), ("info", "비고", 190)],
            args.proc_rows, grow=True,
            sortable=("time", "sat", "sid", "st"))

        for tv in (self.tv_scene, self.tv_plan, self.tv_proc):
            tv.tag_configure("hot", foreground="#c62828")     # 손 볼 것(중단?)
            tv.tag_configure("new", foreground="#b06000")     # 아직 안 받은 것
            tv.tag_configure("run", foreground="#0057b8")     # 진행 중
            tv.tag_configure("done", foreground="#5a5a5a")    # 끝난 것
            tv.tag_configure("none", foreground="#8a8a8a")    # 안내 문구
            tv.tag_configure("plan", foreground="#1f6f3f")    # 앞으로 찍을 것
            # 줄을 두 번 누르면 씬 파일명을 클립보드로. 이름이 길어 칸에는
            # 줄여 적으므로, 배치·삭제 명령에 붙여 넣으려면 이게 필요하다.
            tv.bind("<Double-1>", self.copy_scene)

        self.root.after(100, self.tick)
        threading.Thread(target=self.worker, daemon=True).start()

    def _table(self, title, cols, rows, grow: bool = True, sortable=()):
        """제목 붙은 표 하나. 화면에 보이는 줄보다 많이 넣으므로 스크롤바를 단다.

        `grow=False`면 창을 키워도 지정한 줄 수 높이를 유지한다. 남는 높이는
        전처리 표가 가져간다 — 대기 목록이 길어 더 보여 줄수록 쓸모가 있다.

        `sortable`에 든 열은 머리글을 누르면 정렬된다(아래 `click_sort`).
        """
        frame = self.ttk.LabelFrame(self.root, text=title, padding=(4, 2))
        frame.pack(fill="both", expand=grow, padx=6, pady=3)
        tv = self.ttk.Treeview(frame, columns=[c[0] for c in cols],
                               show="headings", height=rows, selectmode="browse")
        bar = self.ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=bar.set)
        labels = {}
        for col in cols:
            key, label, width = col[0], col[1], col[2]
            anchor = col[3] if len(col) > 3 else "w"       # 숫자 칸은 오른쪽 정렬
            labels[key] = label
            if key in sortable:
                tv.heading(key, text=label, anchor=anchor,
                           command=lambda t=tv, k=key: self.click_sort(t, k))
            else:
                tv.heading(key, text=label, anchor=anchor)
            tv.column(key, width=width, anchor=anchor,
                      stretch=(key in ("where", "scene", "info")))
        tv.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.headings[str(tv)] = labels
        return tv

    # --- 정렬 ----------------------------------------------------------------

    def click_sort(self, tv, key: str) -> None:
        """머리글 클릭 — 같은 열을 계속 누르면 **오름차순 → 내림차순 → 기본**.

        기본으로 돌아가는 자리를 남겨 둔 이유: 이 화면의 기본 순서(최신 촬영이
        위, 전처리는 처리중→대기→완료)가 평소에 보는 순서다. 정렬을 한 번 걸면
        갱신할 때마다 유지되므로, 되돌릴 방법이 없으면 "최신이 위"라는 전제가
        조용히 깨진 채로 남는다.
        """
        cur = self.sort.get(str(tv))
        first_desc = key in ("time", "ov", "size")     # 시각·수치는 큰 값부터
        if cur is None or cur[0] != key:
            self.sort[str(tv)] = (key, first_desc)
        elif cur[1] == first_desc:
            self.sort[str(tv)] = (key, not first_desc)
        else:
            self.sort.pop(str(tv), None)               # 세 번째 클릭 = 기본
        self.draw()

    def _sorted(self, tv, rows: list[dict], keyfuncs: dict) -> list[dict]:
        """정렬 상태를 적용하고 머리글에 ▲▼ 표시를 붙인다."""
        state = self.sort.get(str(tv))
        for key, label in self.headings[str(tv)].items():
            mark = ""
            if state and state[0] == key:
                mark = " ▼" if state[1] else " ▲"
            tv.heading(key, text=label + mark)
        if not state or state[0] not in keyfuncs:
            return rows
        return sorted(rows, key=keyfuncs[state[0]], reverse=state[1])

    def copy_scene(self, event) -> None:
        """더블클릭한 줄의 씬 파일명을 클립보드에 넣는다."""
        tv = event.widget
        item = tv.identify_row(event.y)
        name = self.names.get((str(tv), item))
        if not name:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(name)
        self.status.config(text=f"복사됨: {name}")

    # --- 작업 스레드 ---------------------------------------------------------

    def worker(self) -> None:
        """로컬 스캔은 자주, STAC는 --cdse-minutes 간격으로. 예외로 죽지 않는다."""
        while True:
            try:
                st = scan_local(self.args.out_dir, self.args.out_suffix,
                                self.args.stale_minutes)
                self.q.put(("local", st))
            except Exception as e:                           # noqa: BLE001
                self.q.put(("error", f"로컬 스캔 실패: {e}"))

            # 촬영 계획 — ESA 가 하루 몇 번 갱신하므로 자주 볼 이유가 없다.
            if self.args.plan_hours > 0 and time.time() >= self.next_plan:
                self.next_plan = time.time() + self.args.plan_hours * 3600
                try:
                    result = acquisition_plan.korea_passes(days=self.args.plan_days)
                    stamp = datetime.now(KST).strftime("%m-%d %H:%M")
                    acquisition_plan.save_cache(result, stamp)
                    self.q.put(("plan", (result.rows, stamp, result.until)))
                except Exception as e:                       # noqa: BLE001
                    self.q.put(("error", f"촬영계획 조회 실패: {e}"))
                    self.next_plan = time.time() + 600

            if time.time() >= self.next_cdse:
                self.next_cdse = time.time() + self.args.cdse_minutes * 60
                self.q.put(("busy", True))
                try:
                    rows = fetch_cdse(self.args.days, self.args.collection,
                                      self.args.min_overlap, self.args.step)
                    stamp = datetime.now(KST).strftime("%m-%d %H:%M")
                    save_cache(rows, stamp)
                    self.q.put(("cdse", (rows, stamp)))
                except Exception as e:                       # noqa: BLE001
                    self.q.put(("error", f"CDSE 조회 실패: {e}"))
                    self.next_cdse = time.time() + 120        # 곧 다시 시도
                self.q.put(("busy", False))

            time.sleep(self.args.local_seconds)

    def refresh_now(self) -> None:
        self.next_cdse = 0.0
        self.next_plan = 0.0

    # --- 그리기 --------------------------------------------------------------

    def tick(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "local":
                    self.local = payload
                elif kind == "cdse":
                    self.rows, self.fetched = payload
                elif kind == "plan":
                    self.plan, self.plan_fetched, self.plan_until = payload
                elif kind == "busy":
                    self.busy_cdse = payload
                elif kind == "error":
                    self.status.config(text=payload)
                self.draw()
        except queue.Empty:
            pass
        self.root.after(1000, self.tick)

    TAGS = {"미수신": "new", "받는중": "run", "전처리중": "run",
            "완료": "done", "중단?": "hot"}

    def draw(self) -> None:
        st = self.local
        merged = merge_rows(self.rows, st, self.args.days)
        busy = [k for k in st.busy if not st.busy[k][2]]
        stalled = [k for k in st.busy if st.busy[k][2]]
        pending = [k for k in st.zips if k not in st.outs and k not in st.busy]
        n_new = sum(1 for r in merged if r["state"] == "미수신")
        self.names.clear()

        scanned = (datetime.fromtimestamp(st.scanned, KST).strftime("%H:%M:%S")
                   if st.scanned else "-")
        self.status.config(
            text=(f"CDSE {self.fetched}" + ("  조회 중…" if self.busy_cdse else "")
                  + f"   ·   계획 {self.plan_fetched}"
                  + f"   ·   폴더 스캔 {scanned}"))
        self.btn_refresh.state(["disabled"] if self.busy_cdse else ["!disabled"])
        # 작업표시줄에 창을 최소화해 둬도 요점은 보이게 한다.
        self.root.title(f"S1 현황 · 처리중 {len(busy)} · 대기 {len(pending)}"
                        + (f" · 미수신 {n_new}" if n_new else ""))
        self.summary.config(
            text=(f"최근 {self.args.days}일 {len(merged)}개 · 미수신 {n_new}"
                  + (f" · 받는중 {len(st.parts)}" if st.parts else "")
                  + f"    |    보유 {len(st.zips)}"
                  + f"    |    대기 {len(pending)} · 처리중 {len(busy)}"
                  + (f" · 중단? {len(stalled)}" if stalled else "")
                  + f" · 완료 {len(st.outs)}"))

        # 최근 촬영 — 카탈로그와 로컬을 한 줄로 -------------------------------
        scene_rows = [{
            "tag": self.TAGS.get(r["state"], ""), "name": r["name"], "raw": r,
            "values": (kst_hm(r["when"]), r["sat"], r["sid"], r["orbit"], r["where"],
                       f"{r['overlap']:.0f}%" if r["overlap"] is not None else "-",
                       gb(r["size"]) if r["size"] else "-", r["state"]),
        } for r in merged[:self.args.scene_rows * 4]]

        self.tv_scene.delete(*self.tv_scene.get_children())
        if not scene_rows:
            self._insert(self.tv_scene, "none", "",
                         ("", "", "", f"최근 {self.args.days}일 한반도 촬영 없음",
                          "", "", ""))
        for row in self._sorted(self.tv_scene, scene_rows, SCENE_SORT):
            self._insert(self.tv_scene, row["tag"], row["name"], row["values"])

        # 촬영 예정 ------------------------------------------------------------
        plan_rows = [{
            "tag": "plan", "name": "", "raw": p,
            "values": (acquisition_plan.kst_str(p["begin"]), p["sat"],
                       f"rel{p['rel']} {p.get('dir', '')}".strip(),
                       p["where"] or "-", f"{p['cover_pct']:.0f}%",
                       str(len(p["dams"])) if p["dams"] else "-"),
        } for p in self.plan]

        self.tv_plan.delete(*self.tv_plan.get_children())
        if not plan_rows:
            # 계획이 어디까지 덮는지 같이 적는다 — 그게 없으면 "통과 없음"과
            # "계획이 아직 안 나옴"이 똑같아 보인다.
            until = (f"계획은 {acquisition_plan.kst_str(self.plan_until)} KST 까지"
                     if self.plan_until else "계획을 아직 못 받았다")
            self._insert(self.tv_plan, "none", "",
                         ("", "", "", f"예정 없음 — {until}", "", ""))
        for row in self._sorted(self.tv_plan, plan_rows, PLAN_SORT):
            self._insert(self.tv_plan, row["tag"], row["name"], row["values"])

        # 전처리 ---------------------------------------------------------------
        proc_rows = []
        for key in sorted(st.busy, key=lambda k: st.busy[k][1]):
            name, started, stale = st.busy[key]
            out_tif = self.args.out_dir / (Path(name).stem + self.args.out_suffix + ".tif")
            written = gb(out_tif.stat().st_size) if out_tif.exists() else "-"
            proc_rows.append(self._proc_row(
                "중단?" if stale else "처리중", name, "hot" if stale else "run",
                f"{ago(started)} 시작 · {written} 기록"))
        for key in sorted(pending, reverse=True)[:self.args.proc_rows]:
            path, mtime, size = st.zips[key]
            proc_rows.append(self._proc_row("대기", path.name, "", gb(size)))
        for key, (path, mtime, size) in sorted(
                st.outs.items(), key=lambda kv: -kv[1][1])[:self.args.proc_rows]:
            proc_rows.append(self._proc_row(
                "완료", path.name, "done", f"{gb(size)} · {ago(mtime)}"))

        self.tv_proc.delete(*self.tv_proc.get_children())
        if not st.busy:
            self._insert(self.tv_proc, "none", "", ("", "", "", "지금 굽는 씬 없음"))
        for row in self._sorted(self.tv_proc, proc_rows, PROC_SORT):
            self._insert(self.tv_proc, row["tag"], row["name"], row["values"])

    @staticmethod
    def _proc_row(state: str, name: str, tag: str, info: str) -> dict:
        key = scene_key(name)
        return {"tag": tag, "name": name, "state": state,
                "sat": sat_label(name), "sid": sid_label(name),
                "obs": key[0] if key else "",
                "values": (kst_of(name), sat_label(name), sid_label(name),
                           state, info)}

    def _insert(self, tv, tag: str, name: str, values) -> None:
        """줄 하나 추가 + 더블클릭 복사용으로 씬 파일명을 기억해 둔다."""
        item = tv.insert("", "end", tags=(tag,), values=values)
        if name:
            self.names[(str(tv), item)] = name

    def run(self) -> None:
        self.root.mainloop()


# --- 진입점 ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="한반도 Sentinel-1 파이프라인 현황 창")
    ap.add_argument("--once", action="store_true",
                    help="창을 띄우지 않고 콘솔에 한 번만 출력(tkinter 불필요)")
    ap.add_argument("--days", type=int, default=7,
                    help="CDSE 조회 일수. 기본 7 — 한반도를 찍는 궤도가 며칠에 "
                         "한 번이라 4일로는 표가 통째로 비는 날이 흔하다")
    ap.add_argument("--collection", default="sentinel-1-grd",
                    help="sentinel-1-grd 또는 sentinel-1-slc")
    ap.add_argument("--min-overlap", type=float, default=1.0,
                    help="한반도 겹침 하한(%%). 미만은 중국·일본 프레임으로 보고 제외")
    ap.add_argument("--step", type=float, default=0.05,
                    help="footprint 표본 격자 간격(도). 작을수록 정밀·느림")
    ap.add_argument("--out-dir", type=Path, default=RTC_FROST_VH_DIR,
                    help="전처리 산출물 폴더. 기본은 현행 정본(VH·Frost·external DEM)")
    ap.add_argument("--out-suffix", default="_rtc_db_vh",
                    help="산출물 파일 접미사. 기본 _rtc_db_vh")
    ap.add_argument("--stale-minutes", type=int, default=30,
                    help="gpt가 없는데 이 시간을 넘긴 임시폴더는 '중단?'으로 표시")
    ap.add_argument("--local-seconds", type=int, default=20,
                    help="로컬 파일 스캔 주기(초). 기본 20")
    ap.add_argument("--cdse-minutes", type=int, default=15,
                    help="CDSE(STAC) 조회 주기(분). 기본 15")
    ap.add_argument("--plan-days", type=int, default=10,
                    help="촬영 계획을 며칠 앞까지 볼지. 기본 10")
    ap.add_argument("--plan-hours", type=float, default=6.0,
                    help="촬영 계획 재조회 주기(시간). 0이면 계획 표를 끈다")
    ap.add_argument("--scene-rows", type=int, default=8,
                    help="'최근 촬영' 표에 보이는 줄 수(더 있으면 스크롤)")
    ap.add_argument("--plan-rows", type=int, default=4,
                    help="'촬영 예정' 표에 보이는 줄 수")
    ap.add_argument("--proc-rows", type=int, default=8,
                    help="'전처리' 표에 보이는 줄 수")
    ap.add_argument("--geometry", default="640x760", help="창 크기·위치(예: 640x760+40+40)")
    ap.add_argument("--font", default="Malgun Gothic")
    ap.add_argument("--font-size", type=int, default=9)
    ap.add_argument("--no-topmost", dest="topmost", action="store_false",
                    help="다른 창 위에 고정하지 않는다")
    return ap


def main() -> int:
    args = build_parser().parse_args()
    args.out_dir = Path(args.out_dir)

    if args.once:
        try:
            sys.stdout.reconfigure(encoding="utf-8")         # 콘솔 한글 깨짐 방지
        except Exception:                                    # noqa: BLE001
            pass
        st = scan_local(args.out_dir, args.out_suffix, args.stale_minutes)
        try:
            rows = fetch_cdse(args.days, args.collection, args.min_overlap, args.step)
            stamp = datetime.now(KST).strftime("%m-%d %H:%M")
            save_cache(rows, stamp)
        except Exception as e:                               # noqa: BLE001
            cache = load_cache()
            rows = cache.get("rows", [])
            stamp = f"{cache.get('fetched', '-')} (캐시 — 조회 실패: {e})"
        print(render_text(rows, st, stamp, args))
        return 0

    Dashboard(args).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
