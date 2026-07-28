#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nk_crawl.py — 북한 홍수·기상 크롤링 재사용 툴킷 (stdlib only)
================================================================

`flood_nk/CRAWL_GUIDE_KR.md`의 절차를 코드로 모듈화한 것. 표준 라이브러리만
사용하므로 별도 설치 없이 conda/venv 어디서나 실행된다.

주요 기능
---------
1. SPN 「오늘의 북한 날씨」 기사(idxno) 파싱 → 날짜/강수 요약/기온/이미지 URL.
2. 이미지 URL 접근성 검증(HTTP 200 + content-type/size) — 임베드 전 필수 절차.
3. 결과를 마크다운 표 행 / JSON으로 출력.
4. 검증된 출처 레퍼런스(SOURCES) 조회.

사용 예 (Windows conda python)
------------------------------
  python nk_crawl.py sources
  python nk_crawl.py spn 109256
  python nk_crawl.py spn 109252 109256 --md            # 여러 개 → 마크다운 표
  python nk_crawl.py verify https://cdn.spnews.co.kr/....png  https://...jpg
  python nk_crawl.py spn 109256 --check-images         # 파싱 + 이미지 검증

주의: 웹 구조 변경 시 파서 정규식(_RE_*) 조정 필요. yna.co.kr(연합)·
voakorea(403)·ChatGPT 공유링크는 접근 불가(가이드 7장 참조).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field, asdict

# --------------------------------------------------------------------------- #
# 0. 검증된 출처 레퍼런스 (CRAWL_GUIDE_KR.md 2장과 동기화)
# --------------------------------------------------------------------------- #
SOURCES = {
    "spn": {
        "name": "SPN 서울평양뉴스",
        "use": "일자별 북한 날씨 + 기상 개황도",
        "access": "ok",
        "article": "https://www.spnews.co.kr/news/articleView.html?idxno={idxno}",
        "list": ("https://www.spnews.co.kr/news/articleList.html"
                 "?sc_area=A&view_type=sm&sc_word=%EC%98%A4%EB%8A%98%EC%9D%98"
                 "+%EB%B6%81%ED%95%9C+%EB%82%A0%EC%94%A8"),
        "note": "idxno가 날짜순 증가",
    },
    "tongilnews": {
        "name": "통일뉴스", "use": "조선중앙방송/기상수문국 경보 인용", "access": "ok",
        "article": "http://www.tongilnews.com/news/articleView.html?idxno={idxno}",
    },
    "newspim": {
        "name": "뉴스핌", "use": "조선중앙TV 갈무리 카드뉴스", "access": "ok",
        "article": "https://www.newspim.com/news/view/{idxno}",
    },
    "segye": {
        "name": "세계일보 [북마크]", "use": "조선중앙TV 보도장면 갈무리", "access": "ok",
        "article": "https://segye.com/newsView/{idxno}",
    },
    "seoul": {
        "name": "서울신문", "use": "군남댐 방류 실사(연합 전재)", "access": "ok",
    },
    "mbc": {"name": "MBC", "use": "황강댐 방류", "access": "ok"},
    "dailian": {"name": "데일리안", "use": "필승교/군남댐 수위(⚠️자료사진 주의)", "access": "ok"},
    "kma_nk": {
        "name": "기상청 날씨누리 북한예보", "use": "도별 관측·권역 예보(27지점)",
        "access": "web", "url": "https://www.weather.go.kr/w/forecast/life/nk/land.do",
    },
    "kma_portal": {
        "name": "기상청 기상자료개방포털", "use": "북한 정량 강수(03·15시 6h, 09·21시 12h 누적)",
        "access": "web-dynamic", "url": "https://data.kma.go.kr",
    },
    "yna": {"name": "연합뉴스", "use": "댐/수위", "access": "BLOCKED",
            "note": "WebFetch/urllib 차단 → 재전재본(서울신문 등)으로 대체"},
    "voa": {"name": "VOA 한국어", "use": "실측 강수·피해", "access": "403",
            "note": "본문 접근 불가 → 검색 스니펫만"},
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_RE_META = re.compile(
    r'<meta[^>]+property=["\']og:(?P<key>title|image|description)["\'][^>]*'
    r'content=["\'](?P<val>.*?)["\']', re.I | re.S)
_RE_META_ALT = re.compile(  # content 앞, property 뒤 순서 변형 대비
    r'<meta[^>]+content=["\'](?P<val>.*?)["\'][^>]*'
    r'property=["\']og:(?P<key>title|image|description)["\']', re.I | re.S)
# 두 자리 우선(alternation): "2026-07-26"의 일이 "2"로 잘리지 않도록
_RE_DATE = re.compile(r'20\d\d[.\-](?:1[0-2]|0[1-9])[.\-](?:3[01]|[12]\d|0[1-9])')
_RE_SPN_IMG = re.compile(r'https?://cdn\.spnews\.co\.kr/news/photo/[^\s"\'<>)]+')
_RE_MM = re.compile(r'[^,·\n]{0,25}?\d+\s*[~∼\-]\s*\d+\s*mm[^,·\n]{0,20}')
_RE_TEMP = re.compile(r'(평양|삼지연)[^0-9]{0,6}(\d{1,2})\s*(?:도|℃)')


# --------------------------------------------------------------------------- #
# 1. HTTP 유틸
# --------------------------------------------------------------------------- #
def _decode(raw: bytes, ctype: str) -> str:
    """Content-Type 또는 <meta charset>에서 인코딩 판별. SPN은 EUC-KR."""
    enc = None
    m = re.search(r'charset=([\w\-]+)', ctype or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        m = re.search(rb'charset=["\']?([\w\-]+)', raw[:2048], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for cand in ([enc] if enc else []) + ["utf-8", "cp949", "euc-kr"]:
        try:
            return raw.decode(cand)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _decode(r.read(), r.headers.get("Content-Type", ""))


def check_image(url: str, timeout: int = 20) -> dict:
    """이미지 URL 접근성 검증. {ok, status, content_type, bytes}."""
    def _probe(method):
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read() if method == "GET" else b""
            return (r.status, r.headers.get("Content-Type", ""),
                    int(r.headers.get("Content-Length") or len(data)))
    try:
        try:
            status, ctype, size = _probe("HEAD")
            if status == 200 and size == 0:  # 일부 서버 HEAD에 length 미제공
                status, ctype, size = _probe("GET")
        except Exception:
            status, ctype, size = _probe("GET")
        ok = status == 200 and ctype.lower().startswith("image/")
        return {"url": url, "ok": ok, "status": status,
                "content_type": ctype, "bytes": size}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": False, "status": None,
                "content_type": "", "bytes": 0, "error": repr(e)}


# --------------------------------------------------------------------------- #
# 2. SPN 「오늘의 북한 날씨」 파서
# --------------------------------------------------------------------------- #
@dataclass
class SpnWeather:
    idxno: str
    url: str
    title: str = ""
    date: str = ""
    summary: str = ""
    rainfall: list = field(default_factory=list)
    pyongyang_temp: str = ""
    samjiyon_temp: str = ""
    images: list = field(default_factory=list)

    def md_row(self) -> str:
        rain = "; ".join(self.rainfall) if self.rainfall else self.summary[:60]
        temp = f"평양 {self.pyongyang_temp}℃, 삼지연 {self.samjiyon_temp}℃" \
            if self.pyongyang_temp or self.samjiyon_temp else "-"
        return f"| {self.date} | {self.title} | {rain} | {temp} |"


def _og(html: str) -> dict:
    out = {}
    for rx in (_RE_META, _RE_META_ALT):
        for m in rx.finditer(html):
            out.setdefault(m.group("key").lower(), m.group("val").strip())
    return out


def spn_url(idxno) -> str:
    return SOURCES["spn"]["article"].format(idxno=idxno)


def parse_spn_weather(html: str, idxno, url: str) -> SpnWeather:
    og = _og(html)
    title = re.sub(r'\s*-\s*SPN.*$', '', og.get("title", "")).strip()
    desc = og.get("description", "").strip()
    dates = _RE_DATE.findall(html)
    date = dates[0].replace(".", "-") if dates else ""
    # 강수량 원문: og:description은 사이트 길이제한으로 둘째 지역군이 잘릴 수
    # 있어, 본문(태그 제거)에서 "예상 강수량 … 낮 최고" 문장을 우선 사용.
    text = re.sub(r'<[^>]+>', ' ', html)
    m = re.search(r'예상\s*강수량.{0,160}?(?=낮\s*최고)', text)
    rain_src = m.group(0) if (m and "mm" in m.group(0)) else desc
    # 그룹 구분자 '-'로 분할해 지역명까지 보존, '□'/'낮' 이후는 절단.
    rainfall = []
    for seg in re.split(r'\s*[-–]\s*', rain_src):
        seg = re.split(r'[□▢]|낮\s*최고', seg)[0].strip(" ·:")
        if "mm" in seg:
            rainfall.append(re.sub(r'\s+', ' ', seg))
    if not rainfall:  # 폴백: 느슨한 mm 패턴
        rainfall = [s.strip(" -·") for s in _RE_MM.findall(desc)]
    # 기온: og:description 우선, 없으면 본문 전체에서 탐색
    temps = dict((r, t) for r, t in _RE_TEMP.findall(desc))
    if not temps:
        temps = dict((r, t) for r, t in _RE_TEMP.findall(html))
    images = []
    if og.get("image"):
        images.append(og["image"])
    for u in _RE_SPN_IMG.findall(html):
        if u not in images:
            images.append(u)
    return SpnWeather(
        idxno=str(idxno), url=url, title=title, date=date, summary=desc,
        rainfall=rainfall, pyongyang_temp=temps.get("평양", ""),
        samjiyon_temp=temps.get("삼지연", ""), images=images)


def fetch_spn(idxno, timeout: int = 20) -> SpnWeather:
    url = spn_url(idxno)
    return parse_spn_weather(http_get(url, timeout=timeout), idxno, url)


def spn_site_max_idxno(timeout: int = 20) -> int | None:
    """SPN 목록 페이지에서 현재 최신(최대) idxno를 얻는다.

    SPN 검색 목록은 날씨 기사를 신뢰성 있게 필터하지 못하지만(전 분야 최신이
    섞임), 최대 idxno는 안정적으로 제공한다. 이를 스캔 시작점으로 쓴다.
    """
    html = http_get(SOURCES["spn"]["list"], timeout=timeout)
    ids = [int(x) for x in re.findall(r'idxno=(\d+)', html)]
    return max(ids) if ids else None


def is_weather(w: "SpnWeather") -> bool:
    return "날씨" in (w.title or "")


def collect_spn_weather(idxnos, limit: int | None = None,
                        timeout: int = 20) -> list:
    """주어진 idxno 순서대로 fetch해 '오늘의 북한 날씨' 기사만 수집."""
    out = []
    for idx in idxnos:
        try:
            w = fetch_spn(idx, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        if is_weather(w):
            out.append(w)
            if limit and len(out) >= limit:
                break
    return out


def spn_latest(limit: int = 3, timeout: int = 20, max_scan: int = 120) -> list:
    """사이트 최신 idxno에서 아래로 스캔해 최근 날씨 기사 `limit`건을 반환.

    idxno를 몰라도 자동으로 최신 날씨 기사를 찾는다. 날씨 기사는 하루 1건,
    idxno 간격이 크므로(수십) 최대 `max_scan`건까지만 조회한다.
    """
    top = spn_site_max_idxno(timeout)
    if not top:
        return []
    return collect_spn_weather(range(top, top - max_scan, -1),
                               limit=limit, timeout=timeout)


# --------------------------------------------------------------------------- #
# 3. CLI
# --------------------------------------------------------------------------- #
def _cmd_sources(_):
    for key, s in SOURCES.items():
        flag = {"ok": "✅", "web": "🌐", "web-dynamic": "🌐",
                "BLOCKED": "⛔", "403": "⛔"}.get(s.get("access"), "·")
        print(f"{flag} {key:12} {s['name']:22} — {s.get('use','')}")
        if s.get("note"):
            print(f"     ↳ {s['note']}")


def _cmd_verify(a):
    rows = [check_image(u, a.timeout) for u in a.urls]
    for r in rows:
        mark = "OK " if r["ok"] else "FAIL"
        print(f"[{mark}] {r['status']} {r['content_type']} "
              f"{r['bytes']}b  {r['url']}")
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(r["ok"] for r in rows) else 1


def _emit(results, a):
    """SpnWeather 목록을 옵션(--check-images/--md/--json/기본)대로 출력."""
    if getattr(a, "check_images", False):
        for w in results:
            for r in (check_image(u, a.timeout) for u in w.images):
                print(f"    img [{'OK' if r['ok'] else 'FAIL'}] "
                      f"{r['status']} {r['bytes']}b {r['url']}")
    if getattr(a, "md", False):
        print("| 날짜 | 주요 날씨 | 예상 강수량 요약 | 낮 최고기온 |")
        print("|---|---|---|---|")
        for w in results:
            print(w.md_row())
    elif getattr(a, "json", False):
        print(json.dumps([asdict(w) for w in results],
                         ensure_ascii=False, indent=2))
    else:
        for w in results:
            print(f"# {w.date}  (idxno {w.idxno})")
            print(f"  제목: {w.title}")
            print(f"  강수: {'; '.join(w.rainfall) or '-'}")
            print(f"  기온: 평양 {w.pyongyang_temp}℃ / 삼지연 {w.samjiyon_temp}℃")
            print(f"  이미지: {w.images[0] if w.images else '-'}")
            print(f"  원문: {w.url}")


def _cmd_spn(a):
    results = []
    for idxno in a.idxno:
        try:
            results.append(fetch_spn(idxno, timeout=a.timeout))
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] idxno={idxno}: {e}", file=sys.stderr)
    _emit(results, a)
    return 0


def _cmd_latest(a):
    print(f"[..] 사이트 최신 idxno에서 아래로 최대 {a.max_scan}건 스캔 중"
          f"(날씨 {a.n}건 목표)…", file=sys.stderr)
    results = spn_latest(a.n, timeout=a.timeout, max_scan=a.max_scan)
    if not results:
        print(f"최근 {a.max_scan} idxno에서 날씨 기사를 못 찾음. "
              f"--max-scan을 늘리거나 scan 명령을 쓰세요.", file=sys.stderr)
        return 1
    _emit(results, a)
    return 0


def _cmd_scan(a):
    lo, hi = sorted((a.from_, a.to))
    print(f"[..] idxno {lo}~{hi} 스캔 중(날씨 기사만 수집)…", file=sys.stderr)
    results = collect_spn_weather(range(hi, lo - 1, -1), timeout=a.timeout)
    if not results:
        print("해당 구간에 날씨 기사 없음.", file=sys.stderr)
        return 1
    _emit(results, a)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nk_crawl", description="북한 홍수·기상 크롤링 재사용 툴킷")
    p.add_argument("--timeout", type=int, default=20)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="검증된 출처 레퍼런스 출력").set_defaults(
        func=_cmd_sources)

    v = sub.add_parser("verify", help="이미지 URL 접근성 검증(HTTP 200)")
    v.add_argument("urls", nargs="+")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=_cmd_verify)

    s = sub.add_parser("spn", help="SPN 오늘의 북한 날씨 idxno 파싱")
    s.add_argument("idxno", nargs="+")
    s.add_argument("--md", action="store_true", help="마크다운 표로 출력")
    s.add_argument("--json", action="store_true")
    s.add_argument("--check-images", action="store_true", help="이미지도 검증")
    s.set_defaults(func=_cmd_spn)

    l = sub.add_parser("latest",
                       help="idxno 몰라도 최신 날씨 기사 자동 탐색(사이트 최신→아래 스캔)")
    l.add_argument("-n", type=int, default=3, help="가져올 날씨 기사 수(기본 3)")
    l.add_argument("--max-scan", type=int, default=120,
                   help="최대 조회 idxno 수(기본 120)")
    l.add_argument("--md", action="store_true", help="마크다운 표로 출력")
    l.add_argument("--json", action="store_true")
    l.add_argument("--check-images", action="store_true", help="이미지도 검증")
    l.set_defaults(func=_cmd_latest)

    sc = sub.add_parser("scan",
                        help="idxno 구간을 스캔해 날씨 기사만 수집(빠르고 확실)")
    sc.add_argument("--from", dest="from_", type=int, required=True,
                    help="시작 idxno(예: 마지막 수집분+1)")
    sc.add_argument("--to", type=int, required=True, help="끝 idxno")
    sc.add_argument("--md", action="store_true", help="마크다운 표로 출력")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--check-images", action="store_true", help="이미지도 검증")
    sc.set_defaults(func=_cmd_scan)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
