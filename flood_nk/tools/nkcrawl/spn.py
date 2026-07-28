# -*- coding: utf-8 -*-
"""SPN 「오늘의 북한 날씨」 파서·수집기.

SPN(서울평양뉴스)은 기상청 발표를 매일 정형 기사로 싣는 유일한 소스라 자동화
대상으로 삼았다. 다른 매체(조선중앙TV 인용 등)는 구조가 제각각이라 수동 권장.

공개 API
--------
- :class:`SpnWeather`            : 파싱 결과 데이터클래스
- :func:`fetch_spn`              : idxno 1건 → SpnWeather
- :func:`spn_latest`             : idxno 몰라도 최신 날씨 N건 자동 탐색
- :func:`collect_spn_weather`    : idxno 구간에서 날씨 기사만 수집
- :func:`parse_spn_weather`      : HTML 문자열 → SpnWeather (테스트/오프라인용)

주의: 사이트 HTML/메타 구조 변경 시 아래 ``_RE_*`` 정규식 조정 필요.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .http import http_get
from .sources import SOURCES

# --- 파서 정규식 (사이트 구조 변경 시 여기만 손보면 됨) ------------------- #
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
_RE_IDXNO = re.compile(r'idxno=(\d+)')


@dataclass
class SpnWeather:
    """SPN 날씨 기사 1건의 구조화 결과."""

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
        """마크다운 표 1행으로 직렬화(문서에 바로 붙여넣기용)."""
        rain = "; ".join(self.rainfall) if self.rainfall else self.summary[:60]
        temp = f"평양 {self.pyongyang_temp}℃, 삼지연 {self.samjiyon_temp}℃" \
            if self.pyongyang_temp or self.samjiyon_temp else "-"
        return f"| {self.date} | {self.title} | {rain} | {temp} |"


def _og(html: str) -> dict:
    out: dict[str, str] = {}
    for rx in (_RE_META, _RE_META_ALT):
        for m in rx.finditer(html):
            out.setdefault(m.group("key").lower(), m.group("val").strip())
    return out


def spn_url(idxno) -> str:
    return SOURCES["spn"]["article"].format(idxno=idxno)


def parse_spn_weather(html: str, idxno, url: str) -> SpnWeather:
    """SPN 기사 HTML을 :class:`SpnWeather`로 파싱(네트워크 없이 테스트 가능)."""
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
    """idxno 1건을 네트워크로 가져와 파싱."""
    url = spn_url(idxno)
    return parse_spn_weather(http_get(url, timeout=timeout), idxno, url)


def spn_site_max_idxno(timeout: int = 20):
    """SPN 목록 페이지에서 현재 최신(최대) idxno를 얻는다.

    SPN 검색 목록은 날씨 기사를 신뢰성 있게 필터하지 못하지만(전 분야 최신이
    섞임), 최대 idxno는 안정적으로 제공한다. 이를 스캔 시작점으로 쓴다.
    """
    html = http_get(SOURCES["spn"]["list"], timeout=timeout)
    ids = [int(x) for x in _RE_IDXNO.findall(html)]
    return max(ids) if ids else None


def is_weather(w: SpnWeather) -> bool:
    """제목에 '날씨'가 있으면 「오늘의 북한 날씨」 기사로 판정."""
    return "날씨" in (w.title or "")


def collect_spn_weather(idxnos, limit: int | None = None,
                        timeout: int = 20) -> list:
    """주어진 idxno 순서대로 fetch해 '오늘의 북한 날씨' 기사만 수집."""
    out = []
    for idx in idxnos:
        try:
            w = fetch_spn(idx, timeout=timeout)
        except Exception:  # noqa: BLE001  (404 등은 건너뜀)
            continue
        if is_weather(w):
            out.append(w)
            if limit and len(out) >= limit:
                break
    return out


def spn_latest(limit: int = 3, timeout: int = 20, max_scan: int = 120) -> list:
    """사이트 최신 idxno에서 아래로 스캔해 최근 날씨 기사 ``limit``건을 반환.

    idxno를 몰라도 자동으로 최신 날씨 기사를 찾는다. 날씨 기사는 하루 1건,
    idxno 간격이 크므로(수십) 최대 ``max_scan``건까지만 조회한다.
    """
    top = spn_site_max_idxno(timeout)
    if not top:
        return []
    return collect_spn_weather(range(top, top - max_scan, -1),
                               limit=limit, timeout=timeout)
