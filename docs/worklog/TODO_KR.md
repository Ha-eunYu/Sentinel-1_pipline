# TODO (2026-08-14 갱신)

다른 컴퓨터에서 이어서 작업할 때 참고하는 실행 목록. 배경·근거는
[CODE_REVIEW_KR.md](../review/CODE_REVIEW_KR.md)(코드 품질)와 [PROGRESS_KR.md](PROGRESS_KR.md)
(작업 이력·데이터 현황)에 있고, 여기는 "무엇을 해야 하는지"만 체크리스트로 정리합니다.
문제의 원인·증상은 [ISSUES_KR.md](ISSUES_KR.md)에 따로 모읍니다.

> **운영 규칙**: 작업 중 확인이 필요하거나 나중에 해야 할 것이 나오면
> **그때 바로 이 문서에 추가**한다. 대화에만 남기면 다음 세션에서 사라진다.

## P0.1 — 25·26년 VH external DEM 통일 (2026-08-14 착수, 진행 중)

배경: 7월 VH 산출물이 전부 `--dem` 옵션 도입(08-10) **이전**에 만들어져 SNAP
자동 캐시 COP30을 썼다. 하구 결측 문제([ISSUES_KR](ISSUES_KR.md) #2)에 노출돼
있어 external DEM(`downloads/dem_basin/korea_full_cop30.tif`)으로 통일한다.

- [x] **26년 7월 남한 궤도 19씬 VH ext-DEM** — 완료 (2026-08-14, 실패 0)
      — 대상: rel 32(o008355·o008530·o008705), rel 61(o008384·o008734 08EE),
        기타 SK 궤도의 미처리 프레임
- [x] **7월 전량 external DEM 통일 완료** (2026-08-17 02:05).
      25·26년 7월 63씬 모두 `korea_full_cop30.tif` 기준. 자동 DEM 잔여 0.
      재처리로 산출물이 커진 경우가 많다 — `F336`(25-07-01)은 **0.05 GB →
      1.16 GB**로, 자동 DEM일 때 대부분이 결측이었다(ISSUES #2의 극단 사례).
- [x] **비교 본선 4궤도 재처리 완료** (2026-08-15) — rel 134(25-07-18 C ↔
      26-07-20 C), rel 54(25-07-25 C ↔ 26-07-15 C) 17씬을 VH +
      korea_full_cop30 기준으로 다시 구웠다(**17/17 완료**, 08-15 05:58).
      `6D9F`는 `.SAFE.zip` 패턴 문제로 한 번 조용히 건너뛰어졌다가
      (ISSUES #15) 마지막에 처리했다 — 2.19 GB(자동 DEM) → 2.77 GB.
      **이 두 쌍은 수체탐지 프로젝트로 바로 넘길 수 있는 상태다.**
- [ ] **8월 (25·26년) — 신규 3씬 + DEM 통일 재처리 6씬** (2026-08-17 착수)
      - 신규(VH 없음): `CDCC`·`037F`(25-08-11), `BDA2`(26-08-07)
      - **재처리(다른 external DEM을 씀)**: `2B35`·`9FBB`·`9F4F`(25-08-11),
        `EF16`·`FC19`(26-08-07) ← `korea_cop30.tif` /
        `17B9`(26-08-02) ← `han_cop30.tif`
      - 이미 `korea_full_cop30.tif`로 처리됨(재처리 불필요): `D0A4`·`E160`·
        `3EEB`(25-08-06), `9A11`·`C40B`(25-08-12), `3B05`·`B10F`(26-08-02)

> **external DEM은 `korea_full_cop30.tif`로 통일한다(2026-08-14 결정).**
> 후보 DEM들의 실제 범위를 재보니 이것만 남한 전역 + 제주 + 울릉을 덮는다.
>
> | DEM | 범위 | 제주 |
> | --- | --- | --- |
> | `korea_full_cop30.tif` | 125.0~131.0E, 32.9~39.9N | ✅ |
> | `korea_cop30.tif` | 125.4~129.9E, **33.8**~38.7N | ❌ (제주 33.1~33.6N) |
> | `han_cop30.tif` | 125.7~129.9E, 35.6~39.2N | ❌ (부산·목포도 빠짐) |
>
> DEM 밖 영역은 RTC 산출물에서 **무효(결측)** 로 남는다. 유역 단위 작업에는
> 유역 clip DEM이 효율적이지만, **남한 전역을 한 기준으로 비교하려면 범위가
> 같아야** 한다.
>
> **용량 주의**: external DEM 산출물은 자동 DEM 것보다 크다(결측이 메워지므로).
> 7월 재처리로 F: 여유가 100 GB → 73 GB로 줄었다. 22~24년 확장 전에는
> NAS 업로드가 선행돼야 한다.

> **이 프로젝트의 범위는 RTC까지다(2026-08-14 결정).** VH external DEM RTC가
> 끝나면 여기서 마친다. **수체탐지는 다른 프로젝트에서 진행**하므로 이 저장소의
> `build_water_per_date_otsu.py` 재실행은 계획에 넣지 않는다.
> 넘길 것: `downloads/rtc_grd_frost_vh/*_rtc_db_vh.tif`(전량 external DEM),
> 처리 조건은 [PROCESS_202507_202607_KR.md](../pipeline/PROCESS_202507_202607_KR.md)
> 2절, 궤도 선별 근거는
> [RELATIVE_ORBITS_KR.md](../pipeline/RELATIVE_ORBITS_KR.md).

## P0.2 — 연도 간 비교 설계 (2026-08-14 확정, 실행 대기)

배경·근거: [RELATIVE_ORBITS_KR.md](../pipeline/RELATIVE_ORBITS_KR.md).

- [ ] **공통 관측영역 마스크** — (대권역 × 상대궤도)를 단위로, 양쪽 다
      유효화소인 픽셀만 남겨 집계. 한강처럼 한 궤도가 다 못 덮는 대권역은
      궤도별 부분면적으로 나눠 비교하고 **합산 대신 궤도별 변화율**을 주 지표로.
- [ ] **궤도 간 편향 측정** — 동일일자 6쌍(2023-08-04 rel54↔127 등)의 공통
      영역 수체 면적 차이. 판정: <5% 합산 가능 / 5~15% 보정 후 사용 /
      >15% 궤도별 따로 제시([RELATIVE_ORBITS_KR](../pipeline/RELATIVE_ORBITS_KR.md) 7-6).
      → 2023년·2025년 8월 일부는 **원본 미보유**라 다운로드가 선행.
- [ ] **rel 134·61의 23·25·26년 3개년 비교**
- [ ] **⚠ rel 61 분리도 확인** — 25년 관측이 1프레임짜리 2건뿐이고 남한 커버가
      8~29%로 얕다. 25년 7/19 o060151이 Otsu 실패로 fallback(−16 dB)한 것과
      같은 조건이다. **결과가 나오면 임계값보다 분리도 η를 먼저 보고**, 낮으면
      비교에서 제외하거나 fallback 여부를 명시할 것.
- [ ] **22~24년 확장은 rel 54·127로만** (5개년 연속 관측되는 유일한 궤도)
- [ ] **2025년 S1C를 쓸 때는 그 달 오프셋을 STAC으로 확인**하고 시작
      (`relative_orbit_survey.py --years 2025 --months ...`). 표의 171은
      7·8월에서만 확인한 값이다.
- [ ] 제주 전용 COP30 clip → rel 134 씬으로 제주 RTC (현재 보류)
- ~~SLC 컬렉션 상대궤도 조사~~ — **불필요, 제외(2026-08-14)**.
  수면적 산출의 입력은 GRD다. SLC는 **간섭(coherence·InSAR)** 을 할 때만 필요한데
  이 프로젝트 범위가 아니다. 조사 도구에 `--collection` 옵션이 있어 관성으로
  적어둔 항목이었다. 나중에 coherence 분석을 하게 되면 그때
  `relative_orbit_survey.py --collection sentinel-1-slc` 한 줄로 확인한다.

## P0.3 — 정정 전파 (2026-08-14)

- [x] **GitHub 이슈 본문 정정** — 정정본으로 #8 재등록 완료(구버전 #6은 닫을 것)

- [x] **이슈 #11·#12 등록 완료** — GitHub #9·#10 (2026-08-14)
- [x] **GitHub #6 닫기(#8 중복) 완료** (2026-08-14) — 제목 변경으로 중복 생성됐던 건

- [ ] **대외 보고분 확인** — "25/26년 비교 가능한 상대궤도 짝이 하나뿐"이라는
      문장이 나갔다면 정정 필요. 실제로는 rel 54·61·127·134 네 궤도에 짝이
      있고 rel 134는 위성까지 같다.

## P0.5 — 8월 가뭄 비교쌍 (9/8 보고용)

배경·상세: [WORKLOG_20260807_KR.md](WORKLOG_20260807_KR.md)(최초 6개 유역) ·
[WORKLOG_20260810_12_KR.md](WORKLOG_20260810_12_KR.md)(유역 확장 + external DEM).
광학은 2025-08 ↔ 2026-08인데 SAR만 7월이라 시기를 맞추는 작업.

### 전처리 (S1) — 완료

- [x] **8월 관측 전수 점검** — 78장을 (촬영일×상대궤도)로 묶어 8개 댐유역·
      대권역 커버리지 산정. 8/7의 "6개 유역만 가능" 결론이 뒤집혔다(2026-08-07
      ASC127이 조회 후 등재됨).
- [x] **6개 댐 유역 + 낙동강** ASC54 2025-08-06 ↔ 2026-08-02 (1C↔1D)
- [x] **섬진강·영산강·평림** ASC127 2025-08-11 ↔ 2026-08-07 (1C↔1D)
- [x] **금강** ASC127 같은 쌍 — 9F4F 1장 추가로 76.5% → **100%**
- [x] **한강** ASC54 **2025-08-12** ↔ 2026-08-02 (**1A↔1D**) — 공통 85.1%.
      08-06(1C)은 69.3%가 상한이라 커버리지를 택했다.
- [x] **external DEM 전환** — ASC54 5장 재처리로 8월 14장 전량 통일.
      자동 캐시 DEM이 낙동강 하구 **12.48 km²**를 무효로 만들던 결함 제거.
      창 패치는 불필요해져 `rtc_extdem/_superseded/`로 격리.
- [x] **`korea_full_cop30.tif`** — 대권역 21 + 댐유역 8 전부 nodata 0.
- [x] **GRD 원본 E: 이관**(169 GB, 정션) — F: 4.2 → 173.4 GB.

### 산출 (gee) — 진행 중

- [x] `watershed_change_v9.csv` (낙동강 + 6개 댐) · `_v9_asc127.csv`
      (섬진강·영산강·평림). external DEM 반영으로 임계 +0.70/+0.53 dB 이동,
      변화율 최대 4.5%p 변동(성덕 −29.7 → −25.2%).
- [ ] **한강·금강 산출 추가** — v9 두 파일에 **두 유역 행이 없다.** 전처리는
      끝났고 모자이크도 최신이다. `watershed_pairs.py`의 `ORBIT` 표에
      `"20250812": "ASC54"` 등록이 선행돼야 한다(없으면 `pick()`에서 KeyError).
- [ ] **한강 산출범위 표기** — 제약의 **21.1%가 미관측**(스와스 밖, DEM 결함
      0.15%)이라 "제약+북쪽AOI"로 갈라 다른 유역과 직접 비교되지 않게 할 것.

### 보고서

- [ ] **[REPORT_AUG_SAR_KR.md](../../../2026_drought_map/REPORT_AUG_SAR_KR.md) 갱신**
      — §1 유역별 궤도·위성 표(한강만 1A↔1D), §4 수치를 v9로,
      §5 DEM 문구(이제 전량 external DEM이라 사실과 맞음), §6 한강 관측률.
- [x] 임계값 대조 — 두 해 차이 0.17 dB로 1.5 dB 선에 크게 못 미친다.
      위성 교체 단서는 불필요(단 한강은 1A↔1D라 별도 표기).
- [x] 섬진강·평림 방침 — ASC127로 산출 가능해져 8월 표에 포함.

### 남은 확인

- [ ] **2026-08 재조회** — 8/7에 "없다"고 판정한 뒤 ASC127이 등재된 전례가
      있다. 한강을 1C↔1D로 되돌릴 짝이 생겼는지 확인할 것.
- [ ] **8월 GRD zip NAS 업로드 후 로컬 삭제** (사용자 수행 예정)

## P0 — 지금 바로 (다른 작업보다 먼저)

- [ ] **CDSE 비밀번호 변경**. `.env`가 한동안 public GitHub에 커밋돼 있었고
      (`git filter-repo`로 히스토리에서는 제거했지만 노출 자체는 되돌릴 수 없음),
      실제 `CDSE_PASSWORD` 값이 노출됐었습니다.
      <https://dataspace.copernicus.eu> 계정 설정에서 변경.
- [ ] **S3 access/secret key 재발급**. 같은 `.env`에 `CDSE_S3_ACCESS_KEY`,
      `CDSE_S3_SECRET_KEY`도 있었습니다. 발급받은 콘솔에서 폐기 후 재발급.
- [ ] 두 값을 로컬 `.env`(현재 이 컴퓨터)와, 다른 컴퓨터로 옮길 경우 그쪽 `.env`에도 갱신.
- [ ] **(신규, 7/14) `.env` 재발급 시 반드시 백업해둘 것**: 오늘 `git filter-repo`
      실행 중 로컬 `.env`가 통째로 삭제되는 사고가 있었음(아래 P4 참고). 지금
      만드는 새 `.env`는 프로젝트 밖(예: 비밀번호 관리자, 클라우드 노트)에도
      한 부 저장해두면 같은 사고가 나도 git 작업만으로 복구 가능.

## P1 — 한반도 전체 수집·탐지 (진행 중, 2026-07-20 갱신)

- [x] **일본/중국 전용 궤도 제외** — `Korea_Peninsula.geojson` bbox 검색이라
      가장자리에 일본·중국 위주 프레임이 섞여 들어옴. 판별은 **프레임 전체
      footprint 폴리곤을 `Korea_Peninsula.geojson`(남북한 실경계)과 shapely로
      교차 계산**해서 함 (bbox 사각형 겹침이나 대표좌표 1점 역지오코딩은
      부정확 — SAR 프레임이 대각선 스와스라 사각형엔 빈 바다가 많고, 대표점이
      한쪽 끝에 찍히면 반대쪽 끝의 실제 한국 영토를 놓침. 예: `satellite_
      inventory_sido_korean_*.csv`가 9919/D440/E067/4C8A/D298/3191/4C7C 등을
      "일본"으로 단일 태그했지만 이 씬들은 실제 검증된 침수 검출에 쓰였음).
      한반도 실경계와 **0% 겹침 확인된 것만** 제외: `CDFD`(6/30)·`1CE4`(7/12,
      같은 궤도, 서해 원해·중국), `F598`·`F05D`(7/4, 대한해협~일본 규슈).
      제외 씬은 zip을 삭제해 RTC 큐에서 자동 스킵되게 함.
      **주의(7/22)**: X드라이브(NAS) `rsync --ignore-existing`은 로컬에서 지운
      파일도 원본엔 남아있어 재실행 때마다 이 4개를 다시 끌고 옴 — rsync
      돌릴 때마다 `downloads/sentinel1_grd/`에 이 4개(CDFD/1CE4/F598/F05D)가
      재유입됐는지 확인하고 있으면 삭제할 것.

- [x] **한반도 전체(북한 포함) GRD 일괄 수집** (7/19) — `Korea_Peninsula.geojson`
      bbox로 6/25~7/18 재검색, 신규 44개 다운로드 → 총 73씬. 용량 확보를 위해
      SLC 원본 103GB를 `D:\06_SAR_system_archive\sentinel1`로 이동하고 기존
      경로에 junction 연결(스크립트 무수정 동작). 완료 후 RTC 끝난 GRD zip
      **60개도 NAS(`X:\02_Analysis\20260708_Flood\Sentinel-1`) 크기 검증 후
      로컬 삭제** (F: 35→143GB 확보). 사용자가 NAS 업로드 후 로컬 삭제하는
      방식으로 계속 운영 중 — 다운로드 폴더 점검 시 항상 NAS와 대조할 것.
- [x] **북한 관련 잔여 8씬 우선순위 처리** (7/20) — 처음엔 궤도 겹침 비율
      순으로 정했다가, 사용자 요청으로 **날짜 최신순**으로 재조정:
      `0B91`(7/19)→`3194`(7/19)→`2B06`(7/18)→`9FFF`(7/16)→`5D47`(7/7)→
      `525F`(7/7)→`1571`(7/4)→`794A`(6/25, 중국접경이라 최후순위). 진행 중
      `794A`가 150분(정상 최대치 93FC의 69분의 2배)까지 늘어져 멈춘 것으로
      판단해 강제종료 후 재시도 목록 맨 뒤로 배치.
      **2B06의 같은 궤도(12일 반복) 짝 정정**: 이전에 "6668·427D·74FD·F040·
      4D62(7/6 전체)"라고 잘못 안내함 — 정밀 대조 결과 같은 스와스 위치는
      **`427D` 하나뿐** (나머지 4개는 7/6 패스의 다른 위치, 무관).
- [x] **baseline v3 재구축 완료** (7/21) — 컷오프 7/3 유지 + `--fallback-dates
      20260704,20260706,20260707`로 빈틈메우기(`build_baseline_composite_grd.py`
      옵션 신규). baseline 수체 2,575→6,308 km²(북한 전역 커버).
- [x] **8개 날짜 전체 재탐지 완료** (7/21) — `7/4·7/7·7/13·7/14·7/15·7/16·
      7/18·7/19`를 v3로 일관 재계산 + 남/북 분리. [FLOOD_TIMELINE_KR.md]
      (FLOOD_TIMELINE_KR.md) 갱신 완료. **결론: 남한 수치는 신뢰 가능(7/14
      154km² 최대), 북한 수치는 대부분 아티팩트**(홍수 전 7/4·7/7에도 북한
      30~37km² 검출된 게 증거). v3는 북한 정량 추정엔 부적합.
- [x] **북한 동일궤도 pre/post 쌍 비교 완료** (7/21) — `detect_flood_grd_v2.py`에
      `--baseline`/`--tag` 옵션 추가해 같은 궤도 pre/post 1:1 차분. 결과(북한
      보수적): 7/13↔7/1 **190**, 7/18↔7/6 **254**, 7/19↔6/25 **465** km².
      (7/6·6/25 모자이크가 삭제된 중국 프레임/궤도 불일치로 처음 실패 → 로컬에
      남은 올바른 궤도 프레임만으로 `_s1d`/`_kr` 모자이크 재생성해 해결.)
- [x] **북한 정량화 불가 결론 확정** (7/21) — v3와 동일궤도 값이 크게 다르고,
      7/13↔7/1 습윤도 진단에서 **7/1이 7/13보다 4.1배 넓게 젖음** = 7/1
      baseline이 이미 젖음. **SPN 북한 날씨로 교차검증**: baseline 후보
      6/25·7/1·7/6 전부 강수일 → **마른 baseline 부재**가 근본 원인.
      상세: [FLOOD_NORTH_KOREA_KR.md](../flood/FLOOD_NORTH_KOREA_KR.md) 5·6절.
- [x] **baseline 무관 단일시기 수체 지도** (7/21) — `build_water_per_date.py`
      (날짜별, 6/25~7/19 전 날짜)·`build_water_single_scene.py`(단일 씬 →
      `scene_water/`) 신규. 변화가 아닌 "상태"라 baseline 문제와 무관.
      낡은 VRT(삭제된 소스 참조) 자동 재생성 로직 포함.
- [ ] **(다음) 북한: 장마 이전 baseline 확보** — 관측 기간(6/25~) 내내 북한에
      강수가 있어 마른 baseline이 없음. 6월 초·중순 같은 궤도 관측을 추가
      수집하거나, Sentinel-2 광학·수위계로 교차검증해야 북한 정량화 가능.
- [ ] (선택) 7/16 강원 동부 97km² 검출(남한)의 교차검증 — Sentinel-2 광학 또는
      공식 피해현황(kmz)과 대조.
- [x] **7/20 패스(궤도 008632, CE47·0CEF·DD29·F314·74BD·93DD) RTC 완료** (7/21) —
      392D 포함 7프레임 전부 RTC 완료. `flood_water_total_20260720.tif`는
      아직 미생성 (필요 시 `build_water_per_date.py 20260720`).
- [x] **신규 촬영 씬 재확인** (7/21) — 갱신된 `Korea.geojson`으로 CDSE STAC
      재조회, 7/20 21:32 UTC(74BD) 이후 신규 게시 없음 확인. 93DD가 갱신된
      AOI와 더 이상 안 겹치는 점 발견(경계가 좁아짐, 이미 받은 93DD 자체는
      영향 없음) — 다음 신규 검색 때 서쪽 경계 프레임 누락 여부 주의.
- [ ] **X드라이브(NAS) zip 아카이브 병합** — `wsl rsync --ignore-existing`로
      X드라이브 GRD zip 75개 중 로컬에 없던 59개를 `sentinel1_grd/`로 병합
      진행 중(F: 여유공간 524.7GB, 문제없음). 완료 후 로컬 인벤토리 재확인.
- [x] **footprint 재감사·FLOOD_TIMELINE_KR.md 정정** (7/22) — NAS rsync로
      제외 씬 재유입을 계기로 전체 zip footprint 재검증, 7/8·7/10 발표
      수치가 100% 바다 아티팩트임을 확정하고 문서 정정. 상세:
      [SCENE_FOOTPRINT_REAUDIT_KR.md](../pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md).
- [ ] **7/17행(`D298`·`3191`·`4C7C`, 97.38km²) 격리 재계산** — 현재 저장된
      `flood_water_relaxed_20260716.tif`는 다른 궤도와 섞인 합성본이라 이
      3씬만의 값인지 확인 불가. `detect_flood_grd_v2.py --baseline --tag`로
      이 3씬만 모자이크해 재계산 필요(같은 궤도 003704 pre-event 짝 확인부터).

## P1(구) — post-event 영상 (7/14 시점 기록)

- [x] **S1C 하강 패스(2026-07-13 21:39~21:40 UTC, KST 7/14 06:39경) 카탈로그
      게시 확인** — 홍수일(7/8) 이후 최초 post-event 영상. 촬영→게시까지 실측
      약 4시간 걸림(오전 10:13 KST 확인 때는 게시 전이라 놓쳤었음, 10:43 게시).
- [x] **post-event GRD 다운로드 완료** (7/14 14:05~14:08) — 3개 신규:
      `93FC`/`3C22`/`1A5A` (`sentinel1_grd/`에 있음, 이 중 `3C22`·`1A5A`가 홍수
      AOI와 직접 겹침).
- [x] **post-event GRD RTC 완료** (7/14 14:08~15:54) — `93FC`(북한, AOI 무관)
      69.4분, `3C22`(AOI 겹침) 25.8분, `1A5A`(AOI 겹침) 10.5분. 뒤 두 개가 훨씬
      빠른 이유: 인접 pre-event 씬 처리 때 이미 Copernicus 30m DEM 타일이
      캐시돼 있었기 때문(93FC는 처음 다루는 위도대라 DEM을 새로 받음).
- [x] 모자이크 생성 — **단, `build_rtc_mosaic.py`가 아니라 `gdalbuildvrt`를
      직접 실행**했습니다. 이 스크립트는 `downloads/rtc`(SLC)만 읽도록
      하드코딩돼 있어 GRD(`downloads/rtc_grd`)는 지원하지 않기 때문
      (P5 항목 참고 — `--dir` 옵션 추가하면 스크립트로도 가능해짐). 대신
      P3의 NoData 버그 수정(`-srcnodata 0 -vrtnodata 0`)은 이번 명령에 반영
      해뒀습니다. 결과: `downloads/rtc_grd/s1_rtc_db_mosaic_20260713.vrt`
      (93FC 포함 3개 전부). 3C22·1A5A만 다시 묶고 싶으면 같은 명령에서
      93FC만 빼고 재실행.
- [ ] **post-event SLC는 보류 중** (사용자가 "다음에 하겠습니다"로 명시적으로
      미룸). 재개 시 대응 씬 ID: `S1C_IW_SLC__1SDV_20260713T213913..._41E9`,
      `..._213938..._64C0`, `..._214004..._04E2`. `conda run -n s1_pipeline
      python main_s1_list.py` (기존 파일은 자동 스킵) →
      `conda run -n s1_snappy python batch_slc_rtc.py`.

## P1.5 — 탐색적 분석: 북한 동일궤도(범위 밖, 필요 시에만)

93FC(7/13, 북한) footprint가 12일 주기 반복궤도라 7/1 씬(0FEB 등)과 바로 전/후
비교가 가능하다는 걸 발견해서 만들어둔 산출물들. **현재 프로젝트 핵심 범위
(충청권 홍수)는 아니므로 급하지 않음.**

- [x] 7/1·7/13 동일궤도 3프레임씩 날짜 모자이크 + 2밴드 스택 VRT + dB 차분
      계산 완료 (`downloads/rtc_grd/s1_rtc_db_diff_0701_vs_0713.tif`) — 평균
      +0.52dB, -3dB 이상 어두워진 픽셀 4.4%.
- [x] 같은 영역 HAND 22타일 다운로드 완료 (`downloads/hand/hand_north_orbit.vrt`).
- [ ] **차분 + HAND 결합해서 4.4%가 진짜 수체 변화인지 그림자/노이즈인지
      가려내기** — `build_baseline_water.py`의 `(dB 임계값) AND (HAND 임계값)`
      로직을 이 두 산출물에 재사용하면 됨. 다만 이건 baseline 4개 날짜 합집합이
      아니라 pre/post 각 1개 날짜 비교라 신뢰도는 낮음(스펙클 노이즈 영향 큼).

## P2 — 신규 침수 탐지 (핵심 목표 — ✅ 구현됨, 개선 항목만 남음)

- [x] **탐지 구현 완료** — `detect_flood.py` 계획은 `detect_flood_grd.py`(v1)
      → **`detect_flood_grd_v2.py`(현재 표준)**로 실현됨. dB<-16 + 하락폭
      -3dB(보수적)/무하락폭(느슨) 2단계, `--dates` 날짜 선택, post 씬 경계
      윈도우 최적화. 날짜별 결과는 [FLOOD_TIMELINE_KR.md](../flood/FLOOD_TIMELINE_KR.md).
- [ ] `260709_침수피해현황_v2.kmz`(공식 피해 현황)와 대조해 confusion matrix
      스크립트 작성 → 임계값(-16dB/-3dB) 튜닝 근거 확보.
- [ ] HAND 결합 옵션 — 현재 v2는 HAND 미사용(전국 확장 시 타일 부족).
      `hand_aoi.vrt`+`hand_north_orbit.vrt` 범위에서만이라도 `--hand` 옵션 추가
      하면 그림자 오탐 감소 기대.
- [ ] baseline 궤도 방향(ascending/descending) 혼합 이슈 — post와 같은
      relative orbit의 baseline만 비교하는 `--orbit` 옵션 고려
      (CODE_REVIEW_KR.md P3-2). 시간 변화 추적에는 필수적
      (동일궤도 쌍: 7/1↔7/13, 6/26↔7/8, 6/28↔7/10, 6/27↔7/16, 7/6↔7/18).

## P3 — 결과값 정확도에 영향 (코드 수정, 언제든 가능)

- [ ] `build_rtc_mosaic.py:62` — `gdalbuildvrt`에 `-srcnodata 0 -vrtnodata 0` 추가.
      현재 프레임 겹침 구간에서 위 프레임의 빈 영역(0)이 아래 프레임의 유효 dB를
      덮어써 baseline 커버리지가 실제보다 줄어드는 버그. 수정 후
      **기존 VRT·baseline 재생성 필요**. (7/14, GRD post-event 모자이크는
      `gdalbuildvrt`를 직접 실행하면서 이 옵션을 수동으로 넣었지만, 스크립트
      본체는 아직 안 고쳐서 SLC 쪽 기존 VRT 4개는 여전히 버그 있는 상태.)
- [ ] `download_hand.py:83-91` — HAND 타일 다운로드에 `.part` 임시파일 +
      Content-Length 검증 추가 (`stac/download_s1.py` 패턴 재사용). 현재는
      중간에 끊긴 손상 타일이 재실행 시 "이미 있음"으로 조용히 통과됨.
- [ ] `build_baseline_water.py:108` — `dst_crs=src.crs`가 "전부 EPSG:4326"이라는
      주석에만 의존. UTM 등 다른 CRS 입력이 섞이면 조용히 어긋나므로 assert 추가.

## P4 — 이식성 (다른 컴퓨터로 옮길 계획이 있다면 우선순위 높음)

- [ ] **(7/14 사고 기록)** `git filter-repo --invert-paths --path .env` 실행 중
      로컬 `.env`가 디스크에서도 삭제됨 — `.gitignore`에 있어도 "추적되던 파일"이
      히스토리 재작성으로 트리에서 사라지면 작업 트리 정리 과정에서 함께 지워짐.
      reflog도 filter-repo가 즉시 만료시켜 git으로 복구 불가했음. **앞으로 히스토리
      재작성(filter-repo, rebase, reset --hard 등) 전에는 `.env`류를 프로젝트 밖으로
      먼저 복사해둘 것.**
- [ ] `prepro_gpt.py:41`, `prepro_grd_gpt.py:36` — `SNAP_BIN = r"C:\Program
      Files\snap\bin"` 하드코딩. 다른 PC는 SNAP 설치 경로가 다를 수 있으므로
      `.env`의 `SNAP_BIN`으로 이동.
- [ ] 같은 파일들의 `-c 14G`(gpt 캐시), `-q 8`(스레드 수)도 `.env`의
      `GPT_CACHE`/`GPT_THREADS`로 이동 — 램 32GB 미만 PC에서는 `14G`가 과함.
- [ ] `config.py`의 `OutputConfig.out_dir`이 상대경로(`./downloads`)라 실행
      위치에 따라 결과 폴더가 바뀜. `Path(__file__).resolve().parent /
      "downloads"`로 통일.
- [ ] `environment.yml` / `environment_snappy.yml`에 버전 고정이 없음
      (`python=3.10`만 고정). `conda env export --no-builds`로 lock 파일을
      만들어두면 다른 컴퓨터에서 같은 환경 재현이 쉬움. SNAP 버전(예: 12.x)도
      README에 기록 권장.

## P5 — 구조 정리 (급하지 않음, 유지보수성)

- [ ] `main_s1_list.py` / `main_s1_list_grd.py` 통합 (`--product slc|grd` 인자).
      겸사겸사 "검색 AOI와 교차하는 후보는 위성/날짜와 무관하게 전부 포함" 옵션
      추가 — 현재 top-k 로직은 같은 패스의 일부 프레임이 우연히 탈락할 수 있음
      (실례: 7/14 재검증 중 발견한 `S1A..._BA53` 미다운로드, 다행히 AOI상 중복이라
      손실은 없었음).
- [ ] AOI/geojson 처리 함수 4곳 중복(`main_s1_list*.py`, `prepro_gpt.py`,
      `build_baseline_water.py`, `download_hand.py`) → `geoutil.py`로 통합.
      `AOI_MARGIN_DEG = 0.1`도 세 곳에 흩어져 있음 → 한 곳으로.
- [ ] `batch_slc_rtc.py` / `batch_grd_rtc.py` 러너 중복 → 공용 함수로 추출.
      실패 시 "AOI 미교차(정상)"와 "그 외 실패"를 로그에서 구분 (현재는 SNAP 로그를
      직접 열어봐야 구분 가능).
- [ ] `stac/check_kml_dam_korea.py`, `stac/batch_check_kml_dams.py` — 이 저장소와
      무관한 K-water 댐 스크립트(하드코딩된 `E:\` 경로 포함). 별도 저장소로 이동.
- [ ] 정리 대상 파일: `downloads/rtc_grd`의 DEM 비교 실험 산출물(`*_dem_diff.tif`
      등 4개) → `experiments/` 하위로, 2022 Jeddah SLC(11GB) → 별도 보관,
      `output_partitioned_stac/`(출처 불명, 524KB) → 문서화 또는 삭제,
      `downloads/s1_frames_report_GRD.qmd` → 구버전 잔재, 삭제 권장
      (`s1_frames_report_GRD.geojson`은 7/14에 재생성해서 최신 상태 — 삭제 대상
      아님, 다만 export_frames_geojson.py에는 아직 GRD 전용 옵션이 없어 별도
      스크립트로 만듦. `export_frames_geojson.py`에 `--product grd|slc|all`
      옵션을 추가하면 이 별도 스크립트가 필요 없어짐).
- [ ] 최소 단위 테스트 추가: `stac/models.py`의 `parse_target_datetime_utc`,
      `make_datetime_range`; `stac/search_s1.py`의 `extract_product_id`;
      `prepro_gpt.py`의 `_iter_lonlat`/`aoi_wkt_from_geojson`.
- [ ] `print` 기반 로깅을 `logging` + 파일 핸들러(`downloads/logs/`)로 전환.

## 완료된 것 (참고용, 재작업 불필요)

- [x] GRD 검색·다운로드·RTC 파이프라인 전체 (14/14, 14/14)
- [x] SLC 검색·다운로드 전체 (14/14, EBE9 포함)
- [x] SLC RTC — 홍수 AOI 교차 씬 6/6 (나머지 8개는 AOI 밖이라 처리 대상 아님, 버그 아님)
- [x] HAND 다운로드, NGII DEM 클립, pre-event baseline 수체 지도
- [x] `.env` git 히스토리 세척 + force push (단, 비밀번호/키 자체 변경은 P0 참고)
- [x] git upstream 추적 연결(`git branch --set-upstream-to=origin/main main`)
- [x] post-event GRD 다운로드 + RTC + 모자이크 (3/3, 7/14 완료)
- [x] `s1_frames_report_GRD.geojson` 재생성 (7/14, 17개 프레임 반영)
- [x] GRD pre-event 날짜 모자이크 5종 + GRD baseline (`build_baseline_water_grd.py`,
      홍수 AOI, dB+HAND 합집합 — 7/14)
- [x] 남한 전역 최신관측 baseline (`build_baseline_latest_grd.py`, dB만·HAND 미사용·
      최근 영상 우선 — 7/14). detect_flood에서 post GRD와 비교할 기준 완비.
- [x] speckle 필터 비교(SNAP 4종 vs `filtering/` 자체구현) + `qa/` 4축 정량 평가
      패키지 커밋 (7/15, [FILTER_COMPARISON_KR.md](../pipeline/FILTER_COMPARISON_KR.md))
- [x] 재현 가능한 baseline 빌더 `build_baseline_composite_grd.py` (7/15)
- [x] 신규침수 탐지 v1/v2 + 전범위 확장 + 핫스팟/남북 분리 도구 (7/15~16,
      [FLOOD_DETECTION_KR.md](../flood/FLOOD_DETECTION_KR.md))
- [x] 한반도 전체 GRD 44씬 추가 수집 + SLC 원본 D: 이동(junction) (7/19)
- [x] baseline v2 재구축(pre-event 신규 17프레임 반영) + 7/8~7/16 날짜별
      침수 시간선 분석 (7/20, [FLOOD_TIMELINE_KR.md](../flood/FLOOD_TIMELINE_KR.md))
