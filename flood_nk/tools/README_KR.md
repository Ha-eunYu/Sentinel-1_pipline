# nkcrawl — 북한 홍수·기상 크롤링 툴킷

`CRAWL_GUIDE_KR.md`의 절차를 코드로 모듈화한 **표준 라이브러리 전용** 패키지.
별도 설치가 필요 없고, **라이브러리**로 import 하거나 **CLI**로 실행할 수 있다.

## 구성

```
tools/
├─ nkcrawl/               (패키지 = 실제 구현)
│  ├─ __init__.py         공개 API export
│  ├─ __main__.py         python -m nkcrawl 진입점
│  ├─ sources.py          출처 레지스트리(SOURCES) + User-Agent
│  ├─ http.py             http_get / check_image (범용 HTTP)
│  ├─ spn.py              SPN 날씨 파서·수집기(SpnWeather 등)
│  └─ cli.py              argparse CLI
├─ nk_crawl.py            얇은 CLI 래퍼(하위호환)
└─ README_KR.md           이 문서
```

## 실행 환경
Python 3.9+ (stdlib만 사용). 환경에 맞는 `python`을 쓰면 된다. 예를 들어 conda를
쓰면 해당 env의 `python`. 한글 출력이 깨지면 `PYTHONIOENCODING=utf-8` 설정.

세 가지 실행 방법(모두 동일):

```bash
python nk_crawl.py latest -n 3 --md        # 얇은 래퍼
python -m nkcrawl latest -n 3 --md         # 패키지 모듈 (tools/ 에서)
# 라이브러리:
python -c "import nkcrawl; [print(w.md_row()) for w in nkcrawl.spn_latest(3)]"
```

## CLI 명령어

| 명령 | 설명 |
|---|---|
| `sources` | 검증된 출처 레퍼런스(접근 가능/차단 표시) |
| `latest -n 3` | **idxno 몰라도** 최신 날씨 기사 자동 탐색 |
| `scan --from A --to B` | idxno 구간을 스캔해 날씨 기사만 수집 |
| `spn <idxno...>` | SPN 「오늘의 북한 날씨」 파싱(날짜·강수·기온·이미지) |
| `verify <img_url...>` | 이미지 URL 접근성만 검증 |

`--md`(마크다운 표) / `--json` / `--check-images`는 `latest`·`scan`·`spn` 공통.
`--timeout N`은 전역(기본 20초).

### idxno를 모를 때 (권장 시작점)

```bash
# A. 완전 자동: 사이트 최신 idxno에서 아래로 스캔해 최신 날씨 N건
python nk_crawl.py latest -n 3 --md --check-images

# B. 마지막 수집분을 알면 구간 스캔이 더 빠르고 확실
python nk_crawl.py scan --from 109257 --to 109300 --md
```

- `latest`는 SPN 검색 목록이 날씨를 못 거르므로(전 분야 최신 혼합), **최대 idxno에서
  아래로 한 건씩 조회**해 제목에 '날씨'가 있는 기사만 모은다(`--max-scan` 기본 120).
- 날씨 기사는 하루 1건, idxno 간격이 수십이라 `latest`는 요청이 다소 많다.
  마지막 수집 idxno를 알면 `scan --from <그 번호+1> --to <최근>`이 빠르다.

## 라이브러리 API

```python
import nkcrawl
nkcrawl.spn_latest(3)                 # 최신 날씨 3건 → [SpnWeather, ...]
nkcrawl.fetch_spn(109271)             # idxno 1건
nkcrawl.collect_spn_weather(range(109298, 109270, -1))  # 구간
nkcrawl.check_image("https://…​.png") # 이미지 200 검증 → dict
nkcrawl.SOURCES                       # 출처 레지스트리(dict)
```

**SpnWeather 필드:** `idxno, url, title, date, summary, rainfall[],
pyongyang_temp, samjiyon_temp, images[]` + `.md_row()`.

- `date`는 본문에서 추출(`YYYY-MM-DD`, EUC-KR/UTF-8 자동 디코딩).
- `rainfall`은 본문(태그 제거)에서 지역별 그룹까지 보존, 실패 시 og:description 폴백.
- `images`는 og:image + 본문 `cdn.spnews.co.kr` 사진 URL(중복 제거).

## 검증
07-22~26(idxno 109124·109172·109198·109235·109256) 5건이 수작업 크롤링 값과
일치. `latest`가 07-27=109271, 07-28=109297, 07-29를 자동 탐색함을 확인.
07-24 평양 기온 공란은 원문에 평양 지역명이 생략된 정상 결과.

## 한계 / 확장 여지
- **SPN 날씨 기사만 자동화**(가장 정형). 조선중앙TV·통일뉴스·뉴스핌·세계일보
  등 경보 기사는 구조가 제각각이라 아직 수동(WebFetch) 권장.
- 사이트 HTML/메타 구조 변경 시 `nkcrawl/spn.py`의 `_RE_*` 정규식 조정.
  새 매체 자동화는 `spn.py`를 본떠 모듈을 추가하고 `sources.py`에 등록.
- 차단 소스(연합 `yna.co.kr`, `voakorea` 403)는 코드로도 우회 불가 → 재전재본.
