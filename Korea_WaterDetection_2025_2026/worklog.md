# 작업 이력 (worklog)

이 폴더는 **스냅샷/팔로업용**이다. 활성 개발은
`F:/06_SAR_system/gee/Korea_WaterDetection_2025_2026/`에서 진행 중이며, 여기
파일들은 그 시작 시점의 사본으로 더는 동시수정하지 않는다(이유는 §2026-07-29
후반부). 원 지시사항은 [박사님 요청사항.md](박사님%20요청사항.md).

---

## 2026-07-29

### 배경·지시사항
손찬영 박사님 지시: 경상·전라 가뭄이 심함 → 한반도 전체를 4대강(한강 제외:
낙동강·섬진강·영산강·금강)으로 나눠 **하천 수면적**과 **댐 저수량**(특정 댐
리스트 추후 제공)을 확인. 평면(전체 시계열)은 확인에 너무 오래 걸리므로
**작년 동기(2025-07) vs 올해(2026-07) 스냅샷 비교**로 진행.

### 열린 질문 검토·결론
사용자가 남긴 메모(GEE로 해야 하는지/snappy와 다른지, 1년치 로컬 처리 가능한지,
water detection을 어떻게 진행할지)에 대해 기존 `gee/geeflood`(북한 홍수 산정
모듈) 경험을 바탕으로 답변:
- **GEE 채택**. 시계열이 아니라 스냅샷 2장 비교라 GEE의 "다운로드 불필요·필터만
  교체" 강점이 그대로 적용됨. 1년치 로컬 처리 자체가 불필요.
- 한강도 S1 패스 커버리지엔 문제없음(사용자 확인).
- **수면적(area) ≠ 저수량(volume)** 임을 명확히 함 — SAR로는 수면적(km²)만
  나오고, 저수량(m³)은 수위-면적-용적 관계(rating curve)가 있어야 계산되므로
  SAR 단독 산정 불가. 댐 리스트 도착 전까지 저수량 부분은 코드화하지 않기로 함.

### 스캐폴딩 (최초, 이 폴더에서)
`watercompare/` 패키지 신설:
- `config.py` — BASINS(4대강 대략 bbox)·PERIODS(올해/작년 7월)·DEFAULTS·
  DAMS(빈 상태, 리스트 대기).
- `auth.py` — Earth Engine 초기화(geeflood.auth와 동일 로직 독립 사본).
- `water.py` — S1 수면 마스크. **geeflood.sar.detect_flood와 핵심 차이**:
  before/after 차분이 아니라 **한 시점의 후방산란을 그대로 Otsu 이진화**하고,
  JRC 상시수체를 **제외하지 않음**(하천·저수지 자체가 측정 대상이므로 — 홍수
  변화탐지와 반대).
- `export.py` — GeoJSON 내보내기.
- CLI `river_water_area.py` — 4대강 × (올해/작년) 수면적·증감(km², %) 표+CSV.

`gee/geeflood`와 **cross-import 하지 않음**(각자 폴더 상대로만 동작) — geeflood가
향후 `F:/GEE` 독립 프로젝트로 분리될 예정이라 부모 의존을 만들지 않기 위함. 작은
함수(otsu·load_s1)라 복사가 더 안전하다고 판단.

### 실행 검증 → P0 블로커 발견
`F:/envs/sar-gee` conda env로 `py_compile` 통과 확인 후, 실제 EE 실행 테스트
(`auth.init_ee()` → `watercompare.water.water_mask()`)를 시도. `earthengine
authenticate` 토큰은 캐시돼 있었으나, 로그인된 GCP 프로젝트가 **Earth Engine에
미등록**이라 403(`Not signed up for Earth Engine or project is not
registered`) 확인. `gee/todo.md`에 이미 있던 P0 "실 GEE 계정으로 실행 검증"
항목과 동일 원인 — `geeflood`도 같은 이유로 아직 실행 미검증 상태였음. 해결은
사용자가 GCP 프로젝트를 EE에 등록하거나 `EE_PROJECT` 환경변수를 등록된
프로젝트로 지정해야 함(대신 풀 수 없는 부분).

### 활성 개발 위치 이전
사용자 결정: `F:/06_SAR_system/gee`(geeflood v2가 이미 병합·정착된 "진짜 활성
프로젝트 폴더")로 옮겨서 진행. `F:/06_SAR_system/gee`는 git 관리가 전혀 없는
폴더라, S1(실제 git 저장소)의 이 사본이 유일한 백업/이력 역할.

1차 시도: `watercompare/`·`river_water_area.py`·`박사님 요청사항.md`를
`gee/` **최상위**에 바로 복사, `README_KR.md`→`WATER_AREA_KR.md`로 이름 바꿔
경로 참조 수정, `gee/README.md`·`gee/todo.md`에 교차링크 추가.

**사용자 정정**: 원래 의도는 `gee/` 최상위가 아니라
`gee/Korea_WaterDetection_2025_2026/` **하위 폴더**로 복사하는 것이었음. 재작업:
- `gee/`에 flat으로 있던 4개 항목을 `gee/Korea_WaterDetection_2025_2026/`으로
  이동.
- `WATER_AREA_KR.md`의 상대경로 링크를 한 단계 깊어진 위치에 맞게 재수정
  (`geeflood/`→`../geeflood/`, `README.md`→`../README.md`,
  `todo.md`→`../todo.md`), 폴더 구조 다이어그램·빠른 시작 안내도 갱신.
- `gee/README.md`·`gee/todo.md`의 링크도 `Korea_WaterDetection_2025_2026/` 경로로
  재수정.
- 최종 위치에서 `py_compile` 재검증 통과.

**최종 상태**: 활성 소스 = `F:/06_SAR_system/gee/Korea_WaterDetection_2025_2026/`.
이 S1 폴더는 스냅샷으로 고정, 이후 동시수정 안 함.

---

## 남은 TODO (활성 소스 쪽 `WATER_AREA_KR.md` §6과 동일)

- [ ] **P0 — EE 프로젝트 등록**. 이거 없으면 아무것도 못 돌림.
- [ ] 4대강 AOI 실경계 교체(현재는 대략 bbox, 실측 아님).
- [ ] 관측일(올해 7월 최신 S1 가용일) 확정.
- [ ] 궤도(ASC/DESC) 커버리지 유역별 확인.
- [ ] 댐 리스트 수신 후 저수량 모듈 설계(공식 저수율 데이터 확보 여부부터 확인).
