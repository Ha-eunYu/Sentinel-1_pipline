# Sentinel-1 홍수 모니터링 파이프라인

Copernicus Data Space Ecosystem(CDSE)에서 Sentinel-1 SLC/GRD를 검색·다운로드하고,
ESA SNAP(gpt)으로 RTC(Radiometric Terrain Correction) 전처리한 뒤, dB 임계값 + HAND
결합으로 수체를 탐지하는 파이프라인입니다. 현재는 **2026년 7월 한국 홍수 모니터링**
(홍수일 7/8, AOI: 충청권)을 대상으로 설정되어 있습니다.

작업 진행 이력과 현재 데이터 인벤토리는 [PROGRESS_KR.md](PROGRESS_KR.md),
코드 품질 리뷰는 [CODE_REVIEW_KR.md](CODE_REVIEW_KR.md), 다음 할 일 체크리스트는
[TODO_KR.md](TODO_KR.md) 참고.

(English version: [README_ENG.md](README_ENG.md) — 검색·다운로드 부분만 다루는 구버전)

## 파이프라인 전체 구조

```text
[1] 검색·다운로드 (env: s1_pipeline)
    main_s1_list.py      SLC  ─┐   CDSE STAC 검색 -> manifest -> zipper 다운로드
    main_s1_list_grd.py  GRD  ─┘   (이어받기·토큰 자동갱신 지원)

[2] RTC 전처리 (env: s1_snappy + SNAP Desktop 설치 필요)
    prepro_gpt.py        SLC 1장 -> AOI 서브셋 RTC dB   (batch_slc_rtc.py 로 일괄)
    prepro_grd_gpt.py    GRD 1장 -> 전체 씬 RTC dB      (batch_grd_rtc.py 로 일괄)
    build_rtc_mosaic.py  날짜별 프레임들을 VRT 모자이크로

[3] 보조 데이터
    download_hand.py     GLO-30 HAND 타일 (수체 탐지 오탐 제거용)
    prepare_ngii_dem.py  NGII DEM -> SNAP External DEM 변환 (필요시)
    compare_dem_rtc.py   Copernicus 30m vs NGII 5m RTC 품질 비교 실험

[4] 수체 탐지 (baseline)
    build_baseline_water.py         pre-event 시계열 -> 기준 수체 지도 (SLC, dB+HAND, 합집합)
    build_baseline_water_grd.py     GRD 버전 (dB+HAND, 합집합, 홍수 AOI)
    build_baseline_latest_grd.py    GRD 남한 전역, dB만(HAND 미사용), 최신 관측 우선
    build_baseline_composite_grd.py pre-event 날짜모자이크 -> 최신관측 우선 합성 -> baseline
                                    (전 과정 자동화, 현재 표준 baseline 생성 경로)

[5] 신규 침수 탐지 (post vs baseline)
    detect_flood_grd.py     v1: 7/13 3프레임, 3중 AND 보수적 판정 (참고용)
    detect_flood_grd_v2.py  현재 버전: --dates 날짜 선택, 관측 중 최솟값 채택,
                            보수적/느슨 2단계, post 씬 경계로 윈도우 최적화.
                            --baseline/--tag 로 동일궤도 pre/post 쌍 비교도 가능
    split_flood_area_nk_sk.py  침수 면적을 위도 기준 남/북한 분리 집계
    flood_hotspots.py          침수 마스크 -> 2km 격자 핫스팟 + GeoJSON

[5b] baseline 무관 단일시기 수체 지도 (변화 아닌 "상태")
    build_water_per_date.py       날짜별 프레임 모자이크 -> dB<-16 수체 지도
    build_water_per_date_otsu.py  궤도별·날짜별, 타일기반 Otsu 자동임계값 -> water_otsu/
    build_water_single_scene.py   단일 씬 하나만 -> scene_water/<씬ID>.tif

[6] 필터 QA (선택)
    filtering/  순수 파이썬 speckle 필터 6종 (SNAP과 동등성 검증됨)
    qa/         필터 4축 정량 평가 (ENL·소하천·경계·수면분리도)

[보고] export_frames_geojson.py  프레임 현황 GeoJSON (QGIS)
       export_graph_xml.py       SNAP Desktop GraphBuilder용 그래프 XML
```

## 요구사항

- conda (miniconda/anaconda)
- CDSE 계정 — <https://dataspace.copernicus.eu> 무료 가입.
  인증은 `CDSE_USERNAME`/`CDSE_PASSWORD` 방식 (OAuth client id/secret 아님)
- **ESA SNAP Desktop** (전처리용) — <https://step.esa.int/main/download/snap-download/>
- 디스크 여유 공간: SLC 1개 5~8GB, GRD 1개 ~1GB, RTC 산출물 별도.
  입력이 HDD에 있으면 SSD로 복사 후 처리하는 것이 훨씬 빠릅니다 (배치 러너가 자동 수행)

## 설치

### 환경 1: s1_pipeline (검색·다운로드·보고)

```bash
conda env create -f env/environment.yml
cp .env.example .env   # CDSE_USERNAME / CDSE_PASSWORD 입력
```

### 환경 2: s1_snappy (SNAP 전처리·분석)

```bash
conda env create -f env/environment_snappy.yml
# SNAP Desktop 설치 후, SNAP의 bin 폴더에서 이 환경의 python을 연결:
"C:\Program Files\snap\bin\snappy-conf.bat" <s1_snappy 환경의 python.exe 경로>
# 확인: conda run -n s1_snappy python -c "import esa_snappy"
```

상세 절차와 배경은 [SNAPPY_GUIDE_KR.md](SNAPPY_GUIDE_KR.md) 참고.

## 실행 순서 (quick start)

```bash
# 0) 검색만
wsl
curl -s "https://stac.dataspace.copernicus.eu/v1/search" -H "Content-Type: application/json" -d '{"collections":["sentinel-1-grd"],"bbox":[124.0,32.0,131.0,40.0],"datetime":"2026-07-13T00:00:00Z/2026-07-16T23:59:59Z","limit":50}' | grep -o '"id":"S1[^"]*"\|"bbox":\[[^]]*\]' | paste - -

# 1) 검색 + 다운로드 (SLC와 GRD 각각)
conda run -n s1_pipeline python main_s1_list.py
conda run -n s1_pipeline python main_s1_list_grd.py

# 2) RTC 전처리 일괄 실행 (이미 처리된 씬은 자동 스킵 - 재실행 안전)
conda run -n s1_snappy python batch_grd_rtc.py    # GRD: 전체 씬
conda run -n s1_snappy python batch_slc_rtc.py    # SLC: 홍수 AOI 서브셋

# 3) 날짜별 모자이크 (QGIS용 VRT)
conda run -n s1_snappy python build_rtc_mosaic.py

# 4) HAND 다운로드 + 기준 수체 지도
conda run -n s1_snappy python download_hand.py
conda run -n s1_snappy python build_baseline_water.py

# (보고) 프레임 현황 GeoJSON -> QGIS에서 status/product 필드로 스타일
conda run -n s1_pipeline python export_frames_geojson.py
```

## 폴더 구조

```text
main_s1_list.py            # SLC 검색 -> manifest -> 다운로드
main_s1_list_grd.py        # GRD 버전 (manifest·폴더 분리)
config.py                  # .env 로드, CDSEConfig / OutputConfig
stac/
  client.py                # CDSE STAC 클라이언트
  models.py                # S1SearchConfig, 날짜 파싱
  search_s1.py             # 검색 + 지정 날짜 근접순 정렬 (MAX_DOWNLOADS로 개수 제한)
  download_s1.py           # 토큰 발급, zipper 다운로드 (이어받기/재시도)
prepro_gpt.py              # SLC -> RTC dB (snapista/gpt, AOI 서브셋)
prepro_grd_gpt.py          # GRD -> RTC/GTC dB (전체 씬, --aoi/--dem/--gtc 옵션)
prepro.py                  # (참고용) esa_snappy GPF 직접 호출 버전 - 아래 '주의' 참고
batch_slc_rtc.py           # SLC 일괄 처리 (SSD 복사, 스킵/재개, AOI 미교차 자동 건너뜀)
batch_grd_rtc.py           # GRD 일괄 처리 (RTC)
batch_grd_gtc.py           # GRD 일괄 처리 (GTC, TF 생략 대조군 - RTC_VS_GTC_KR.md)
build_rtc_mosaic.py        # 날짜별 RTC 모자이크 VRT
download_hand.py           # GLO-30 HAND 타일 다운로드 + VRT
prepare_ngii_dem.py        # (범용) 로컬 DEM -> SNAP External DEM 변환
compare_dem_rtc.py         # Copernicus 30m vs NGII 5m RTC 비교 실험
build_baseline_water.py    # pre-event 기준 수체 지도 (dB + HAND)
build_baseline_composite_grd.py # pre-event baseline (--fallback-dates 빈틈메우기)
detect_flood_grd.py        # 신규침수 탐지 v1 (참고용)
detect_flood_grd_v2.py     # 신규침수 탐지 현재 버전 (--dates/--baseline/--tag)
split_flood_area_nk_sk.py  # 침수 면적 남/북한 분리 집계
flood_hotspots.py          # 침수 핫스팟 추출 + GeoJSON
build_water_per_date.py    # 날짜별 baseline-무관 수체 지도 (고정 dB<-16)
build_water_per_date_otsu.py # 궤도별·날짜별 타일기반 Otsu 수체 지도 (water_otsu/)
water_area_report.py       # 수체 면적 산출·비교 (픽셀 행별보정 / 폴리곤 측지, WATER_AREA_KR.md)
build_water_single_scene.py # 단일 씬 수체 지도 (scene_water/)
monitor_new_scenes.py      # 한반도 신규 S1 촬영 감시 (STAC, SCENE_MONITOR_KR.md)
monitor_new_scenes.ps1     # ↑ 래퍼: 윈도우 알림 + 백그라운드/주기 실행
archive_gtc.ps1            # GTC tif를 downloads/gtc/로 분리 보관 (배치 종료 후 실행)
filtering/                 # speckle 필터 6종 순수 파이썬 구현 (FILTER_COMPARISON_KR.md)
qa/                        # 필터 정량 QA 4축 (compare/metrics/visualize + CLI)
export_frames_geojson.py   # 프레임 상태 보고 GeoJSON (SLC+GRD)
export_graph_xml.py        # SNAP Desktop용 그래프 XML 생성
graphs/                    # 생성된 그래프 XML (GraphBuilder에서 Load 가능)
geojson/                   # AOI·경계 폴리곤 (2026-07-22 폴더 분리)
  Korea_flood_AOI.geojson  #   홍수 피해 지역 AOI (전처리 서브셋/수체 탐지 기준)
  South_Korea.geojson      #   남한 본토 간략 폴리곤 (검색용 - 제주 미포함 주의)
  Korea_Peninsula.geojson  #   한반도 전체 (남북 실경계, footprint 분류용)
  Korea.geojson            #   한반도 단일 폴리곤 (main_s1_list_grd.py 검색 AOI)
  NK.geojson               #   북한 경계
env/                       # conda 환경 정의 (environment.yml / environment_snappy.yml)
kmz/                       # 공식 침수 피해현황 kmz (육안 대조용)
data/                      # 기타 데이터 (satellite_inventory csv, tree.txt, graphs.zip)
SNAPPY_GUIDE_KR.md         # snappy/esa_snappy/SNAPISTA 가이드 (esa-snappy-master 레퍼런스)
TERRAIN_AUX_DATA_KR.md     # HAND / NGII DEM 가이드
RTC_VS_GTC_KR.md           # RTC를 쓰는 이유 (GTC 대조군 개념 설명)
GTC_RTC_PROCESSING_LOG_KR.md # 어떤 씬을 RTC/GTC 했는지 인벤토리·처리과정 (+GTC 정리 방침 5절)
OTSU_SPLIT_BASED_KR.md     # 타일기반 Otsu 방법론·레퍼런스 (Otsu/Martinis/Chini)
WATER_AREA_KR.md           # 궤도별·날짜별 수체 면적 (pixel_perrow 기준)
SCENE_MONITOR_KR.md        # 신규 S1 촬영 자동 감시 + 윈도우 백그라운드 설정
SCENE_FOOTPRINT_REAUDIT_KR.md # footprint 재감사 (7/8·7/10 수치 무효화)
esa-snappy-master/         # esa-snappy 공식 저장소 사본 (참고 문서·소스)
downloads/                 # 실행 결과물 (git 미추적)
  s1_stac_list_manifest.json / s1_stac_list_manifest_grd.json
  sentinel1/*.zip          # SLC 원본
  sentinel1_grd/*.zip      # GRD 원본 (COG SAFE, 씬ID가 _COG로 끝남)
  rtc/                     # SLC RTC dB + 날짜별 모자이크 VRT
  rtc_grd/                 # GRD RTC dB (+ 배치 진행 중에는 GTC _gtc_db.tif 나란히;
                            #   배치 종료 후 archive_gtc.ps1로 gtc/로 분리)
  hand/                    # HAND 타일 + hand_aoi.vrt (홍수 AOI용).
                            # hand_north_orbit.vrt는 별도 탐색적 분석용(PROGRESS_KR.md 참고)
  dem/                     # NGII DEM AOI 클립
  gtc/                     # GTC 산출물 <씬ID>_gtc_db.tif 분리 보관 (육안 비교 전용)
  excluded_china_japan/    # 일본/중국 전용(footprint 0%) 씬 분리 보관 (tif만)
  water/                   # 수체 마스크 (baseline, flood_water_*, diff 등)
    scene_water/           # 단일 씬 수체 지도 (build_water_single_scene.py)
  water_otsu/              # 궤도별·날짜별 타일기반 Otsu 수체 지도 + otsu_thresholds.csv
  monitor_state.json / new_scenes.log  # 신규 씬 감시 상태·로그
```

## 데이터 처리 현황 (2026-07-22 기준)

| 구분 | 다운로드 | RTC | 비고 |
| --- | --- | --- | --- |
| GRD 한반도 전체 (`sentinel1_grd/`) | 6/25~7/20 수집 (NAS 재병합 포함, 완료분 zip은 삭제) | **RTC 58 / GTC 53+ 완료** (GTC 배치 진행 중) | 6/25~7/20. **2026-07-22 footprint 재감사**로 한반도 교집합 0% 씬 다수 확인·제외(일본/중국 방향). RTC+GTC 끝난 7씬은 `excluded_china_japan/`로 분리. GTC 완료분은 배치 종료 후 `archive_gtc.ps1`로 `downloads/gtc/`로 이동 예정. 상세 [SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md)·[GTC_RTC_PROCESSING_LOG_KR.md](GTC_RTC_PROCESSING_LOG_KR.md) |
| SLC (`sentinel1/` → **D:로 이동**) | 14 / 14 완료 | 6 / 6 완료 (pre-event만) | F: 용량 확보를 위해 `D:\06_SAR_system_archive\sentinel1`로 이동, 기존 경로에 junction 연결(스크립트 영향 없음). post-event SLC는 보류 중 |
| baseline (pre-event) | — | **v3 완료 (7/21)** | 컷오프 7/3 + 7/4·7/6·7/7 빈틈메우기(북한 커버리지 확장). baseline 수체 6,308 km² |
| 신규 침수 탐지 | — | **v3 8개 날짜 + 동일궤도 3쌍 완료** | v3: 7/4·7/7·7/13~16·7/18·7/19. 동일궤도: 7/13↔7/1·7/18↔7/6·7/19↔6/25. [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md) |
| 단일시기 수체 지도 | — | 6/25~7/20 전 날짜 완료 | baseline 무관 `flood_water_total_<날짜>.tif` (변화 아닌 상태, 고정 -16dB). **Otsu판(궤도별 18그룹)**: `water_otsu/flood_water_total_<날짜>_o<궤도>.tif` — 타일기반 Otsu 자동임계값([OTSU_SPLIT_BASED_KR.md](OTSU_SPLIT_BASED_KR.md)), 면적 [WATER_AREA_KR.md](WATER_AREA_KR.md) |
| 신규 촬영 감시 | — | baseline 등록 완료(7/22) | STAC 폴링으로 한반도 신규 S1 알림. [SCENE_MONITOR_KR.md](SCENE_MONITOR_KR.md) |

- **홍수 침수 시간선(v3)**: 7/14~15 조합에서 **남한 154.1 km²(보수적)** 최대
  관측 — 상세는 [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md). (**⚠️ 2026-07-22
  정정**: 기존에 "7/8 당일 저녁 침수 최초 검출"로 소개했던 7/8·7/10 수치는
  footprint 재감사 결과 물 픽셀이 100% 바다인 아티팩트로 확정돼 무효화됨 —
  [SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md).)
- **⚠️ 북한 침수는 정량화 불가**: v3(322/419/468)와 동일궤도 정공법
  (190/254/465)이 크게 다르고, 홍수 전(7/4·7/7)에도 검출됨. 근본 원인은
  **마른 baseline 부재** — SPN 북한 날씨 대조 결과 baseline 후보 6/25·7/1·7/6
  전부 강수일이었다. **남한 수치만 신뢰** — [FLOOD_NORTH_KOREA_KR.md](FLOOD_NORTH_KOREA_KR.md).
- **분석 범위는 홍수 AOI가 아니라 baseline 전체 커버리지**(한반도 대부분+서해)
  — AOI는 다운로드 범위 선정용이었을 뿐, 수재해 모니터링은 위성이 확보되는 전
  지역 대상 ([FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md) 3-B절).
- **일본/중국 씬 판별은 반드시 실제 footprint 폴리곤 교차로** — bbox 사각형
  겹침이나 대표좌표 1점 역지오코딩(예: 다른 도구가 만든 `satellite_inventory_
  sido_korean_*.csv`)은 대각선 SAR 스와스에서 부정확함(TODO_KR.md P1 참고).
- **SLC RTC "실패 6건"은 정상** — 홍수 AOI(126.61~127.39E, 35.91~36.72N) 미교차
  프레임의 의도된 스킵. post-event SLC(`41E9`/`64C0`/`04E2`)는 보류 중 —
  [TODO_KR.md](TODO_KR.md) P1 참고.

## 위성 운영 상황과 촬영 일정 확인법

### Sentinel-1A 퇴역 (2026-06-29)

S1A는 **2026-06-29부로 12년 운영을 마치고 퇴역**했습니다
([ESA 공지](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1/Time_to_say_goodbye_to_Sentinel-1A),
[CDSE 공지](https://dataspace.copernicus.eu/news/2026-6-30-copernicus-sentinel-1a-satellite-end-operations-after-12-years-service)).
6/25 S1A 씬이 이 지역 마지막 S1A 촬영이며, 이후 constellation은 **S1C + S1D 2기**
체제입니다. 퇴역 전후 S1C/S1D 궤도 재배치·관측계획 재편이 진행 중이라 이 시기에는
**위성당 12일 반복주기가 매 주기 보장되지 않습니다** (예: 7/7 S1A 반복은 퇴역으로,
7/8 S1C 반복은 관측계획 공백으로 미촬영 — 계획 KML에서 21:15~21:37 UTC datatake
공백 확인됨).

### 촬영 계획(acquisition plan) 확인법

카탈로그에 없다고 촬영 실패가 아니라, 애초에 계획에 없었을 수 있습니다. 확정
일정은 ESA가 공개하는 계획 KML로 확인합니다:

1. <https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans> 에서
   위성별(S1C/S1D) KML 다운로드 (파일명이 계획 기간: `s1c_mp_user_<시작>_<끝>`)
2. KML의 `<Placemark>`에서 한국 통과 예상 시각(UTC) 주변의 `<begin>/<end>`와
   `<coordinates>` 폴리곤이 한반도(경도 125~130, 위도 33~39)와 겹치는지 확인
3. 촬영 후 카탈로그 등록까지 보통 3~6시간 소요

참고 — 홍수일(7/8) 이후 실제 확보된 post-event 관측: 7/8·7/10·7/11·7/13·7/14·
7/15·7/16·7/18·7/19 (패스별 프레임 구성과 침수 분석 결과는
[FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md) 참고).

## 설정 포인트

### AOI (관심 지역)

- **검색 AOI**: `main_s1_list*.py`의 `korea_geojson` — 현재 `South_Korea.geojson`
  (본토 간략 폴리곤, **제주도 미포함**이므로 제주가 필요하면 폴리곤 확장 필요)
- **전처리/수체탐지 AOI**: `Korea_flood_AOI.geojson` — SLC 서브셋과
  `build_baseline_water.py`의 기준 격자가 이 폴리곤(+0.1도 여유)을 따름

### 목표 날짜 지정

`main_s1_list*.py`의 `targets` 리스트에 **날짜만** 넣습니다:
`("라벨", "YYYY-MM-DD")` (예: `("Korea_flood", "2026-07-20")`). 시각·타임존은
필요 없습니다 — **날짜 근접도**로 정렬하기 때문입니다. `window_days`(현재 15일)는
검색 창(±N일)일 뿐 신경 쓸 필요가 거의 없습니다.

### 검색 결과 선별 방식 (날짜 근접순)

지정 날짜에 **가까운 촬영일 순**으로 후보를 정렬한 뒤, **`MAX_DOWNLOADS`개**만
내려받습니다. 이것이 **유일한 설정값**입니다(`main_s1_list*.py` 상단, 기본 10,
`None`이면 창 안의 후보 전부). 예전의 "목표 시각 top-k + 위성별 보장" 방식은
같은 패스 프레임이 우연히 탈락하는 문제가 있어 제거했습니다 — 이제 근접 일자의
프레임을 `MAX_DOWNLOADS` 한도까지 순서대로 받으므로, 한도를 넉넉히 주면(또는
`None`) 해당 날짜의 프레임이 통째로 들어옵니다. 프레임 현황은
`export_frames_geojson.py` 결과를 QGIS로 확인.

### RTC 처리 파라미터 (prepro_gpt.py / prepro_grd_gpt.py)

- DEM: 기본 `Copernicus 30m Global DEM` (자동 다운로드).
  GRD는 `--dem <로컬DEM.tif>`로 NGII 5m 등 External DEM 사용 가능
  (정표고 DEM은 EGM 보정 자동 적용 — [TERRAIN_AUX_DATA_KR.md](TERRAIN_AUX_DATA_KR.md))
- 스펙클 필터: Refined Lee (기본), `speckle_filter_name`으로 변경 가능
- 출력: dB GeoTIFF 하나만 (GeoTIFF 쓰기가 단일 스레드 병목이라 이중 쓰기 금지)

### 수체 탐지 임계값 (build_baseline_water.py)

`수체 = (dB < -16) AND (HAND < 10m)` 이 기본. `--db`, `--hand`로 조정.

## 주의사항

- **prepro.py(esa_snappy GPF 직접 호출)는 참고용입니다.** 이 방식은 파이썬 JVM에서
  SNAP 모듈이 완전히 초기화되지 않아 **DEM 자동 다운로드가 동작하지 않고, 에러가
  파이썬으로 전파되지 않은 채 깨진 GeoTIFF를 만들 수 있습니다.** 실제 처리는
  반드시 gpt 실행 방식(prepro_gpt.py / prepro_grd_gpt.py)을 쓰세요.
- **RTC 산출물은 쓰다 만 파일도 열릴 수 있으므로**, 배치가 비정상 종료된 뒤에는
  해당 씬 산출물을 지우고 재실행하세요 (배치 러너의 정상 실패 처리는 자동 삭제됨).
- `main_s1_list.py`는 검색된 후보를 **전부** 다운로드합니다. 실행 전 디스크 확인.
  GRD 변형은 `max_downloads`로 개수 제한 가능.
- CDSE 다운로드가 네트워크 문제로 끊기면 **같은 명령을 다시 실행** — `.part`
  이어받기와 토큰 자동 재발급으로 이어집니다.
- SLC 카탈로그 등록에는 촬영 후 수 시간~하루 지연이 있고, **촬영 계획에 없던
  지역은 아예 올라오지 않습니다** (같은 궤도의 다른 구간만 공개돼 있다면 그
  지역은 촬영이 안 된 것). Sentinel-1 반복 주기는 위성당 12일이지만 매 주기
  촬영이 보장되지 않으므로, 위의 "위성 운영 상황과 촬영 일정 확인법" 절차로
  계획 KML을 먼저 확인하세요.
- Windows에서 첫 실행 시 SNAP이 궤도 파일과 DEM 타일을
  `C:\Users\<user>\.snap\auxdata\`에 내려받으므로 첫 씬 처리가 더 오래 걸립니다.

## 관련 문서

- [FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md) — **침수 시간선**: 날짜별
  위성영상·침수 면적·남북 분리, 해석 주의사항 (핵심 결과 문서)
- [FLOOD_NORTH_KOREA_KR.md](FLOOD_NORTH_KOREA_KR.md) — **북한 지역 전용**:
  영상 인벤토리(궤도 계열), 판별 방법론, baseline v3 빈틈메우기 설계, 한계
- [FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md) — 신규침수 탐지 방법론
  (baseline 구축, 판정 기준, 전범위 확장 경위, 한계)
- [FILTER_COMPARISON_KR.md](FILTER_COMPARISON_KR.md) — speckle 필터 4종 비교와
  `filtering/`·`qa/` 패키지 리뷰
- [SNAPPY_GUIDE_KR.md](SNAPPY_GUIDE_KR.md) — snappy/esa_snappy 개념, 설치, 방식 A(GPF)
  vs 방식 B(SNAPISTA/gpt), esa-snappy-master 전체 레퍼런스
- [TERRAIN_AUX_DATA_KR.md](TERRAIN_AUX_DATA_KR.md) — HAND 개념·다운로드·활용,
  NGII 5m DEM의 External DEM 사용법, DEM 비교 방법론
- [OTSU_SPLIT_BASED_KR.md](OTSU_SPLIT_BASED_KR.md) — 궤도별·날짜별 수체 지도의
  타일기반 Otsu 자동임계값 방법론·레퍼런스(Otsu 1979, Martinis 2009, Chini 2017)
- [WATER_AREA_KR.md](WATER_AREA_KR.md) — 궤도별·날짜별 수체 면적(pixel_perrow),
  픽셀 vs 폴리곤 면적 산출 방식
- [SCENE_MONITOR_KR.md](SCENE_MONITOR_KR.md) — 한반도 신규 Sentinel-1 촬영 자동
  감시와 윈도우 백그라운드(작업 스케줄러 등) 설정
