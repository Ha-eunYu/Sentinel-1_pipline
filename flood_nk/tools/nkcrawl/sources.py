# -*- coding: utf-8 -*-
"""출처 레퍼런스 레지스트리 + 공통 User-Agent.

`CRAWL_GUIDE_KR.md` 2장과 동기화한다. 새 매체를 추가하려면 여기에 항목만
넣으면 CLI `sources`에 자동 반영된다.

access 값
---------
- ``ok``          : WebFetch/urllib로 본문 접근 가능
- ``web`` / ``web-dynamic`` : 웹 UI만(동적 렌더링), 스크립트 자동수집 제한
- ``BLOCKED`` / ``403`` : 접근 차단 → 재전재본·검색 스니펫으로 우회
"""
from __future__ import annotations

#: 검증된 출처 레퍼런스. 값 스키마: name/use/access[/article/list/url/note]
SOURCES: dict[str, dict] = {
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

#: 접근 상태 → 표시 아이콘 (CLI/문서 공용)
ACCESS_ICON = {"ok": "✅", "web": "🌐", "web-dynamic": "🌐",
               "BLOCKED": "⛔", "403": "⛔"}

#: 일반 브라우저 User-Agent(차단 회피용)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
