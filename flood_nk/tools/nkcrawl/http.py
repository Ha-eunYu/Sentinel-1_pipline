# -*- coding: utf-8 -*-
"""범용 HTTP 유틸 (stdlib only).

어떤 소스에도 쓸 수 있는 저수준 도구:
- :func:`http_get`   : 인코딩 자동 판별 텍스트 GET (EUC-KR/UTF-8 등)
- :func:`check_image`: 이미지 URL 접근성 검증(임베드 전 필수 절차)
"""
from __future__ import annotations

import re
import urllib.request

from .sources import UA


def _decode(raw: bytes, ctype: str) -> str:
    """Content-Type 또는 <meta charset>에서 인코딩을 판별해 디코딩.

    한국 언론사는 EUC-KR(cp949)과 UTF-8이 섞여 있어 자동 판별이 필요하다.
    """
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
    """URL을 GET 해 (자동 디코딩된) 텍스트를 반환."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _decode(r.read(), r.headers.get("Content-Type", ""))


def check_image(url: str, timeout: int = 20) -> dict:
    """이미지 URL 접근성 검증.

    Returns dict: ``{url, ok, status, content_type, bytes[, error]}``.
    ``ok``는 HTTP 200 이고 content-type이 ``image/*`` 일 때만 True.
    """
    def _probe(method: str):
        req = urllib.request.Request(
            url, headers={"User-Agent": UA}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read() if method == "GET" else b""
            return (r.status, r.headers.get("Content-Type", ""),
                    int(r.headers.get("Content-Length") or len(data)))
    try:
        try:
            status, ctype, size = _probe("HEAD")
            if status == 200 and size == 0:  # 일부 서버 HEAD에 length 미제공
                status, ctype, size = _probe("GET")
        except Exception:  # noqa: BLE001  (HEAD 미지원 → GET 폴백)
            status, ctype, size = _probe("GET")
        ok = status == 200 and ctype.lower().startswith("image/")
        return {"url": url, "ok": ok, "status": status,
                "content_type": ctype, "bytes": size}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": False, "status": None,
                "content_type": "", "bytes": 0, "error": repr(e)}
