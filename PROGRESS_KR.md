# 작업 진행 현황 (2026-07-20 기준)

2026년 7월 한국 홍수(홍수일 7/8) 모니터링 파이프라인의 작업 이력·데이터
인벤토리·다음 할 일 정리. 분석 범위는 충청권 AOI에서 **한반도 전체(북한
포함)**로 확장됐습니다. 파이프라인 사용법은 [README_KR.md](README_KR.md) 참고.

## 한눈에 보기

| 단계 | 상태 |
| --- | --- |
| GRD 검색·다운로드 (한반도 전체 73씬 + 7/19 2씬) | ✅ 완료 (7/19 2씬은 다운로드 중) |
| GRD RTC | 🔄 57+/73 배치 진행 중 (완료 예상: 7/20 밤~7/21) |
| SLC 검색·다운로드 (14씬) | ✅ 완료 — **원본은 D:로 이동**(junction 연결) |
| SLC RTC (AOI 교차 6씬) | ✅ 완료 — 나머지 8씬은 AOI 미교차로 대상 아님 |
| post-event SLC | ⬜ 보류 (사용자 요청) |
| baseline (pre-event, 컷오프 7/3) | ✅ v2 재구축 완료 (7/20) — 배치 후 v3 최종판 예정 |
| **신규 침수 탐지** | ✅ **구현·운용 중** (`detect_flood_grd_v2.py`) — 7/8·7/10·7/13·7/14·7/15·7/16 완료 |
| 침수 시간선 분석 | ✅ [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md) — 7/8 당일 검출, 7/14~15 최대 154.4km²(남한) |
| speckle 필터 QA | ✅ [FILTER_COMPARISON_KR.md](FILTER_COMPARISON_KR.md) + `filtering/`·`qa/` 패키지 |

## 데이터 인벤토리 (`downloads/`)

- `sentinel1/` — SLC 원본 14개 (2026년 씬) + 2022 Jeddah 참조 1개
  - 6/25 S1A ×1, 6/26 S1C ×4, 7/1 S1C ×3, 7/2 S1D ×2, 7/3 S1C ×3, EBE9(북한 쪽) ×1
- `sentinel1_grd/` — GRD(COG) 원본 17개: pre-event 14개(6/25 ×2, 6/26 ×4, 7/1 ×3,
  7/2 ×2, 7/3 ×3) + **post-event 3개(7/13 21:39~21:40 UTC S1C, 신규)**
- `rtc/` — SLC RTC dB 6개 + 날짜별 모자이크 VRT (0625/0626/0701/0702)
- `rtc_grd/` — GRD RTC dB pre-event 14개 + post-event 3개(7/14 완료) + NGII/
  Copernicus DEM 비교 실험 산출물(5469 씬) + `s1_rtc_db_mosaic_20260713.vrt`
  (post-event 모자이크, `gdalbuildvrt` 직접 실행으로 생성 — 아래 7/14 항목 참고)
- `hand/` — GLO-30 HAND 타일: 홍수 AOI용 4장(N35–36/E126–127) + `hand_aoi.vrt`,
  **북한 동일궤도 스와스용 22장(N34–39/E123–127, 7/14 추가) + `hand_north_orbit.vrt`**
- `dem/` — NGII 5m DEM AOI 클립 (`ngii_5m_aoi.tif`)
- `water/` — SLC 기준: 날짜별 마스크 4개(0625/0626/0701/0702),
  `baseline_water_union.tif`, `water_frequency.tif`, `observed_count.tif`.
  **GRD 기준(7/14 추가)**: `*_water_mask_grd.tif` ×5, `baseline_water_union_grd.tif`,
  `water_frequency_grd.tif`, `observed_count_grd.tif` (홍수 AOI, dB+HAND 합집합),
  `baseline_water_latest_grd.tif` (남한 전역, dB만·최신 관측 우선)
- 매니페스트: `s1_stac_list_manifest.json`(SLC), `s1_stac_list_manifest_grd.json`(GRD)
  — 구버전이라 top-k 후보만 기록되어 실제 다운로드 목록과 일부 차이 있음
- 프레임 현황: `s1_frames_report.geojson` / `s1_frames_report_GRD.geojson` (QGIS용)

## 작업 이력

### ~7/9: 초기 구축 (git 이력 참고)

- CDSE STAC 검색·다운로드 파이프라인 (SLC/GRD 분리, 이어받기·토큰 자동갱신)
- snapista/gpt 기반 RTC 전처리 + 배치 러너 (SLC는 AOI 서브셋, GRD는 전체 씬)
- HAND 다운로드, NGII 5m vs Copernicus 30m DEM 비교, 날짜별 모자이크, 프레임 보고
- pre-event 4개 날짜로 기준(평상시) 수체 지도 생성 (dB < -16 AND HAND < 10m)

### 7/13 (오늘)

1. **EBE9 SLC 다운로드 완료** — 오전에 3.1GB에서 끊겨 있던
   `S1C_IW_SLC__1SDV_20260626T213052..._EBE9.zip`을 재개. STAC에서 product UUID를
   조회해 `download.dataspace.copernicus.eu` OData URL로 받았는데, **이 엔드포인트가
   Range 요청을 무시해 처음부터 전체 재다운로드**됨 (7.38GB 완료, `.part` 소멸).
   이 씬은 위도 38.25°~40.28° 북한 쪽 프레임이라 RTC 대상은 아님 (세트 완성 목적).
2. **SLC RTC 배치 재실행 및 검증** — `batch_slc_rtc.py` 결과: 성공 0 / 건너뜀 6 /
   실패 6. 실패 6건의 SNAP 로그를 확인하니 전부
   `SubsetOp: No intersection with source product boundary` → Multilook의
   "Input should be a SAR product" 에러로, **AOI 미교차 씬의 정상 스킵 동작**임을
   확인. STAC footprint를 홍수 AOI bbox(126.61~127.39E, 35.91~36.72N)와 대조해
   교차 없음을 재확인:
   - 7/3 패스 3개(D560, 43D6, 8105): 경도 127.7°E 동쪽 swath — AOI 완전 이탈
   - 0C58(36.76°N~), 7AB0(~35.80°N), 65DC(37.87°N~): 남북 인접 프레임, 경계 밖
   - **결론: AOI 교차 SLC는 6개가 전부이며 모두 RTC 완료. 추가 처리 불필요.**
   - 7/2 `29B8_rtc_db.tif`가 11MB로 작은 것도 AOI 남단만 걸친 정상 결과.
3. **신규 촬영 조회** — CDSE STAC 직접 조회(7/4~7/13, 본토 bbox): GRD·SLC 모두
   **0건**. 광역 bbox로는 8프레임이 있으나 전부 동해/서해/제주 남쪽 해상·북한 쪽.
4. **미촬영 원인 규명**:
   - **S1A: 2026-06-29 임무 종료(퇴역)** — 촬영계획도 6/30에서 끝남. 6/25 씬이
     이 지역 마지막 S1A 촬영. 이후 S1C+S1D 2기 체제.
     ([ESA 공지](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1/Time_to_say_goodbye_to_Sentinel-1A))
   - **S1C 7/8 반복 미촬영: 관측계획 공백** — 계획 KML
     (`s1c_mp_user_20260702t172028_20260722t194000`) 파싱 결과 7/8 저녁 datatake가
     21:15 UTC에 끝나고 21:37:51 UTC(필리핀 부근)에서 재개 — 한국 통과(~21:31 UTC)가
     공백 구간. 퇴역 전후 궤도 재배치로 12일 주기가 매번 보장되지 않는 시기.
5. **다음 촬영 확정 (계획 KML 검증)**:
   - **7/13 21:28:47~21:40:27 UTC** (KST 7/14 새벽 ~06:39) — S1C 하강, 한반도 포함
   - **7/14 09:30:31~09:31:27 UTC** (KST 7/14 18:30) — S1D 상승, 계획 폴리곤
     [125.2~128.7E, 33.8~37.6N]이 **홍수 AOI 정확히 커버** → **최초 post-event 영상**
   - 7/15 21:23 UTC 반복(동부 swath)은 계획에 없음 (AOI 미교차 궤도라 영향 없음)
6. README_KR.md에 데이터 현황·위성 운영 상황·계획 KML 확인법 반영, 본 문서 작성.

### 7/14 (오늘)

1. **전체 파이프라인 코드 리뷰 갱신** — [CODE_REVIEW_KR.md](CODE_REVIEW_KR.md) 전면
   재작성(7/13 리뷰 이후 코드 자체는 안 바뀌었음을 확인, P0는 히스토리 세척으로
   해결 처리하되 비밀번호/키 변경은 잔여 항목으로 분리), [TODO_KR.md](TODO_KR.md)
   신규 작성(다른 컴퓨터에서 이어받을 수 있는 P0~P5 체크리스트).
2. **`.env` 사고**: `git filter-repo`로 `.env`를 히스토리에서 제거하는 과정에서
   **로컬 디스크의 실제 `.env` 파일까지 함께 삭제됨** (filter-repo가 재작성된
   HEAD로 작업 트리를 정리하면서, 더 이상 트리에 없는 추적 파일을 지움 + reflog까지
   즉시 만료시켜 git으로 복구 불가). 사용자가 직접 `.env`를 새로 생성해 복구
   (12:24). **교훈: 히스토리를 재작성하는 git 작업 전에는 `.gitignore`된 파일이라도
   먼저 별도 위치에 백업할 것** — TODO_KR.md에 반영 필요.
3. **신규 촬영 확인**: CDSE STAC 재조회 결과 South_Korea 교차 건수가 GRD/SLC 각각
   14→17개로 증가. 어제 계획 KML로 예측했던 **S1C 하강 패스(7/13 21:39~21:40
   UTC)가 실제로 게시됨** — 홍수일(7/8) 이후 **최초 post-event 영상**. GRD 3개
   (93FC/3C22/1A5A), SLC 3개(41E9/64C0/04E2) 대응하는 프레임 확인. 이 중 3C22·1A5A가
   홍수 AOI(126.61~127.39E, 35.91~36.72N)와 직접 겹침.
   - STAC 아이템의 `created`/`updated`/`published` 필드로 게시 지연을 정량 확인:
     촬영(21:39:40 UTC) → 처리완료(23:40:13 UTC, +2h) → 게시(익일 01:43:30 UTC,
     **촬영 후 약 4시간**). 오전 10:13 KST 확인 때는 아직 게시 전(게시는 10:43
     KST)이라 놓쳤던 것으로 확인 — 지연이나 버그가 아니라 확인 타이밍 문제였음.
4. **post-event GRD 다운로드 + RTC + 모자이크 완료**: 사용자 요청으로 GRD만
   우선 진행(SLC는 보류). `main_s1_list_grd.py` 재실행 → 3개 다운로드
   완료(14:05~14:08). `batch_grd_rtc.py` 실행 결과(씬당 소요시간, 완료 타임
   스탬프 기준):
   - `93FC`(북한, AOI 무관) 69.4분 — 이 위도대는 처음 처리하는 거라 Copernicus
     30m DEM 타일을 새로 받느라 오래 걸림
   - `3C22`(AOI 겹침) 25.8분, `1A5A`(AOI 겹침) 10.5분 — 인접 pre-event 씬
     처리 때 이미 DEM이 캐시돼 있어서 훨씬 빠름
   - 모자이크는 `build_rtc_mosaic.py`가 GRD를 지원하지 않아(`downloads/rtc`
     SLC 전용 하드코딩) **`gdalbuildvrt`를 직접 실행**해서 생성, 이때 CODE_REVIEW
     P1-1(VRT NoData 미지정 버그)의 수정(`-srcnodata 0 -vrtnodata 0`)을 반영함
     → `downloads/rtc_grd/s1_rtc_db_mosaic_20260713.vrt`
5. **93FC(북한) footprint의 과거 촬영 이력 조회**: 사용자가 "93FC 이전 영상"을
   요청해 STAC 조회 — 같은 relative orbit이 5월부터 12일 주기로 반복 촬영됨을
   확인. 그중 **7/1 씬(0FEB)이 이미 이 프로젝트에서 RTC까지 처리돼 있어**,
   원하면 93FC와 바로 전/후 비교 가능(단, 현재 프로젝트 범위 밖이라 보류).
6. **`s1_frames_report_GRD.geojson` 재생성**: `export_frames_geojson.py`가
   SLC+GRD 통합본만 만들도록 돼 있어(GRD 단독 옵션 없음), 그 함수들을 재사용하는
   일회성 스크립트로 GRD 17개 프레임 전체를 반영해 재생성. `downloads/`에 저장.
7. **RAM 증설 요청 근거 문서 작성**: 홍수 파이프라인과는 무관한 별도 요청 —
   `f:\06_SAR_system\S1\RAM_증설_요청_근거.md`. 오늘 GRD RTC 처리 중 실측한
   리소스 수치(RAM 32GB 중 씬 1개가 18.49GB 단독 사용, 여유 RAM 3.7GB까지 감소,
   CPU는 8스레드로 이미 최대 활용 중 등) 근거로 정리. git에는 미포함(개인 문서).
8. **동일궤도(93FC 위치) 전/후 비교 VRT 3종 생성**: 사용자 요청으로 7/1(pre,
   0FEB/EC8B/8E98)과 7/13(post, 93FC/3C22/1A5A) 같은 relative orbit 프레임을
   비교용으로 묶음.
   - `downloads/rtc_grd/s1_rtc_db_mosaic_20260701_sameorbit.vrt` — 7/1 세 프레임
     날짜 모자이크 (신규 생성, `build_rtc_mosaic.py`가 GRD 미지원이라 이번에도
     `gdalbuildvrt` 직접 실행 + NoData 옵션 반영)
   - `s1_rtc_db_same_orbit_0701_vs_0713.vrt` — 위 7/1 모자이크와 기존 7/13
     모자이크를 밴드 1(pre)·밴드 2(post)로 쌓은 2밴드 VRT (`-separate`)
   - `s1_rtc_db_diff_0701_vs_0713.tif` — 밴드2−밴드1 dB 차분 (rasterio 스크립트,
     2.4GB). **결과**: 유효 픽셀 약 6.67억 개, 평균 +0.52dB(표준편차 2.21dB,
     노이즈 수준), **-3dB 이상 어두워진 픽셀 4.4%** — 국지적 수체 증가
     가능성이 있으나 이 지역엔 HAND가 없어 레이더 그림자 등 오탐과 구분 불가
     (첫 시도에서 `profile`을 VRT에서 그대로 복사해 driver가 GTiff로 안 바뀌는
     버그로 한 번 실패, `driver="GTiff"` 명시로 수정 후 성공).
9. **북한 동일궤도 스와스 HAND 다운로드**: 위 4.4% 판정을 검증하기 위해
   `download_hand.py`와 같은 로직(`.part`+Content-Length 검증 포함)의 일회성
   스크립트로 93FC/3C22/1A5A 합친 bbox(+0.1도, lon 123.64~127.76, lat
   34.89~39.92)를 커버하는 타일 30개 후보 중 **22개 다운로드**(8개는 서해
   바다라 HTTP 404) → `downloads/hand/hand_north_orbit.vrt`. 기존
   `hand_aoi.vrt`(홍수 AOI용)는 건드리지 않음.
10. **GRD 날짜 모자이크 5종 + GRD 기준 baseline 생성**
    (`build_baseline_water_grd.py` 신규): pre-event 5개 날짜(6/25~7/3) GRD
    모자이크를 만들고(NoData 옵션 반영), SLC baseline과 같은 로직(dB<-16 AND
    HAND<10m, 합집합)을 홍수 AOI에 적용. 산출물은 `_grd` 접미사로 분리.
    결과: baseline 합집합 277.60 km², 상시 수체 131.19 km². 7/3은 AOI 밖
    (동부 swath)이라 커버리지 0%로 기여 없음 — 실질 4개 날짜.
11. **남한 전역 "최신 관측 우선" baseline 생성**
    (`build_baseline_latest_grd.py` 신규, 사용자 요청 사양): 대상을 South_Korea
    bbox(+0.1도)로 확장, **HAND 미사용(dB<-16 단독)**, 중첩 구간은 합집합이
    아니라 **가장 최근 촬영 픽셀 우선**(날짜 오름차순 gdalbuildvrt 합성 →
    `rtc_grd/s1_rtc_db_composite_latest_pre.vrt`, 나중 파일이 이기는 성질 이용).
    남한 전역에서는 7/3 동부 swath도 동해안에 실제 기여. 약 35,900×48,400px를
    블록 단위로 처리. 결과: 커버리지 79.7%, 수체 판정 1,869 km²(**바다·그림자
    오탐 포함 값** — 육지 통계는 South_Korea 폴리곤 클립 후 재계산 필요).
    산출물: `water/baseline_water_latest_grd.tif`.

### 7/15 — speckle 필터 비교 + 재현 가능 baseline + 침수탐지 v1

1. **SNAP 필터 4종 비교**(multilook-only/Refined Lee/Lee/Frost, 1A5A 씬) 및
   `filtering/`(자체 필터 6종)·`qa/`(4축 정량 QA) 패키지와 교차 검증 —
   윈도우를 맞추면 자체 구현이 SNAP을 5~9% 이내로 재현. 상세:
   [FILTER_COMPARISON_KR.md](FILTER_COMPARISON_KR.md) (커밋 `8792291`).
2. **`build_baseline_composite_grd.py` 신규** — 수동 gdalbuildvrt로 만들던
   pre-event "최신 관측 우선" 합성을 전 과정 스크립트화 (커밋 `96fd7b8`).
3. **`detect_flood_grd.py`(v1) 신규** — 7/13 3프레임 vs baseline, 3중 AND
   보수적 판정. 홍수 AOI 기준 신규침수 6.48km² — 커버리지 35% 한계 확인.
4. 신규 GRD 3씬(FE43/8EF1/B126) 다운로드+RTC.

### 7/16 — 전범위 확장 + 핫스팟/남북 분리

1. **`detect_flood_grd_v2.py` 신규** — 7/13+14 6프레임, 픽셀별 최솟값 채택,
   보수적/느슨 2단계 (커밋 `7420efd`). 이후 **AOI 클리핑 제거**: 분석 범위를
   baseline 전체 커버리지로 확장(사용자 방침: "위성영상이 확보되는 모든 지역").
   전범위 신규침수(보수적) 243.54km² — 남한 164.05 / 북한 79.49 (커밋 `6c09cb6`).
2. **`flood_hotspots.py`·`split_flood_area_nk_sk.py` 신규** — 2km 격자 핫스팟
   GeoJSON + 위도 기준 남/북 분리. 남한 핫스팟: 김제/부안, 논산~부여(금강),
   대전/옥천, 당진/서산, 천안/아산, 인천/강화, 평택/화성.
   [FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md) 작성.
3. 7/14만 단독 재분석(`--dates` 옵션 추가), 7/15 신규 5씬·7/16 3씬 다운로드+RTC.

### 7/19 — 한반도 전체(북한 포함) 일괄 수집

1. **수집 범위 확장**: `Korea_Peninsula.geojson` bbox(124.18~130.67E,
   33.11~43.00N)로 6/25~7/18 재검색 → 총 71씬 중 신규 44씬 식별.
2. **디스크 확보**: F: 여유 35GB뿐 → SLC 원본 103GB(14파일)를
   `D:\06_SAR_system_archive\sentinel1`로 robocopy /MOVE 이동 후 기존 경로에
   **junction** 생성(스크립트 무수정 동작). 재생성 가능한 중간산출물
   (전범위 diff 5.5GB, 필터비교 tif 3개) 삭제 → 여유 143GB 확보.
3. 44씬 일괄 다운로드(~45GB, 전량 성공) → `batch_grd_rtc.py` 배치 시작
   (73씬 중 신규 44씬 대상, 씬당 17~85분).

### 7/20 — baseline v2 재구축 + 침수 시간선 완성

1. **날짜별 침수 탐지 확장**: RTC가 끝난 날짜부터 순차 분석. 7/13(128.42km²),
   7/14(177.02km²), 7/15(84.79km²), 7/16(0% — baseline 미커버로 비교 불가) 확인.
2. **7/8·7/10·7/11이 "비교 불가"였던 원인 규명**: 다른 궤도(동해안/서해) 프레임
   인데 그 궤도의 pre-event가 baseline v1에 없었음. 밤사이 배치가 같은 궤도
   pre-event(6/26 FAA4, 6/27 S1A, 6/28 등)를 완료 → **baseline v2 재구축**
   (컷오프 7/3 유지 — 7/4·7/6·7/7은 강우 시작 가능성으로 제외, 사용자 결정.
   신규 17프레임 반영, 7개 날짜 31프레임).
3. **탐지 성능 최적화**: 전체 격자(86395×72001)를 날짜와 무관하게 전부 스캔하던
   것을 **post 씬 경계 합집합 ∩ baseline 윈도우**로 축소 — 결과 동일, 소형
   프레임 날짜는 30분 → 1~2분.
4. **침수 시간선 완성**: 7/8 당일 저녁 1.64km² 최초 검출(같은 궤도 6/26 FAA4
   대비), 7/10 69.06km², 7/16 강원 동부 97.87km²(6/27 S1A 대비, v2로 비교
   가능해짐). 7/11은 pre-event 동일궤도 미촬영으로 비교 불가 확정.
   상세: [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md).
5. 7/19 신규 2씬(0B91/3194) 발견·다운로드. README/TODO/PROGRESS 문서 갱신.
6. **NAS 업로드 후 로컬 정리 운영 체계화**: 사용자가 GRD 원본을
   `X:\02_Analysis\20260708_Flood\Sentinel-1`에 업로드. 바이트 단위 크기
   검증 후 RTC 완료된 60개 로컬 삭제(F: 35→90GB), 이후 흐름을 "다운로드→
   RTC→NAS 검증→로컬 삭제"로 정착. NAS↔로컬 rtc_grd 폴더도 주기적으로
   대조해 사용자가 별도로 지운 완료분까지 정확히 반영.
7. **일본/중국 전용 씬 판별 방법론 확립**: 처음엔 bbox 사각형 겹침으로
   판단하려다, 7/8·7/10 등 핵심 검출에 쓰인 씬까지 잘못 걸러질 뻔해서
   **실제 footprint 폴리곤을 `Korea_Peninsula.geojson`과 shapely로 교차
   계산**하는 방식으로 전환. 사용자가 별도로 갖고 있던
   `satellite_inventory_sido_korean_*.csv`(대표좌표 1점 역지오코딩 방식)와
   대조해 방법론 차이를 확인 — 대각선 SAR 스와스에서는 폴리곤 교차만 신뢰
   가능함을 상호 검증. 최종 제외: `CDFD`·`1CE4`(중국 서해)·`F598`·`F05D`
   (일본/대한해협), 전부 한반도 실경계와 0% 겹침.
8. **북한 관련 잔여 8씬 우선순위 재처리**: 최신 날짜순(0B91→3194→2B06→
   9FFF→5D47→525F→1571→794A)으로 재정렬해 순차 RTC. 진행 중 794A가 150분
   (정상 최대치의 2배)까지 늘어져 멈춘 것으로 판단, 강제종료 후 재시도.
   2B06의 정확한 동일궤도 짝을 재확인해 이전 안내(6668 등 7/6 전체)를
   `427D` 하나로 정정.
9. **baseline v3 설계**: `build_baseline_composite_grd.py`에
   `--fallback-dates` 옵션 신규 추가 — 컷오프(7/3) 이하 정식 데이터가 없는
   궤도(1571↔9FFF, 7/6계열↔2B06)의 빈틈만 7/4·7/6·7/7로 메우고, 이미 정식
   데이터가 있는 곳은 그대로 유지. RTC 완료 대기 → v3 재구축 →
   `7/4·7/7·7/13·7/14·7/15·7/16·7/18·7/19` 8개 날짜 일관 재탐지를
   백그라운드 파이프라인으로 구성해 실행 중.

### 7/21 — 북한 정량화 한계 규명 + 단일시기 수체지도

1. **v3 8개 날짜 재탐지 완료**: 남한 신뢰 가능(7/14 154km² 최대), 그러나
   북한이 7/13 322·7/18 419·7/19 468km²로 과대. 홍수 전 7/4·7/7에도 북한
   30~37km² 검출 → 아티팩트 확정.
2. **북한 동일궤도 pre/post 1:1 비교**: `detect_flood_grd_v2.py`에
   `--baseline`/`--tag` 옵션 신규 추가. 7/13↔7/1 190·7/18↔7/6 254·
   7/19↔6/25 465km²(북한 보수적). 7/6·6/25 모자이크가 삭제된 중국 프레임/
   궤도 불일치로 처음 실패 → 로컬 잔존 올바른 궤도 프레임만으로
   `s1_rtc_db_mosaic_20260625_s1d.vrt`·`_20260706_kr.vrt` 재생성해 해결.
3. **7/1 습윤도 진단**: diff(7/13−7/1) 북한 band 집계 → 7/1이 더 어두운(젖은)
   면적 13,114km² vs 7/13이 더 어두운 면적 3,189km²(비 4.1). 7/1 baseline이
   이미 크게 젖어 있었음.
4. **SPN 북한 날씨 교차검증**: `SPN_오늘의_북한날씨_20260625_20260721.md`
   (기상청 발표)로 baseline 후보 강수 확인 — 6/25(황해 5~40mm)·7/1(황해
   30~80mm)·7/6(평안·함남·황해 30~80mm, 평북 100mm+) **전부 강수일**.
   관측 기간 내내 북한 장마 → **마른 baseline 부재**가 정량화 불가의 근본 원인.
   결론을 [FLOOD_NORTH_KOREA_KR.md](FLOOD_NORTH_KOREA_KR.md)에 정리.
5. **baseline 무관 단일시기 수체지도 신규 도구**: `build_water_per_date.py`
   (날짜별, 6/25~7/19 전 날짜 생성)·`build_water_single_scene.py`(단일 씬 →
   `downloads/water/scene_water/<씬ID>.tif`, 392D 105.01km²). "변화"가 아닌
   "상태"라 baseline 문제와 무관하게 신뢰. NAS 업로드 후 로컬 삭제 운영으로
   VRT가 삭제된 소스를 참조하는 문제를 자동 감지·재생성하도록 보완.
6. **씬 제외·수집 관리**: 일본/중국 전용 궤도는 footprint 폴리곤 교차 0%인
   것만 제외(bbox·대표점 방식은 부정확). 7/20 신규 패스(궤도 008632)
   7프레임 다운로드·RTC(392D 등, 북한 함경~제주 남북 스와스). 코페르니쿠스
   브라우저에 보인 비-COG(84AC 등) 제품은 이미 받은 COG의 중복이라 무시.

## 다음 할 일

1. **북한 동일궤도 4.4% 어두워짐 판정 마무리**: `hand_north_orbit.vrt`가
   생겼으니 `s1_rtc_db_diff_0701_vs_0713.tif`와 결합해
   (dB 어두워짐 AND HAND 낮음)로 오탐(그림자 등) 걸러내면 실제 변화 면적을
   추정할 수 있음. `build_baseline_water.py`의 판정 로직을 이 영역에 맞게
   재사용 가능. (현재 프로젝트 핵심 범위 밖이므로 필요 시에만.)
2. **post-event SLC**는 사용자가 "다음에 하겠습니다"로 보류함 — 필요 시
   `main_s1_list.py` 재실행(41E9/64C0/04E2 등 신규만 받아짐) 후
   `batch_slc_rtc.py`.
3. **(최우선) RTC 배치 완료 → 마무리 사이클**: ① 배치 종료 확인 → ② 7/19
   2씬 포함 `batch_grd_rtc.py` 재실행 → ③ baseline v3 최종 재구축(6/25 S1D
   아침·6/30 추가, 컷오프 7/3 — 낡은 날짜별 VRT 삭제 후) → ④ 전 날짜 일관
   재계산 → ⑤ [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md) 수치 갱신.
   상세 체크리스트는 [TODO_KR.md](TODO_KR.md) P1.
4. (선택) 매니페스트가 top-k만 기록하는 문제 — 다운로드 대상 전체를 기록하도록
   `main_s1_list*.py` 개선하면 이번 EBE9처럼 URL을 다시 조회할 필요가 없어짐.
5. (선택) `README_ENG.md` 전체 동기화 (현재는 검색·다운로드 단계만 다루는 구버전).

## 주의/메모

- 다운로드 이어받기: zipper URL은 Range 재개를 지원하지만
  `download.dataspace.copernicus.eu`는 무시하고 200으로 전체를 다시 보냄
  (`download_s1.py`가 감지해 처음부터 다시 받음 — 데이터 무결성엔 문제 없음).
- `s1_pipeline` env = 검색·다운로드(dotenv 등), `s1_snappy` env = SNAP 전처리.
  다운로드 스크립트를 `s1_snappy`로 돌리면 `ModuleNotFoundError: dotenv` 발생.
- 홍수 목표 시각(7/8 18:30 KST ≈ 09:30 UTC)과 거의 같은 시각의 7/8 S1C 촬영이
  카탈로그에 있으나 제주 남쪽 해상 프레임이라 AOI와 무관.
- **`.env`는 git 히스토리 재작성(filter-repo, rebase 등) 작업 전에 반드시 별도
  위치에 백업**. `.gitignore`에 있어도 "추적되던 파일"이 히스토리에서 완전히
  빠지면 작업 트리에서도 삭제될 수 있음 (7/14 실제 발생).
- STAC 아이템 게시 지연은 촬영 후 **3~4시간**이 일반적 (7/13 밤 패스로 실측:
  촬영→게시 약 4시간). "아직 안 올라왔다"고 판단하기 전에 이 정도는 기다릴 것.
