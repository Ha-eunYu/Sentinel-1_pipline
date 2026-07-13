# 작업 진행 현황 (2026-07-13 기준)

2026년 7월 한국 홍수(홍수일 7/8, AOI: 충청권 부여·서천·청주 인근) 모니터링
파이프라인의 작업 이력·데이터 인벤토리·다음 할 일 정리. 파이프라인 사용법은
[README_KR.md](README_KR.md) 참고.

## 한눈에 보기

| 단계 | 상태 |
| --- | --- |
| GRD 검색·다운로드 (14씬) | ✅ 완료 |
| GRD RTC (14씬 전체) | ✅ 완료 |
| SLC 검색·다운로드 (14씬) | ✅ 완료 (7/13 EBE9 마지막 완료) |
| SLC RTC (AOI 교차 6씬) | ✅ 완료 — 나머지 8씬은 AOI 미교차로 대상 아님 |
| HAND / NGII DEM / 기준 수체 지도 | ✅ 완료 |
| post-event(7/8 이후) 영상 확보 | ⏳ 대기 — 최초 촬영이 7/13 밤~7/14 (아래 참고) |
| 신규 침수 탐지 (`detect_flood.py`) | ⬜ 미착수 — post 영상 확보 후 |

## 데이터 인벤토리 (`downloads/`)

- `sentinel1/` — SLC 원본 14개 (2026년 씬) + 2022 Jeddah 참조 1개
  - 6/25 S1A ×1, 6/26 S1C ×4, 7/1 S1C ×3, 7/2 S1D ×2, 7/3 S1C ×3, EBE9(북한 쪽) ×1
- `sentinel1_grd/` — GRD(COG) 원본 14개 (6/25 ×2, 6/26 ×4, 7/1 ×3, 7/2 ×2, 7/3 ×3)
- `rtc/` — SLC RTC dB 6개 + 날짜별 모자이크 VRT (0625/0626/0701/0702)
- `rtc_grd/` — GRD RTC dB 14개 + NGII/Copernicus DEM 비교 실험 산출물(5469 씬)
- `hand/` — GLO-30 HAND 타일 4장(N35–36/E126–127) + `hand_aoi.vrt`
- `dem/` — NGII 5m DEM AOI 클립 (`ngii_5m_aoi.tif`)
- `water/` — 날짜별 수체 마스크 4개(0625/0626/0701/0702), `baseline_water_union.tif`,
  `water_frequency.tif`, `observed_count.tif`
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

## 다음 할 일

1. **7/14 이후 post-event 다운로드** — 촬영 후 카탈로그 등록까지 3~6시간이므로
   7/14 밤부터 `main_s1_list_grd.py` / `main_s1_list.py` 재실행 (기존 파일은 자동
   스킵, 신규만 다운로드). 목표 시각(7/8 18:30 KST)+`window_days=15` 창에 7/14가
   포함되므로 설정 변경 불필요.
2. post-event 씬 RTC: `batch_grd_rtc.py` / `batch_slc_rtc.py` 재실행 (스킵 로직으로
   신규만 처리됨).
3. **`detect_flood.py` 작성** — post 수체(dB < -16 AND HAND < 10m) −
   `baseline_water_union.tif` = 신규 침수. `build_baseline_water.py`의 격자·마스킹
   로직 재사용.
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
