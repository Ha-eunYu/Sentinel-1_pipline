# -*- coding: utf-8 -*-
"""한반도 Sentinel-1 파이프라인 **현황 창** — 회사 PC에 띄워 두는 작은 대시보드.

한 화면에서 다음을 본다.

1. **CDSE 최신 촬영** — 최근 며칠간 Copernicus 카탈로그에 올라온 한반도 프레임.
   관측시각(KST), 상대궤도·상승/하강, **대략적인 위치(충남·전남 …)**, 한반도
   겹침%, 그리고 **이 PC에서의 처리 단계**.
2. **이 PC의 진행 상황** — 최근 다운로드 / 받는 중(.part) / 전처리 대기 /
   전처리 중 / 전처리 완료.

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

from s1.core.paths import (DOWNLOADS_DIR, GEOJSON_DIR, GRD_DIR,  # noqa: E402
                           KOREA_PENINSULA, RTC_FROST_VH_DIR, rel)
from s1.core.scene import parse_scene                            # noqa: E402
from s1.tools.monitor.monitor_new_scenes import (KOREA_BBOX, Boundary,  # noqa: E402
                                                 load_rings, point_in_ring,
                                                 search_stac)

KST = timezone(timedelta(hours=9))
SIDO_GEOJSON = GEOJSON_DIR / "sido_simplified.geojson"
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


def short_id(name: str) -> str:
    """표시용 짧은 이름: 위성 + 촬영시각(KST) + 씬ID (예: `S1C 08-07 06:39 0868`)."""
    k = parse_scene(name)
    m = START_RE.search(name)
    if not k or not m:
        return name[:28]
    dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return f"{k.platform} {dt.astimezone(KST):%m-%d %H:%M} {k.sid}"


# --- 대략적인 위치(시도) -----------------------------------------------------

class SidoIndex:
    """시도 경계 묶음. monitor_new_scenes.Boundary 와 같은 1°격자 색인 방식이되,
    "안/밖"이 아니라 **어느 시도인지**를 돌려준다.

    경계는 `geojson/sido_simplified.geojson`(build_sido_geojson.py 산출물).
    파일이 없으면 위치 칸만 비고 나머지는 그대로 돈다.
    """

    def __init__(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.rings: list[tuple[str, list[tuple[float, float]]]] = []
        self.index: dict[tuple[int, int], list[int]] = {}
        for feat in data.get("features", []):
            name = feat.get("properties", {}).get("name", "?")
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Polygon":
                polys = [geom["coordinates"]]
            elif geom.get("type") == "MultiPolygon":
                polys = geom["coordinates"]
            else:
                continue
            for poly in polys:
                ring = [(float(p[0]), float(p[1])) for p in poly[0]]
                k = len(self.rings)
                self.rings.append((name, ring))
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                for cx in range(int(min(xs) // 1), int(max(xs) // 1) + 1):
                    for cy in range(int(min(ys) // 1), int(max(ys) // 1) + 1):
                        self.index.setdefault((cx, cy), []).append(k)

    def at(self, x: float, y: float) -> str | None:
        for k in self.index.get((int(x // 1), int(y // 1)), ()):
            name, ring = self.rings[k]
            if point_in_ring(x, y, ring):
                return name
        return None


def describe_footprint(geom: dict, boundary: Boundary | None,
                       sido: SidoIndex | None, step: float = 0.05,
                       min_share: float = 8.0, max_names: int = 3
                       ) -> tuple[float, str]:
    """footprint 하나를 (한반도 겹침%, "충남·전북")으로 요약한다.

    겹침%와 시도 판정을 **같은 표본 격자 한 번**으로 처리한다. 따로 돌리면
    프레임마다 격자를 두 번 뿌리게 되고, 대시보드는 이걸 수십 프레임에
    반복하므로 그 차이가 체감된다.

    시도는 **육지 표본 중 비율**이 min_share% 이상인 것만 큰 순서로 최대
    max_names개. 프레임 대부분이 바다인 경우가 흔해 전체 표본 대비로 세면
    전부 잘려 나간다.
    """
    if not geom:
        return 0.0, ""
    if geom.get("type") == "Polygon":
        polys = [geom["coordinates"]]
    elif geom.get("type") == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return 0.0, ""
    rings = [[(float(p[0]), float(p[1])) for p in poly[0]] for poly in polys]
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]

    n_in = n_hit = 0
    counts: dict[str, int] = {}
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            if any(point_in_ring(x, y, r) for r in rings):
                n_in += 1
                if boundary is not None and boundary.contains(x, y):
                    n_hit += 1
                if sido is not None:
                    name = sido.at(x, y)
                    if name:
                        counts[name] = counts.get(name, 0) + 1
            x += step
        y += step

    pct = 100.0 * n_hit / n_in if n_in else 0.0
    total_land = sum(counts.values())
    names = ""
    if total_land:
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        keep = [n for n, c in ranked if 100.0 * c / total_land >= min_share]
        names = "·".join(keep[:max_names]) or ranked[0][0]
    return pct, names


# --- 로컬 상태 ---------------------------------------------------------------

@dataclass
class LocalState:
    """이 PC의 파일 상태 스냅샷. 키는 전부 (관측 시작시각, 절대궤도)."""

    zips: dict = field(default_factory=dict)        # key -> (Path, mtime, size)
    outs: dict = field(default_factory=dict)        # key -> (Path, mtime, size)
    busy: dict = field(default_factory=dict)        # key -> (파일명, 시작시각, stale)
    parts: list = field(default_factory=list)       # [(Path, mtime, size)]
    gpt_procs: int = 0                              # -1 = 확인 실패
    scanned: float = 0.0

    def state_of(self, key) -> str:
        if key in self.busy:
            return "중단?" if self.busy[key][2] else "전처리중"
        if key in self.outs:
            return "완료"
        if key in self.zips:
            return "대기"
        return "미수신"


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
            s = p.stat()
            st.parts.append((p, s.st_mtime, s.st_size))

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

def render_text(rows: list[dict], st: LocalState, fetched: str, args) -> str:
    out: list[str] = []
    add = out.append

    n_new = sum(1 for r in rows if st.state_of(scene_key(r["id"])) == "미수신")
    busy = [k for k in st.busy if not st.busy[k][2]]
    stalled = [k for k in st.busy if st.busy[k][2]]
    pending = [k for k in st.zips if k not in st.outs and k not in st.busy]

    add(f"■ CDSE 최근 {args.days}일 (조회 {fetched}) — {len(rows)}개, 미수신 {n_new}")
    for r in rows[:args.cdse_rows]:
        key = scene_key(r["id"])
        add(f"  {kst_hm(r['datetime'])} KST  rel{str(r['rel'] or '?'):>3} {r['dir']}"
            f"  {r['where'] or '-':<12} 한반도 {r['overlap']:>5.1f}%  "
            f"{st.state_of(key)}")

    add("")
    add(f"■ 다운로드 — 보유 {len(st.zips)}개"
        + (f", 받는 중 {len(st.parts)}개" if st.parts else ""))
    for p, mtime, size in sorted(st.parts, key=lambda x: -x[1]):
        add(f"  받는중  {short_id(p.name)}  {gb(size)}  ({ago(mtime)} 갱신)")
    recent = sorted(st.zips.items(), key=lambda kv: -kv[1][1])[:args.local_rows]
    for key, (path, mtime, size) in recent:
        add(f"  {ago(mtime):>8}  {short_id(path.name)}  {gb(size)}  {st.state_of(key)}")

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
    for key in sorted(pending, key=lambda k: k[0], reverse=True)[:args.local_rows]:
        add(f"  대기    {short_id(st.zips[key][0].name)}")
    done = sorted(st.outs.items(), key=lambda kv: -kv[1][1])[:args.local_rows]
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

        cache = load_cache()
        if cache.get("rows"):
            self.rows = cache["rows"]
            self.fetched = cache.get("fetched", "-") + " (캐시)"

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
        ttk.Button(top, text="새로고침", width=8,
                   command=self.refresh_now).pack(side="right")
        self.var_top = tk.BooleanVar(value=args.topmost)
        ttk.Checkbutton(top, text="항상 위", variable=self.var_top,
                        command=lambda: self.root.attributes(
                            "-topmost", self.var_top.get())).pack(side="right", padx=4)

        self.summary = ttk.Label(self.root, text="", padding=(8, 2))
        self.summary.pack(fill="x")

        self.tv_cdse = self._table(
            "CDSE 최근 촬영",
            [("time", "촬영(KST)", 92), ("orbit", "궤도", 74),
             ("where", "위치", 116), ("ov", "한반도", 54), ("st", "상태", 62)],
            args.cdse_rows)
        self.tv_down = self._table(
            "이 PC 다운로드",
            [("when", "받은 때", 96), ("scene", "씬", 152),
             ("size", "크기", 66), ("st", "상태", 62)],
            args.local_rows)
        self.tv_proc = self._table(
            "전처리",
            [("st", "상태", 62), ("scene", "씬", 152),
             ("info", "비고", 152)],
            args.local_rows + 4)

        for tv in (self.tv_cdse, self.tv_down, self.tv_proc):
            tv.tag_configure("hot", foreground="#b00020")     # 손 볼 것
            tv.tag_configure("run", foreground="#0057b8")     # 진행 중
            tv.tag_configure("done", foreground="#5a5a5a")    # 끝난 것

        self.root.after(100, self.tick)
        threading.Thread(target=self.worker, daemon=True).start()

    def _table(self, title, cols, rows):
        """제목 붙은 표 하나. 화면에 보이는 줄보다 많이 넣으므로 스크롤바를 단다."""
        frame = self.ttk.LabelFrame(self.root, text=title, padding=(4, 2))
        frame.pack(fill="both", expand=True, padx=6, pady=3)
        tv = self.ttk.Treeview(frame, columns=[c[0] for c in cols],
                               show="headings", height=rows, selectmode="none")
        bar = self.ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=bar.set)
        for key, label, width in cols:
            tv.heading(key, text=label)
            tv.column(key, width=width, anchor="w", stretch=(key in ("where", "scene", "info")))
        tv.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        return tv

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

    # --- 그리기 --------------------------------------------------------------

    def tick(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "local":
                    self.local = payload
                elif kind == "cdse":
                    self.rows, self.fetched = payload
                elif kind == "busy":
                    self.busy_cdse = payload
                elif kind == "error":
                    self.status.config(text=payload)
                self.draw()
        except queue.Empty:
            pass
        self.root.after(1000, self.tick)

    def draw(self) -> None:
        st, rows = self.local, self.rows
        busy = [k for k in st.busy if not st.busy[k][2]]
        stalled = [k for k in st.busy if st.busy[k][2]]
        pending = [k for k in st.zips if k not in st.outs and k not in st.busy]
        n_new = sum(1 for r in rows if st.state_of(scene_key(r["id"])) == "미수신")

        self.status.config(
            text=(f"CDSE {self.fetched}" + ("  조회 중…" if self.busy_cdse else "")
                  + f"   ·   로컬 {datetime.now(KST):%H:%M:%S}"))
        # 작업표시줄에 창을 최소화해 둬도 요점은 보이게 한다.
        self.root.title(f"S1 현황 · 처리중 {len(busy)} · 대기 {len(pending)}"
                        + (f" · 미수신 {n_new}" if n_new else ""))
        self.summary.config(
            text=(f"CDSE {self.args.days}일 {len(rows)}개 · 미수신 {n_new}    |    "
                  f"보유 {len(st.zips)}"
                  + (f" · 받는중 {len(st.parts)}" if st.parts else "")
                  + f"    |    대기 {len(pending)} · 처리중 {len(busy)}"
                  + (f" · 중단? {len(stalled)}" if stalled else "")
                  + f" · 완료 {len(st.outs)}"))

        # CDSE ---------------------------------------------------------------
        self.tv_cdse.delete(*self.tv_cdse.get_children())
        for r in rows[:self.args.cdse_rows * 3]:
            state = st.state_of(scene_key(r["id"]))
            tag = {"미수신": "hot", "전처리중": "run", "받는중": "run",
                   "완료": "done"}.get(state, "")
            self.tv_cdse.insert(
                "", "end", tags=(tag,),
                values=(kst_hm(r["datetime"]),
                        f"rel{r['rel'] or '?'} {r['dir']}",
                        r["where"] or "-", f"{r['overlap']:.0f}%", state))

        # 다운로드 -------------------------------------------------------------
        self.tv_down.delete(*self.tv_down.get_children())
        for p, mtime, size in sorted(st.parts, key=lambda x: -x[1]):
            self.tv_down.insert("", "end", tags=("run",),
                                values=(ago(mtime), short_id(p.name),
                                        gb(size), "받는중"))
        for key, (path, mtime, size) in sorted(
                st.zips.items(), key=lambda kv: -kv[1][1])[:self.args.local_rows * 3]:
            state = st.state_of(key)
            tag = {"전처리중": "run", "완료": "done"}.get(state, "")
            self.tv_down.insert("", "end", tags=(tag,),
                                values=(ago(mtime), short_id(path.name),
                                        gb(size), state))

        # 전처리 ---------------------------------------------------------------
        self.tv_proc.delete(*self.tv_proc.get_children())
        for key in sorted(st.busy, key=lambda k: st.busy[k][1]):
            name, started, stale = st.busy[key]
            out_tif = self.args.out_dir / (Path(name).stem + self.args.out_suffix + ".tif")
            written = gb(out_tif.stat().st_size) if out_tif.exists() else "-"
            self.tv_proc.insert(
                "", "end", tags=("hot" if stale else "run",),
                values=("중단?" if stale else "처리중", short_id(name),
                        f"{ago(started)} 시작 · {written} 기록"))
        for key in sorted(pending, reverse=True)[:self.args.local_rows]:
            path, mtime, size = st.zips[key]
            self.tv_proc.insert("", "end",
                                values=("대기", short_id(path.name), gb(size)))
        for key, (path, mtime, size) in sorted(
                st.outs.items(), key=lambda kv: -kv[1][1])[:self.args.local_rows]:
            self.tv_proc.insert("", "end", tags=("done",),
                                values=("완료", short_id(path.name),
                                        f"{gb(size)} · {ago(mtime)}"))

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
    ap.add_argument("--cdse-rows", type=int, default=6, help="CDSE 표 줄 수")
    ap.add_argument("--local-rows", type=int, default=5, help="로컬 표 줄 수")
    ap.add_argument("--geometry", default="600x760", help="창 크기·위치(예: 600x760+40+40)")
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
