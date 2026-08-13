# Sentinel-1 홍수 모니터링 파이프라인

Copernicus Data Space Ecosystem(CDSE)에서 Sentinel-1 SLC/GRD를 검색·다운로드하고,
ESA SNAP(gpt)으로 RTC(Radiometric Terrain Correction) 전처리한 뒤, dB 임계값 + HAND
결합으로 수체를 탐지하는 파이프라인입니다. 현재는 **2026년 7월 한국 홍수 모니터링**
(홍수일 7/8, AOI: 충청권)을 대상으로 설정되어 있습니다.

작업 진행 이력과 현재 데이터 인벤토리는 [PROGRESS_KR.md](docs/worklog/PROGRESS_KR.md),
코드 품질 리뷰는 [CODE_REVIEW_KR.md](docs/review/CODE_REVIEW_KR.md), 다음 할 일 체크리스트는
[TODO_KR.md](docs/worklog/TODO_KR.md) 참고.

(English version: [README_ENG.md](README_ENG.md) — 검색·다운로드 부분만 다루는 구버전)

## 파이프라인 전체 구조

> **실행 경로**: 아래 파일들은 모두 `s1/` 패키지 안에 있다. 실행은 저장소
> 루트에서 `python -m s1.tools.<영역>.<모듈>` 형식으로 한다(폴더 구조 절 참고).

```text
[1] 검색·다운로드 (env: s1_pipeline)
    main_s1_list.py      SLC  ─┐   CDSE STAC 검색 -> manifest -> zipper 다운로드
    main_s1_list_grd.py  GRD  ─┘   (이어받기·토큰 자동갱신 지원)
    search_korea_missing.py   한반도 미보유분 목록만 (다운로드 안 함)
    download_korea_missing.py 위 목록을 실제로 받기 (로컬·RTC·NAS 보유분 제외)
    download_aug_pair.py      지정한 씬만 골라 받기 (8월 가뭄 비교쌍 5장)

[2] RTC 전처리 (env: s1_snappy + SNAP Desktop 설치 필요)
    prepro_gpt.py        SLC 1장 -> AOI 서브셋 RTC dB   (batch_slc_rtc.py 로 일괄)
    prepro_grd_gpt.py    GRD 1장 -> 전체 씬 RTC dB      (batch_grd_rtc.py 로 일괄)
    build_rtc_mosaic.py  날짜별 프레임들을 VRT 모자이크로
    rebuild_mosaic_extdem.py  VH RTC(+external DEM)를 날짜별 모자이크로 (vrt_vh/)
    check_mosaic_basin_cover.py  그 모자이크가 유역을 덮는지 **유효화소 기준** 검증

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
    filtering/  순수 파이썬 speckle 필터 7종 (SNAP과 동등성 검증됨; refined_lee_snap=SNAP 충실 재현)
    qa/         필터 4축 정량 평가 (ENL·소하천·경계·수면분리도)

[보고] footprint/export_frames_geojson.py  프레임 현황 GeoJSON (QGIS)
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

상세 절차와 배경은 [SNAPPY_GUIDE_KR.md](docs/pipeline/SNAPPY_GUIDE_KR.md) 참고.

## 실행 순서 (quick start)

```bash
# 0) 검색만
wsl
curl -s "https://stac.dataspace.copernicus.eu/v1/search" -H "Content-Type: application/json" -d '{"collections":["sentinel-1-grd"],"bbox":[124.0,32.0,131.0,40.0],"datetime":"2026-07-13T00:00:00Z/2026-07-16T23:59:59Z","limit":50}' | grep -o '"id":"S1[^"]*"\|"bbox":\[[^]]*\]' | paste - -

# 1) 검색 + 다운로드 (SLC와 GRD 각각)
conda run -n s1_pipeline python -m s1.tools.download.main_s1_list
conda run -n s1_pipeline python -m s1.tools.download.main_s1_list_grd

# 2) RTC 전처리 일괄 실행 (이미 처리된 씬은 자동 스킵 - 재실행 안전)
conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc    # GRD: 전체 씬
conda run -n s1_snappy python -m s1.tools.preprocess.batch_slc_rtc    # SLC: 홍수 AOI 서브셋

# 3) 날짜별 모자이크 (QGIS용 VRT)
conda run -n s1_snappy python -m s1.tools.mosaic.build_rtc_mosaic

# 4) HAND 다운로드 + 기준 수체 지도
conda run -n s1_snappy python -m s1.tools.download.download_hand
conda run -n s1_snappy python -m s1.tools.water.build_baseline_water

# (보고) 프레임 현황 GeoJSON -> QGIS에서 status/product 필드로 스타일
conda run -n s1_pipeline python -m s1.footprint.export_frames_geojson
```

## 폴더 구조 (2026-08-13 재구성)

실행 코드는 전부 **`s1/` 파이썬 패키지** 안에 있다. 라이브러리(`s1/core`,
`s1/preprocess`, `s1/stac`, `s1/footprint`)와 실행 도구(`s1/tools/<영역>`)를
나눴고, 문서는 주제별로 `docs/` 아래로 옮겼다.

```text
s1/
  core/                    # 저장소 전역 공용 (도구가 아니라 라이브러리)
    paths.py               #   모든 경로를 한 곳에서 정의 (저장소 루트 기준 상대)
    scene.py               #   S1 파일명 파싱 (날짜·절대궤도·씬ID·위성)
    aoi.py                 #   원본 zip의 footprint(kml)로 남한 커버율 산정
    config.py              #   .env 로드, CDSEConfig / OutputConfig
  stac/                    # CDSE STAC 검색·다운로드
    client.py  models.py  search_s1.py  download_s1.py
  footprint/               # bbox 대신 footprint로 촬영지역 판정 (FOOTPRINT_AOI_KR.md)
    footprint_aoi.py       #   프레임=shapely / 픽셀=numpy 2계층
    export_frames_geojson.py
  preprocess/              # SNAP gpt 그래프와 배치 뼈대
    prepro_grd_gpt.py      #   GRD -> RTC/GTC dB (--aoi/--dem/--gtc)
    prepro_gpt.py          #   SLC -> RTC dB (AOI 서브셋)
    prepro.py              #   (참고) esa_snappy GPF 직접 호출판
    batch_runner.py        #   임시복사·건너뛰기·실패정리·집계 공통 러너
    export_graph_xml.py    #   SNAP Desktop GraphBuilder용 XML
  tools/                   # 실행 스크립트 (python -m 으로 실행)
    download/              #   main_s1_list*, search_*, download_* (CDSE 수집)
    preprocess/            #   batch_grd_rtc*, batch_grd_gtc, batch_slc_rtc,
                           #   rtc_basin_extdem, rtc_reservoir_windows, patch_void_rtc
    water/                 #   build_water_*, build_baseline_*, detect_flood_*,
                           #   water_area_report, split_flood_area_nk_sk, flood_hotspots
    mosaic/                #   build_rtc_mosaic, rebuild_mosaic_extdem
    dem/                   #   make_basin_dem, prepare_ngii_dem, make_ls_mask, make_test_dem
    audit/                 #   check_*, compare_*, audit_*, benchmark_rtc,
                           #   verify_scene_footprint, audit_rtc_bbox_vs_footprint
    monitor/               #   monitor_new_scenes (신규 촬영 감시)
    scratch/               #   일회성 조사 스크립트 (재현 보장 안 함)

docs/                      # 문서 (주제별)
  pipeline/                #   RTC/GTC 처리·필터·SNAP·DEM·footprint·처리이력
  water/                   #   Otsu 방법론, 궤도별 수체 면적
  flood/                   #   홍수 탐지·타임라인·북한
  drought/                 #   가뭄(25 vs 26년 비교 설계)
  worklog/                 #   진행상황·TODO·작업일지
  review/                  #   코드리뷰·파이프라인 리뷰

scripts/                   # PowerShell 래퍼 (archive_gtc, monitor_*)
graphs/                    # SNAP GraphBuilder용 XML
geojson/                   # AOI·경계 폴리곤
  Korea_flood_AOI.geojson  #   홍수 AOI (전처리 서브셋 기준)
  South_Korea.geojson      #   남한 간략 폴리곤 (⚠ 해안·도서 제외 — 아래 주의)
  Korea_Peninsula.geojson  #   한반도 전체 (footprint 분류용)
  NK.geojson               #   북한 경계
  dams8.geojson / dam_*.geojson / aoi_*.geojson  # 댐·유역 AOI
env/                       # conda 환경 정의
filtering/  qa/            # speckle 필터 구현·정량 QA
data/  kmz/                # 씬 목록 CSV, 공식 침수 kmz
downloads/                 # 산출물 (git 미추적, 아래 별도 표)
temp/                      # 임시 작업물 (git 미추적)
  logs/                    #   배치 실행 로그·에러 (_*.log, _*.err) — 루트에 쌓지 말 것
```

> **로그는 `temp/logs/`에 쓴다.** 예전에는 배치 로그가 저장소 루트에 쌓였다
> (2026-08-13 기준 64개). git에는 안 올라가지만 루트가 어지러워져 옮겼다.
> 로그에서 반복 확인된 문제는 [ISSUES_KR.md](docs/worklog/ISSUES_KR.md)에 옮겨 적는다.
>
> ```powershell
> conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc_frost --month 202608 `
>     *> temp/logs/_rtc_202608.log
> ```

### 실행 방법

패키지 구조라 **저장소 루트에서 모듈 경로로** 실행한다.

```bash
conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc_frost --month 202607
conda run -n s1_snappy python -m s1.tools.water.build_water_per_date_otsu --dates 2026
conda run -n s1_pipeline python -m s1.tools.download.main_s1_list_grd
```

어느 디렉터리에서든 import하고 싶으면 개발 설치를 한다: `pip install -e .`

### downloads/ (git 미추적)

```text
downloads/
  sentinel1/*.zip          # SLC 원본        sentinel1_grd/*.zip  # GRD 원본
  rtc/                     # SLC RTC dB      rtc_grd/             # GRD RTC dB (Refined Lee)
  rtc_grd_frost/           # GRD RTC dB VV (Frost, 현행 기본)
  rtc_grd_frost_vh/        # 같은 파이프라인 VH 판 (VV와 약 6 dB 오프셋 — 섞으면 안 됨)
  rtc_extdem/              # external DEM RTC (하구 결측 회피판)
  gtc/                     # GTC 산출물 (육안 비교 전용)
  excluded_china_japan/    # 한반도 footprint 0% 씬 분리 보관
  dem/  dem_basin/  hand/  # DEM·HAND 보조자료
  water/                   # 고정 임계값 수체 마스크
  water_otsu/              # 궤도별 Otsu 수체 지도
    vrt/                   #   궤도별 dB 모자이크 VRT (QGIS 확인용)
    vrt_vh/                #   VH 날짜별 모자이크
    otsu_thresholds.csv    #   ← git 추적 (임계값 이력)
    water_area_perrow.csv  #   ← git 추적 (면적 이력)
```

## 데이터 처리 현황 (2026-07-22 기준)

| 구분 | 다운로드 | RTC | 비고 |
| --- | --- | --- | --- |
| GRD 한반도 전체 (`sentinel1_grd/`) | 6/25~7/20 수집 (NAS 재병합 포함, 완료분 zip은 삭제) | **RTC 58 / GTC 53+ 완료** (GTC 배치 진행 중) | 6/25~7/20. **2026-07-22 footprint 재감사**로 한반도 교집합 0% 씬 다수 확인·제외(일본/중국 방향). RTC+GTC 끝난 7씬은 `excluded_china_japan/`로 분리. GTC 완료분은 배치 종료 후 `archive_gtc.ps1`로 `downloads/gtc/`로 이동 예정. 상세 [SCENE_FOOTPRINT_REAUDIT_KR.md](docs/pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md)·[GTC_RTC_PROCESSING_LOG_KR.md](docs/pipeline/GTC_RTC_PROCESSING_LOG_KR.md) |
| SLC (`sentinel1/` → **D:로 이동**) | 14 / 14 완료 | 6 / 6 완료 (pre-event만) | F: 용량 확보를 위해 `D:\06_SAR_system_archive\sentinel1`로 이동, 기존 경로에 junction 연결(스크립트 영향 없음). post-event SLC는 보류 중 |
| baseline (pre-event) | — | **v3 완료 (7/21)** | 컷오프 7/3 + 7/4·7/6·7/7 빈틈메우기(북한 커버리지 확장). baseline 수체 6,308 km² |
| 신규 침수 탐지 | — | **v3 8개 날짜 + 동일궤도 3쌍 완료** | v3: 7/4·7/7·7/13~16·7/18·7/19. 동일궤도: 7/13↔7/1·7/18↔7/6·7/19↔6/25. [FLOOD_TIMELINE_KR.md](docs/flood/FLOOD_TIMELINE_KR.md) |
| 단일시기 수체 지도 | — | 6/25~7/20 전 날짜 완료 | baseline 무관 `flood_water_total_<날짜>.tif` (변화 아닌 상태, 고정 -16dB). **Otsu판(궤도별 18그룹)**: `water_otsu/flood_water_total_<날짜>_o<궤도>.tif` — 타일기반 Otsu 자동임계값([OTSU_SPLIT_BASED_KR.md](docs/water/OTSU_SPLIT_BASED_KR.md)), 면적 [WATER_AREA_KR.md](docs/water/WATER_AREA_KR.md) |
| 신규 촬영 감시 | — | baseline 등록 완료(7/22) | STAC 폴링으로 한반도 신규 S1 알림. [SCENE_MONITOR_KR.md](docs/pipeline/SCENE_MONITOR_KR.md) |

- **홍수 침수 시간선(v3)**: 7/14~15 조합에서 **남한 154.1 km²(보수적)** 최대
  관측 — 상세는 [FLOOD_TIMELINE_KR.md](docs/flood/FLOOD_TIMELINE_KR.md). (**⚠️ 2026-07-22
  정정**: 기존에 "7/8 당일 저녁 침수 최초 검출"로 소개했던 7/8·7/10 수치는
  footprint 재감사 결과 물 픽셀이 100% 바다인 아티팩트로 확정돼 무효화됨 —
  [SCENE_FOOTPRINT_REAUDIT_KR.md](docs/pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md).)
- **⚠️ 북한 침수는 정량화 불가**: v3(322/419/468)와 동일궤도 정공법
  (190/254/465)이 크게 다르고, 홍수 전(7/4·7/7)에도 검출됨. 근본 원인은
  **마른 baseline 부재** — SPN 북한 날씨 대조 결과 baseline 후보 6/25·7/1·7/6
  전부 강수일이었다. **남한 수치만 신뢰** — [FLOOD_NORTH_KOREA_KR.md](docs/flood/FLOOD_NORTH_KOREA_KR.md).
- **분석 범위는 홍수 AOI가 아니라 baseline 전체 커버리지**(한반도 대부분+서해)
  — AOI는 다운로드 범위 선정용이었을 뿐, 수재해 모니터링은 위성이 확보되는 전
  지역 대상 ([FLOOD_DETECTION_KR.md](docs/flood/FLOOD_DETECTION_KR.md) 3-B절).
- **일본/중국 씬 판별은 반드시 실제 footprint 폴리곤 교차로** — bbox 사각형
  겹침이나 대표좌표 1점 역지오코딩(예: 다른 도구가 만든 `satellite_inventory_
  sido_korean_*.csv`)은 대각선 SAR 스와스에서 부정확함(TODO_KR.md P1 참고).
- **SLC RTC "실패 6건"은 정상** — 홍수 AOI(126.61~127.39E, 35.91~36.72N) 미교차
  프레임의 의도된 스킵. post-event SLC(`41E9`/`64C0`/`04E2`)는 보류 중 —
  [TODO_KR.md](docs/worklog/TODO_KR.md) P1 참고.

## 연도 간 가뭄 비교용 산출 (VH, 2026-08-07 기준)

홍수 모니터링과 별개로, **댐 유역 가뭄 분석**을 위해 두 해 같은 시기를 견주는
VH RTC 계열을 따로 쌓고 있다. 수체 판별·변화 산정은 `gee` 프로젝트 폴더에서
하고, 이 저장소는 **그 입력(RTC·모자이크)까지**를 만든다.

| 시기 쌍 | 궤도 | 씬 | 대상 |
| --- | --- | --- | --- |
| 2025-07 ↔ 2026-07 | 여러 궤도 (유역마다 다름) | 다수 | 대권역 21 · 댐유역 38 |
| **2025-08-06 ↔ 2026-08-02** | **ASC54 (두 해 공통 궤도가 이것뿐)** | 3 + 2 | **댐유역 6** |

- **궤도를 섞지 않는다.** 커버 영역이 달라져 면적 비교가 성립하지 않기 때문이다.
  8월에 두 해 모두 있는 상대궤도는 ASC54 하나뿐이라 대상이 6개 유역으로 줄었다
  (섬진강·평림은 ASC54 스와스 밖 — 교차 0%).
- **8월 쌍은 위성이 다르다** (2025 S1C ↔ 2026 S1D). 8월에는 같은 위성 조합이
  없다. 임계값이 두 해에 1.5 dB 넘게 벌어지면 보고서에 단서를 달 것 —
  사전 점검 결과는 [WORKLOG_20260807_KR.md](docs/worklog/WORKLOG_20260807_KR.md) 5-3절.
- 산출 전 과정(7월): [PROCESS_202507_202607_KR.md](docs/pipeline/PROCESS_202507_202607_KR.md),
  8월: [WORKLOG_20260807_KR.md](docs/worklog/WORKLOG_20260807_KR.md).

```bash
# 8월 비교쌍 재현 (셋 다 이미 처리된 것은 자동 스킵)
conda run -n s1_pipeline python download_aug_pair.py
conda run -n s1_snappy  python batch_grd_rtc_frost.py --month 202508 \
    --pol VH --out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G --oldest-first
conda run -n s1_snappy  python batch_grd_rtc_frost.py --month 202608 \
    --pol VH --out-dir downloads/rtc_grd_frost_vh --out-tag _vh --gpt-c 7G --oldest-first
conda run -n sar-gee    python rebuild_mosaic_extdem.py --date 20250806 --date 20260802
conda run -n sar-gee    python check_mosaic_basin_cover.py
```

> **⚠ VV와 VH를 섞지 말 것.** GEE 수체탐지는 VH를 쓰고, 실측 오프셋이 약 6 dB다.
> 두 산출물을 비교하면 RTC 차이가 아니라 **편파 차이**를 재게 된다.

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
[FLOOD_TIMELINE_KR.md](docs/flood/FLOOD_TIMELINE_KR.md) 참고).

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
`footprint/export_frames_geojson.py` 결과를 QGIS로 확인.

### 중국·일본 등 비한반도 프레임 자동 제외 (footprint 필터, 2026-07-23)

검색 AOI는 이제 **느슨한 bbox**([123.0, 32.5, 131.5, 43.5], 제주 포함 여유
있게)만 쓰고, `stac/search_s1.py`의 `list_s1_items_for_date`가 검색 결과 각
프레임의 **실제 footprint(item.geometry)를 `geojson/Korea_Peninsula.geojson`
(NK+SK 실경계)와 대조**해 교집합이 전혀 없는(=중국/일본/공해 전용) 프레임을
자동으로 제외합니다(`exclude_non_korea=True` 기본, shapely 사용).

이전에는 검색 AOI로 `Korea.geojson`(남쪽 경계 34.57°N, **제주 미포함**)을
직접 `intersects`로 써서, 그 경계를 넘는 프레임이 **검색 자체에서 통째로
누락**되는 문제가 있었다(예: 7/20 `93DD`, 제주 인근 5.27% 겹침에도 누락).
이제는 넉넉한 bbox로 먼저 다 받아온 뒤 정밀 footprint로만 걸러내므로, 경계에
걸친 정당한 프레임을 놓치지 않으면서 진짜 비한반도 프레임만 뺄 수 있다.

이 자동 필터는 [SCENE_FOOTPRINT_REAUDIT_KR.md](docs/pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md)
가 수동으로 찾아냈던 비한반도 씬(3167·FAA4·9919·D440·88AF·E215·3883·B5A5·
D298·3191 등)을 자동 재현해 검증됐다. 제외된 프레임은 실행 로그에
`[footprint 제외] ...`로 남는다.

### RTC 처리 파라미터 (prepro_gpt.py / prepro_grd_gpt.py)

- DEM: 기본 `Copernicus 30m Global DEM` (자동 다운로드).
  GRD는 `--dem <로컬DEM.tif>`로 NGII 5m 등 External DEM 사용 가능
  (정표고 DEM은 EGM 보정 자동 적용 — [TERRAIN_AUX_DATA_KR.md](docs/pipeline/TERRAIN_AUX_DATA_KR.md))
- 스펙클 필터: **Frost (기본, 2026-07-23 Refined Lee에서 변경 — FILTER_COMPARISON §6)**,
  `speckle_filter_name`으로 변경 가능. ⚠️ 기존 RTC 65개는 Refined Lee(7×7)라 필터
  혼재 — 일관성 필요 시 재처리 권장([GTC_RTC_PROCESSING_LOG_KR.md](docs/pipeline/GTC_RTC_PROCESSING_LOG_KR.md))
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

- [ISSUES_KR.md](docs/worklog/ISSUES_KR.md) — **이슈 트래킹**: SNAP external DEM(VRT 불가·
  하구 결측), PowerShell stderr 오탐, 궤도번호 앞 0 유실, 미해결 항목 상태
- [WORKLOG_20260813_KR.md](docs/worklog/WORKLOG_20260813_KR.md) — 저장소 `s1/` 패키지
  재구성과 공용 모듈(paths·scene·aoi·batch_runner) 분리 내역
- [DROUGHT_KR.md](docs/drought/DROUGHT_KR.md) — 25년 7월 대비 26년 7월 남한 가뭄 판정
  설계, 상대궤도 짝 확정, 말할 수 있는 것 / 없는 것
- [FLOOD_TIMELINE_KR.md](docs/flood/FLOOD_TIMELINE_KR.md) — **침수 시간선**: 날짜별
  위성영상·침수 면적·남북 분리, 해석 주의사항 (핵심 결과 문서)
- [FLOOD_NORTH_KOREA_KR.md](docs/flood/FLOOD_NORTH_KOREA_KR.md) — **북한 지역 전용**:
  영상 인벤토리(궤도 계열), 판별 방법론, baseline v3 빈틈메우기 설계, 한계
- [FLOOD_DETECTION_KR.md](docs/flood/FLOOD_DETECTION_KR.md) — 신규침수 탐지 방법론
  (baseline 구축, 판정 기준, 전범위 확장 경위, 한계)
- [FILTER_COMPARISON_KR.md](docs/pipeline/FILTER_COMPARISON_KR.md) — speckle 필터 4종 비교와
  `filtering/`·`qa/` 패키지 리뷰
- [SNAPPY_GUIDE_KR.md](docs/pipeline/SNAPPY_GUIDE_KR.md) — snappy/esa_snappy 개념, 설치, 방식 A(GPF)
  vs 방식 B(SNAPISTA/gpt), esa-snappy-master 전체 레퍼런스
- [TERRAIN_AUX_DATA_KR.md](docs/pipeline/TERRAIN_AUX_DATA_KR.md) — HAND 개념·다운로드·활용,
  NGII 5m DEM의 External DEM 사용법, DEM 비교 방법론
- [OTSU_SPLIT_BASED_KR.md](docs/water/OTSU_SPLIT_BASED_KR.md) — 궤도별·날짜별 수체 지도의
  타일기반 Otsu 자동임계값 방법론·레퍼런스(Otsu 1979, Martinis 2009, Chini 2017)
- [WATER_AREA_KR.md](docs/water/WATER_AREA_KR.md) — 궤도별·날짜별 수체 면적(pixel_perrow),
  픽셀 vs 폴리곤 면적 산출 방식
- [SCENE_MONITOR_KR.md](docs/pipeline/SCENE_MONITOR_KR.md) — 한반도 신규 Sentinel-1 촬영 자동
  감시와 윈도우 백그라운드(작업 스케줄러 등) 설정
- [PROCESS_202507_202607_KR.md](docs/pipeline/PROCESS_202507_202607_KR.md) — 2025-07 ↔ 2026-07
  두 시기를 동일 파이프라인으로 처리한 전 과정(씬 선별 → RTC → 모자이크 → Otsu → 면적)
- [WORKLOG_20260807_KR.md](docs/worklog/WORKLOG_20260807_KR.md) — **8월 가뭄 비교쌍**(ASC54
  2025-08-06 ↔ 2026-08-02) 산출: 쌍 선정 근거, VH RTC, 모자이크, 커버리지 검증,
  위성 교체(S1C↔S1D) 사전 점검
