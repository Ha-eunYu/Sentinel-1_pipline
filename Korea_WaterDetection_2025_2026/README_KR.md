# 남한 4대강 수면적 · 댐 저수량 비교 (2025 vs 2026)

> **이 폴더는 스냅샷이다.** 활성 개발은
> `F:/06_SAR_system/gee/Korea_WaterDetection_2025_2026/`에서 진행 중이며 이
> 문서는 그 시작 시점 사본이라 이후 갱신되지 않는다. 진행 경과는
> [worklog.md](worklog.md) 참고.

경상·전라 가뭄 확인을 위해, 한강을 제외한 4대강(낙동강·섬진강·영산강·금강)의
**하천 수면적**과 **댐 저수량**을 작년 동기(2025-07)와 올해(2026-07) 비교한다.
지시사항 원문·배경은 [박사님 요청사항.md](박사님%20요청사항.md).

- 배경: [gee/](../../gee) 북한 홍수 산정 모듈과 같은 GEE 기반 접근이지만
  **변화탐지가 아니라 스냅샷 비교**라서 별도 자체완결 패키지로 새로 만듦
  (이유는 아래 §2).

---

## 1. 진행 방식 결정 (박사님 노트의 열린 질문에 대한 답)

| 질문 | 결론 |
|---|---|
| GEE로 해야 하나, 로컬(snappy/sarsen)이랑 다른가 | **GEE**. 필요한 건 딱 두 시점(작년 7월/올해 7월) 비교라, GEE의 강점(다운로드 불필요, 필터만 교체)이 그대로 적용됨. GEE는 지형보정까지는 이미 처리·γ⁰(RTC)는 근사치라 로컬과 완전 동일친 않지만, 수면적 상대비교엔 오차범위 안(`../gee/README.md` §4 비교표 참고). |
| 1년치 로컬 처리 가능한가 | **불필요**. 연속 시계열이 아니라 스냅샷 2장만 있으면 됨 — 데이터량 걱정 자체가 해당 없음. |
| 한강도 챙겨야 하나 | 사용자 확인대로 S1 패스가 한강도 지나가므로 커버리지 문제 없음. 다만 박사님 지시는 4대강(한강 제외) 우선. |
| water detection을 어떻게 정리해서 진행하나 | 이 폴더의 `watercompare/` 패키지로. §2, §4 참고. |

---

## 2. 수면적(area) ≠ 저수량(volume) — 중요한 구분

S1 SAR에서 바로 나오는 값은 **수면 면적(km²)** 뿐이다. 댐의 **저수량(m³)**은
수위–면적–용적 관계(rating curve/bathymetry)가 있어야 계산되고, SAR 단독으로는
산정 불가능하다.

- **하천 수면적**(낙동강 등 4대강 본류): SAR 수면적 비교로 충분히 의미 있음 →
  이번 스캐폴딩 대상.
- **댐 저수량**: 박사님이 주실 댐 리스트 도착 후, 그 댐들에 대해
  1) 공식 저수율 데이터(K-water 등)를 확보할 수 있는지 먼저 확인,
  2) 확보 불가한 댐만 SAR 수면적을 저수량의 **프록시**로 검토.
  → 리스트 없이 미리 코드화하지 않음(TODO, §6).

---

## 3. 폴더 구조

```text
Korea_WaterDetection_2025_2026/
├── watercompare/              # ★ 처리 로직 단일 소스(패키지)
│   ├── __init__.py
│   ├── config.py              #   BASINS(4대강 bbox)·PERIODS·기본 파라미터·DAMS(빈 상태)
│   ├── auth.py                #   Earth Engine 초기화
│   ├── water.py                #   S1 수면 마스크(Otsu, 상시수체 유지) + 면적(km2)
│   └── export.py              #   GeoJSON 내보내기
├── river_water_area.py        # CLI: 4대강 × (올해/작년) 수면적 비교 표 + CSV
├── output/                    # 실행 결과(CSV/GeoJSON) — 실행 후 생성
├── 박사님 요청사항.md          # 원 지시사항 + 사용자 메모
└── README_KR.md               # 이 문서
```

### `gee/geeflood`와의 차이
| | `gee/geeflood`(북한 홍수) | `watercompare`(4대강 가뭄) |
|---|---|---|
| 목적 | before/after **변화탐지**(신규 침수만) | 시점별 **절대 수면적** 스냅샷 |
| 상시수체(JRC) | 제외(변화만 보려고) | **유지**(하천·저수지 자체가 측정 대상) |
| Otsu 대상 | after − before 차분 히스토그램 | 원본 후방산란 히스토그램 |
| 피해지표(토지피복/인구/침수심) | 있음 | 불필요(수면적만) |

두 패키지는 **의도적으로 코드 공유 안 함**(cross-import 없음) — `geeflood`가
`F:/GEE` 독립 프로젝트로 분리될 예정이라 부모 폴더 의존을 만들지 않기 위함.
Otsu·load_s1 로직은 작은 함수라 복사가 더 안전(각자 폴더 상대로만 동작).

---

## 4. 빠른 시작

```bash
conda activate sar-gee          # gee/environment.yml과 동일 env 재사용
python river_water_area.py                  # 4대강 전체 표 + CSV
python river_water_area.py --basin nakdong   # 낙동강만
python river_water_area.py --download        # 시점별 수면 GeoJSON도 저장
```

---

## 5. 확인됨 — 실행 시 계정 등록 이슈 (P0, 미해결)

`sar-gee` conda env의 `earthengine authenticate` 토큰은 캐시돼 있으나(2026-07-28),
현재 로그인된 GCP 프로젝트가 **Earth Engine에 미등록**이라 `ee.Initialize()`에서
403(`Not signed up for Earth Engine or project is not registered`)이 남
(2026-07-29 `watercompare` 실행 테스트로 재확인). `gee/todo.md`의 기존 P0
"실 GEE 계정으로 실행 검증" 항목과 동일한 원인 — `gee/`쪽도 아직 미해결 상태다.

해결 필요(사용자/박사님 액션):
1. https://developers.google.com/earth-engine/guides/access 에서 사용할
   GCP 프로젝트를 Earth Engine에 등록, 또는
2. 이미 등록된 프로젝트가 있다면 `EE_PROJECT` 환경변수로 지정 후 재실행.

등록 전까지 `water_mask`/`area_km2` 계산 로직은 **문법·구조만 검증됨**(실제 GEE
응답값 미검증).

---

## 6. TODO

- [ ] **P0 — EE 프로젝트 등록**(§5). 이거 없으면 아무 것도 못 돌림.
- [ ] **4대강 AOI 실경계 교체** — 현재 `config.BASINS`는 대략 bbox(내 지리 지식
      기반 근사치, 실측 아님). 정식 보고 전 환경부 표준유역도/K-water 유역경계
      또는 GEE WWF/HydroSHEDS BasinATLAS로 교체.
- [ ] **관측일 확정** — 올해 7월 최신 S1 장면 가용일에 맞춰 `PERIODS["this_year"]`
      좁히기(구름 무관하지만 궤도 주기 12일 고려).
- [ ] **궤도(ASC/DESC) 커버리지 확인** — `config.DEFAULTS["orbit"]`이 4대강 전
      유역에서 실제로 커버되는지, 유역별로 다르면 비교 왜곡되므로 개별 확인/고정.
- [ ] **댐 리스트 수신 후** — §2 방침대로 공식 저수율 데이터 확보 여부부터 확인,
      이후 `dam_storage.py`(가칭) 설계.
