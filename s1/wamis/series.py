# -*- coding: utf-8 -*-
"""댐 **수문 시계열** 수집 — 기간을 잘라 받고, 겹친 부분을 정리해 되돌린다.

두 가지 자료를 받는다. **저수량·저수율이 시자료에만 있다**는 것이 이 모듈의
설계를 거의 다 결정한다.

============ ================== ====================================== =========
함수          WAMIS               얻는 것                                비용
============ ================== ====================================== =========
:func:`daily`  ``mn_dtdata``      저수위·유입·방류·강우                    싸다
:func:`hourly` ``mn_hrdata``      + **저수량·저수율**                     비싸다
============ ================== ====================================== =========

측정해서 정한 것들 (2026-09-09, 소양강 기준)
--------------------------------------------
* **일자료는 373일까지 됐고 730일은 3회 시도 모두 실패**했다. 다만 365일 요청은
  7.2초가 걸리고 재시도를 요구했다. 180일이면 0.1초에 끝난다 — 그래서 기본
  청크를 180일로 뒀다. **길게 물어 이득이 없다.**
* **시자료는 7일이 7.1초, 5일이 3.1초**였고 25일은 3번째 시도에서야 붙었다.
  기본 5일.
* **끊김은 영구 실패가 아니다.** 같은 요청이 다음 시도에 성공하는 것을 반복
  확인했다. 재시도는 :mod:`s1.wamis.client` 가 맡는다.

⚠ **시자료 경계 아티팩트** — 요청 시작일의 **00시가 항상 빠진다.** 3일치를
받으면 첫날만 01~23시(23행), 나머지는 00~23시(24행)로 온다. 청크를 이어 붙이면
경계마다 한 시간씩 구멍이 나므로, :func:`hourly` 는 **하루 앞에서 시작해** 받은
뒤 요청 범위로 잘라낸다. 청크 사이도 하루씩 겹쳐 받고 ``obsdh`` 로 중복을 없앤다.

필드 뜻 (실측으로 확인한 것만 단정한다)
---------------------------------------
======== ============ ==================================================
필드      단위          뜻
======== ============ ==================================================
rwl      EL.m         저수위
rsqty    백만 m³       저수량 *(시자료 전용)*
rsrt     %            저수율 *(시자료 전용)* — ``rsqty / 총저수용량``
iqty     m³/s         유입량
tdqty    m³/s         총방류량 (= edqty + spdqty + otltdqty)
edqty    m³/s         발전방류량
spdqty   m³/s         여수로 방류량
otltdqty m³/s         기타 방류량
itqty    m³/s         취수량
rf       mm           유역평균 강우량 *(일자료)*
dambsarf mm           댐유역 평균우량 *(시자료)*
======== ============ ==================================================

``rsrt`` 가 정말 저수율인지는 **총저수용량으로 역산해 확인**했다 — 소양강
1995.803/0.688 = 2900, 충주 1519.954/0.553 = 2749, 대청 961.568/0.645 = 1491
백만 m³ 로 셋 다 공표 총저수용량과 일치한다.

``etqty`` 는 규격 문서를 못 찾았지만 **자료가 정체를 말해 준다** — ``rsqty +
etqty`` 가 댐마다 상수다(소양강 2720.873, 섬진강 471.425, 20일 내내 ±0.001).
즉 **어떤 기준수위 대비 빈 용량(공용량)** 이다. 다만 그 기준은 ``rsrt`` 산정에
쓰인 총저수용량과 **다르다**(소양강 2720.9 vs 2899.1). 그래서 저수율을 여기서
다시 계산하지 말고 ``rsrt`` 를 그대로 쓴다.

``ospilwl`` 은 **뜻을 확인하지 못했다.** 값은 그대로 실어 보내되 이름을 바꾸거나
해석하지 않는다 — 모르는 값에 이름을 붙이는 것이 빠뜨리는 것보다 나쁘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from s1.wamis.client import clamp_today, rows, ymd

# 청크 크기 — 위 주석의 실측에서 나온 값이다. 늘리면 느려지고 끊긴다.
DAILY_CHUNK_DAYS = 180
HOURLY_CHUNK_DAYS = 5

# 숫자로 바꿀 필드. 그 외(obsymd·obsdh)는 문자열로 둔다.
_NUMERIC = ("rwl", "rsqty", "rsrt", "iqty", "tdqty", "edqty", "spdqty",
            "otltdqty", "itqty", "rf", "dambsarf", "ospilwl", "etqty")

DAILY_FIELDS = ("obsymd", "rwl", "iqty", "tdqty", "edqty", "spdqty",
                "otltdqty", "itqty", "rf")
HOURLY_FIELDS = ("obsdh", "rwl", "rsqty", "rsrt", "ospilwl", "iqty", "etqty",
                 "tdqty", "edqty", "spdqty", "otltdqty", "itqty", "dambsarf")


@dataclass
class Fetch:
    """수집 결과 + **무슨 일이 있었는지.**

    빈 결과에는 이유가 두 가지다 — 그 댐이 자료를 안 내는 것과, 서버가 계속
    끊긴 것. 둘을 구분하지 않으면 조용히 빈 CSV 가 나온다. ``failed`` 가
    비어 있지 않으면 **결과가 불완전**하다는 뜻이다.
    """
    rows: list[dict] = field(default_factory=list)
    chunks: int = 0
    failed: list[tuple[str, str, str]] = field(default_factory=list)  # (시작,끝,사유)

    @property
    def complete(self) -> bool:
        return not self.failed


def _to_float(v):
    """빈 문자열·None 은 ``None``. ``'.1443'`` 처럼 앞자리가 없는 값도 들어온다."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in {"-", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean(row: dict, keys: tuple[str, ...]) -> dict:
    out = {}
    for k in keys:
        v = row.get(k)
        out[k] = _to_float(v) if k in _NUMERIC else (str(v).strip() if v else None)
    return out


def _windows(start: str, end: str, days: int, overlap: int = 0):
    """[start, end] 를 ``days`` 짜리 창으로 자른다. ``overlap`` 만큼 겹쳐서."""
    d0 = datetime.strptime(start, "%Y%m%d").date()
    d1 = datetime.strptime(end, "%Y%m%d").date()
    step = timedelta(days=days - 1)
    cur = d0
    while cur <= d1:
        stop = min(cur + step, d1)
        yield cur.strftime("%Y%m%d"), stop.strftime("%Y%m%d")
        if stop >= d1:
            return
        cur = stop + timedelta(days=1) - timedelta(days=overlap)


def _collect(op: str, damcd: str, start: str, end: str, keys: tuple[str, ...],
             chunk_days: int, overlap: int, key_field: str,
             today: date | None = None, **kw) -> Fetch:
    """청크 반복 + 중복 제거의 공통부. 한 청크가 죽어도 나머지는 계속 받는다."""
    s = ymd(start)
    e = clamp_today(end, today)
    if s > e:
        return Fetch()

    out = Fetch()
    seen: dict[str, dict] = {}
    for c0, c1 in _windows(s, e, chunk_days, overlap):
        out.chunks += 1
        try:
            got = rows("wkd", op, {"damcd": damcd, "startdt": c0, "enddt": c1}, **kw)
        except Exception as exc:                # WamisError·WamisUnavailable 둘 다
            # 한 구간이 안 된다고 나머지를 버리지 않는다. 대신 반드시 남긴다.
            out.failed.append((c0, c1, f"{type(exc).__name__}: {exc}"))
            continue
        for r in got:
            k = str(r.get(key_field) or "")
            if k:
                seen[k] = _clean(r, keys)      # 겹친 구간은 나중 값으로 덮는다

    out.rows = [seen[k] for k in sorted(seen)]
    return out


def daily(damcd: str, start, end, *, chunk_days: int = DAILY_CHUNK_DAYS,
          today: date | None = None, **kw) -> Fetch:
    """**일자료**(``mn_dtdata``) — 저수위·유입·방류·강우.

    ⚠ 저수량·저수율은 여기 **없다.** 그 둘은 :func:`hourly` 에만 있다.

    ⚠ 하루 늦다 — 2026-09-09 에 물으면 09-08 까지 온다.
    """
    return _collect("mn_dtdata", damcd, start, end, DAILY_FIELDS,
                    chunk_days, 0, "obsymd", today, **kw)


def hourly(damcd: str, start, end, *, chunk_days: int = HOURLY_CHUNK_DAYS,
           today: date | None = None, **kw) -> Fetch:
    """**시자료**(``mn_hrdata``) — 저수량·저수율까지.

    시작일의 00시가 빠지는 서버 습성 때문에 **하루 앞에서 받아** 요청 범위로
    잘라낸다. 그래서 실제 호출 구간은 요청보다 하루 넓다.
    """
    s = ymd(start)
    e = clamp_today(end, today)
    if s > e:
        return Fetch()

    pre = (datetime.strptime(s, "%Y%m%d").date() - timedelta(days=1)).strftime("%Y%m%d")
    got = _collect("mn_hrdata", damcd, pre, e, HOURLY_FIELDS,
                   chunk_days, 1, "obsdh", today, **kw)
    got.rows = [r for r in got.rows if s <= (r["obsdh"] or "")[:8] <= e]
    return got


def daily_from_hourly(hourly_rows: list[dict], hour: int = 0) -> list[dict]:
    """시자료를 **하루 한 줄**로 줄인다 — 저수량·저수율의 일별 시계열용.

    같은 시각을 매일 골라야 비교가 성립한다(저수위는 하루 안에서도 움직인다).
    기본은 00시 — 그 날이 시작되는 값이다.

    고른 시각이 결측인 날은 **그 날의 마지막 관측**으로 대신하고, 어느 쪽인지
    ``src_hour`` 에 남긴다. 조용히 메우면 나중에 구분할 수 없다.
    """
    want = f"{hour:02d}"
    by_day: dict[str, dict[str, dict]] = {}
    for r in hourly_rows:
        stamp = r.get("obsdh") or ""
        if len(stamp) == 10:
            by_day.setdefault(stamp[:8], {})[stamp[8:]] = r

    out = []
    for day in sorted(by_day):
        hours = by_day[day]
        hh = want if want in hours else max(hours)
        row = dict(hours[hh])
        row.pop("obsdh", None)
        out.append({"obsymd": day, "src_hour": hh, **row})
    return out
