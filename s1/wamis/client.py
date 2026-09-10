# -*- coding: utf-8 -*-
"""WAMIS OpenAPI **HTTP 계층** — 요청·재시도·오류 판정만 한다.

WAMIS(국가수자원관리종합정보시스템)는 **인증키 없이** 열려 있다.

    http://www.wamis.go.kr:8080/wamis/openapi/<그룹>/<기능>?...&output=json

⚠ **HTTPS 가 아니라 8080 포트 평문 HTTP 다.** 방화벽이 8080 아웃바운드를 막으면
여기서 전부 실패한다. 그때는 회선 문제이지 코드 문제가 아니다.

이 서버가 까다로운 지점 세 가지
-------------------------------
1. **오류를 HTTP 상태코드로 알리지 않는다.** 무엇을 물어도 200 이고, 성패는
   본문 ``result.code`` 에만 있다. 그래서 ``urlopen`` 성공 == 자료 획득이 아니다.

   ===================== ============ ==========================================
   result.code            count        뜻
   ===================== ============ ==========================================
   ``success``            n>0          정상
   ``success``            0            **자료 없음** — 오류가 아니다
   ``failure``            None         요청이 틀렸다 — 재시도해도 소용없다
   ===================== ============ ==========================================

2. **없는 댐코드도 ``success``/0 으로 답한다.** 오타가 "그 댐은 자료가 없네요"로
   조용히 둔갑한다. 그래서 코드 검증은 호출 전에 목록으로 해야 한다
   (:func:`s1.wamis.dams.resolve`).

3. **과부하를 RST 로 끊는다.** 범위가 넓거나 연속 호출이 잦으면 HTTP 오류가 아니라
   TCP 연결이 그냥 끊긴다(``ConnectionResetError``). **같은 요청이 다음 시도에서
   성공하는 것을 실측으로 확인**했으므로(2026-09-09, 25일치 시자료 3번째 시도에서
   성공) 이는 영구 실패가 아니라 **일시 스로틀**로 다뤄야 한다.

그래서 이 모듈의 규칙은 하나다 — **끊긴 연결은 재시도하고, ``failure`` 는 즉시
포기한다.** 전자는 서버가 바쁜 것이고 후자는 우리가 틀린 것이다.

의존성 없음(표준 라이브러리만). 자세한 설명은 docs/water/WAMIS_DAM_LEVEL_KR.md.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

BASE = "http://www.wamis.go.kr:8080/wamis/openapi"
UA = {"User-Agent": "Mozilla/5.0 (S1 SAR pipeline; WAMIS dam level collector)"}

# 기본 재시도. 첫 시도 포함 4번, 대기 1.5→3→4.5초.
DEFAULT_TRIES = 4
BACKOFF_SEC = 1.5
DEFAULT_TIMEOUT = 90


class WamisError(RuntimeError):
    """서버가 ``result.code == "failure"`` 로 답했다 — **요청이 틀렸다.**

    재시도 대상이 아니다. 실제로 나오는 경우는 두 가지였다.

    * ``정해진 검색 조건 값이 아닙니다!`` — 날짜가 미래이거나 범위가 규격 밖
    * ``필수 요청 항목이 없습니다!`` — damcd 등 필수 파라미터 누락
    """


class WamisUnavailable(RuntimeError):
    """재시도를 다 쓰고도 응답을 못 받았다 — **서버·회선 쪽 문제.**

    여기까지 왔으면 잠시 뒤 다시 돌리는 것 말고는 할 수 있는 일이 없다.
    """


def ymd(value: str | date | datetime) -> str:
    """``YYYYMMDD`` 문자열로 통일. 잘못된 값은 여기서 걸러 서버까지 안 보낸다."""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    s = str(value).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"날짜는 YYYYMMDD 여야 한다: {value!r}")
    datetime.strptime(s, "%Y%m%d")          # 20260231 같은 값을 여기서 튕긴다
    return s


def clamp_today(end: str, today: date | None = None) -> str:
    """**미래 날짜를 오늘로 당긴다.**

    WAMIS 는 ``enddt`` 가 하루라도 미래면 자료를 주는 대신 ``failure`` 를 돌려준다.
    "오늘까지 받아 둬"라는 지극히 평범한 요청이 통째로 실패하는 원인이라, 잘라
    보내는 편이 낫다. 잘라도 잃는 자료가 없다 — 미래 자료는 애초에 없다.
    """
    t = (today or date.today()).strftime("%Y%m%d")
    return min(ymd(end), t)


def request(group: str, op: str, params: dict[str, str],
            *, tries: int = DEFAULT_TRIES, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """WAMIS 한 번 호출. 성공하면 파싱된 본문(dict)을 그대로 돌려준다.

    ``자료 없음``(success/0)은 **오류가 아니므로** 그대로 반환한다. 호출자가
    ``count`` 로 판단한다.

    :raises WamisError: 서버가 요청을 거절했다(재시도 안 함).
    :raises WamisUnavailable: 연결이 계속 끊겼다(재시도 소진).
    """
    q = dict(params)
    q["output"] = "json"
    url = f"{BASE}/{group}/{op}?" + urllib.parse.urlencode(q, encoding="utf-8")

    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, ConnectionError, socket.timeout,
                json.JSONDecodeError) as exc:
            # RST·타임아웃·잘린 본문 — 전부 "서버가 바쁘다"의 다른 얼굴이다.
            last = exc
            if attempt < tries - 1:
                time.sleep(BACKOFF_SEC * (attempt + 1))
            continue

        result = body.get("result") or {}
        if result.get("code") == "failure":
            raise WamisError(f"{result.get('msg', '알 수 없는 거절')} — {url}")
        return body

    raise WamisUnavailable(
        f"{tries}회 시도 모두 연결 실패({type(last).__name__}) — {url}") from last


def rows(group: str, op: str, params: dict[str, str], **kw) -> list[dict]:
    """:func:`request` 의 ``list`` 만 꺼낸다. 자료가 없으면 빈 목록."""
    return request(group, op, params, **kw).get("list") or []
