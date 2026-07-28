# nk_crawl.py — 북한 홍수·기상 크롤링 툴킷

`flood_nk/CRAWL_GUIDE_KR.md`의 절차를 코드로 모듈화한 **표준 라이브러리 전용**
스크립트. 별도 패키지 설치가 필요 없다.

## 실행 환경
이 PC에는 conda base python이 있다(가이드 참조):
```
C:/Users/chlwn/miniconda3/python.exe
```
PowerShell/터미널에서 한글 출력이 깨지면 `PYTHONIOENCODING=utf-8` 설정.

## 명령어

| 명령 | 설명 |
|---|---|
| `python nk_crawl.py sources` | 검증된 출처 레퍼런스(접근 가능/차단 표시) |
| `python nk_crawl.py spn <idxno...>` | SPN 「오늘의 북한 날씨」 파싱(날짜·강수·기온·이미지) |
| `python nk_crawl.py spn <idxno...> --md` | 결과를 마크다운 표로 |
| `python nk_crawl.py spn <idxno...> --json` | JSON(전체 필드: summary 포함) |
| `python nk_crawl.py spn <idxno...> --check-images` | 파싱 + 이미지 HTTP 200 검증 |
| `python nk_crawl.py verify <img_url...>` | 이미지 URL 접근성만 검증 |

## 예시
```bash
export PYTHONIOENCODING=utf-8
PY="C:/Users/chlwn/miniconda3/python.exe"

# 최근 SPN 날씨 여러 건을 표로 → 그대로 SPN_오늘의_북한날씨_*.md에 붙여넣기
"$PY" nk_crawl.py spn 109124 109172 109198 109235 109256 --md

# 임베드 전 이미지 검증(가이드 3.4절)
"$PY" nk_crawl.py verify \
  https://cdn.spnews.co.kr/news/photo/202607/109086_110996_5431.png \
  https://img.newspim.com/news/2026/07/23/2607231023130730_w.jpg
```

## 반환 필드 (SpnWeather)
`idxno, url, title, date, summary, rainfall[], pyongyang_temp,
samjiyon_temp, images[]`

- `date`는 EUC-KR 본문에서 추출(`YYYY-MM-DD`).
- `rainfall`은 본문(태그 제거)에서 지역별 그룹까지 보존. 실패 시 og:description 폴백.
- `images`는 og:image + 본문 `cdn.spnews.co.kr` 사진 URL(중복 제거).

## 검증
07-22~26(idxno 109124·109172·109198·109235·109256) 5건이 수작업 크롤링 값과
일치함을 확인(2026-07-28). 07-24 평양 기온 공란은 원문에 평양 지역명이 생략된
정상 결과.

## 한계 / 확장 여지
- SPN 날씨 기사만 자동화(가장 정형). **조선중앙TV·통일뉴스·뉴스핌·세계일보**
  등 경보 기사는 구조가 제각각이라 아직 수동(WebFetch) 권장.
- 사이트 HTML/메타 구조 변경 시 `nk_crawl.py`의 `_RE_*` 정규식 조정 필요.
- 차단 소스(연합 `yna.co.kr`, `voakorea` 403)는 코드로도 우회 불가 → 재전재본.
