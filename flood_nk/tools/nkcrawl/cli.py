# -*- coding: utf-8 -*-
"""명령줄 인터페이스.

서브커맨드: ``sources`` / ``verify`` / ``spn`` / ``latest`` / ``scan``.
``python -m nkcrawl <cmd>`` 또는 얇은 래퍼 ``nk_crawl.py``로 실행.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .http import check_image
from .sources import ACCESS_ICON, SOURCES
from .spn import collect_spn_weather, fetch_spn, spn_latest


# --------------------------------------------------------------------------- #
# 출력 헬퍼
# --------------------------------------------------------------------------- #
def _emit(results, a) -> None:
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


# --------------------------------------------------------------------------- #
# 서브커맨드 핸들러
# --------------------------------------------------------------------------- #
def _cmd_sources(_a) -> int:
    for key, s in SOURCES.items():
        flag = ACCESS_ICON.get(s.get("access"), "·")
        print(f"{flag} {key:12} {s['name']:22} — {s.get('use', '')}")
        if s.get("note"):
            print(f"     ↳ {s['note']}")
    return 0


def _cmd_verify(a) -> int:
    rows = [check_image(u, a.timeout) for u in a.urls]
    for r in rows:
        mark = "OK " if r["ok"] else "FAIL"
        print(f"[{mark}] {r['status']} {r['content_type']} "
              f"{r['bytes']}b  {r['url']}")
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(r["ok"] for r in rows) else 1


def _cmd_spn(a) -> int:
    results = []
    for idxno in a.idxno:
        try:
            results.append(fetch_spn(idxno, timeout=a.timeout))
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] idxno={idxno}: {e}", file=sys.stderr)
    _emit(results, a)
    return 0


def _cmd_latest(a) -> int:
    print(f"[..] 사이트 최신 idxno에서 아래로 최대 {a.max_scan}건 스캔 중"
          f"(날씨 {a.n}건 목표)…", file=sys.stderr)
    results = spn_latest(a.n, timeout=a.timeout, max_scan=a.max_scan)
    if not results:
        print(f"최근 {a.max_scan} idxno에서 날씨 기사를 못 찾음. "
              f"--max-scan을 늘리거나 scan 명령을 쓰세요.", file=sys.stderr)
        return 1
    _emit(results, a)
    return 0


def _cmd_scan(a) -> int:
    lo, hi = sorted((a.from_, a.to))
    print(f"[..] idxno {lo}~{hi} 스캔 중(날씨 기사만 수집)…", file=sys.stderr)
    results = collect_spn_weather(range(hi, lo - 1, -1), timeout=a.timeout)
    if not results:
        print("해당 구간에 날씨 기사 없음.", file=sys.stderr)
        return 1
    _emit(results, a)
    return 0


# --------------------------------------------------------------------------- #
# 파서
# --------------------------------------------------------------------------- #
def _add_emit_opts(p) -> None:
    p.add_argument("--md", action="store_true", help="마크다운 표로 출력")
    p.add_argument("--json", action="store_true", help="JSON으로 출력")
    p.add_argument("--check-images", action="store_true", help="이미지도 검증")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nkcrawl", description="북한 홍수·기상 크롤링 재사용 툴킷")
    p.add_argument("--timeout", type=int, default=20, help="HTTP 타임아웃(초)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sources", help="검증된 출처 레퍼런스 출력").set_defaults(
        func=_cmd_sources)

    v = sub.add_parser("verify", help="이미지 URL 접근성 검증(HTTP 200)")
    v.add_argument("urls", nargs="+")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=_cmd_verify)

    s = sub.add_parser("spn", help="SPN 오늘의 북한 날씨 idxno 파싱")
    s.add_argument("idxno", nargs="+")
    _add_emit_opts(s)
    s.set_defaults(func=_cmd_spn)

    l = sub.add_parser(
        "latest", help="idxno 몰라도 최신 날씨 기사 자동 탐색(사이트 최신→아래 스캔)")
    l.add_argument("-n", type=int, default=3, help="가져올 날씨 기사 수(기본 3)")
    l.add_argument("--max-scan", type=int, default=120,
                   help="최대 조회 idxno 수(기본 120)")
    _add_emit_opts(l)
    l.set_defaults(func=_cmd_latest)

    sc = sub.add_parser("scan", help="idxno 구간을 스캔해 날씨 기사만 수집(빠르고 확실)")
    sc.add_argument("--from", dest="from_", type=int, required=True,
                    help="시작 idxno(예: 마지막 수집분+1)")
    sc.add_argument("--to", type=int, required=True, help="끝 idxno")
    _add_emit_opts(sc)
    sc.set_defaults(func=_cmd_scan)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0
