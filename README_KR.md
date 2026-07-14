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

[4] 수체 탐지
    build_baseline_water.py   pre-event 시계열 -> 기준(평상시) 수체 지도
    (detect_flood.py 예정: post 영상 확보 후 신규 침수 = post 수체 - baseline)

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
conda env create -f environment.yml
cp .env.example .env   # CDSE_USERNAME / CDSE_PASSWORD 입력
```

### 환경 2: s1_snappy (SNAP 전처리·분석)

```bash
conda env create -f environment_snappy.yml
# SNAP Desktop 설치 후, SNAP의 bin 폴더에서 이 환경의 python을 연결:
"C:\Program Files\snap\bin\snappy-conf.bat" <s1_snappy 환경의 python.exe 경로>
# 확인: conda run -n s1_snappy python -c "import esa_snappy"
```

상세 절차와 배경은 [SNAPPY_GUIDE_KR.md](SNAPPY_GUIDE_KR.md) 참고.

## 실행 순서 (quick start)

```bash
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
  search_s1.py             # 검색 + 목표시각 근접 정렬 + 위성별 커버 보장
  download_s1.py           # 토큰 발급, zipper 다운로드 (이어받기/재시도)
prepro_gpt.py              # SLC -> RTC dB (snapista/gpt, AOI 서브셋)
prepro_grd_gpt.py          # GRD -> RTC dB (전체 씬, --aoi/--dem 옵션)
prepro.py                  # (참고용) esa_snappy GPF 직접 호출 버전 - 아래 '주의' 참고
batch_slc_rtc.py           # SLC 일괄 처리 (SSD 복사, 스킵/재개, AOI 미교차 자동 건너뜀)
batch_grd_rtc.py           # GRD 일괄 처리
build_rtc_mosaic.py        # 날짜별 RTC 모자이크 VRT
download_hand.py           # GLO-30 HAND 타일 다운로드 + VRT
prepare_ngii_dem.py        # (범용) 로컬 DEM -> SNAP External DEM 변환
compare_dem_rtc.py         # Copernicus 30m vs NGII 5m RTC 비교 실험
build_baseline_water.py    # pre-event 기준 수체 지도 (dB + HAND)
export_frames_geojson.py   # 프레임 상태 보고 GeoJSON (SLC+GRD)
export_graph_xml.py        # SNAP Desktop용 그래프 XML 생성
graphs/                    # 생성된 그래프 XML (GraphBuilder에서 Load 가능)
Korea_flood_AOI.geojson    # 홍수 피해 지역 AOI (전처리 서브셋/수체 탐지 기준)
South_Korea.geojson        # 남한 본토 간략 폴리곤 (검색용 - 제주 미포함 주의)
Korea_Peninsula.geojson    # 한반도 전체 (광역 검색용)
SNAPPY_GUIDE_KR.md         # snappy/esa_snappy/SNAPISTA 가이드 (esa-snappy-master 레퍼런스)
TERRAIN_AUX_DATA_KR.md     # HAND / NGII DEM 가이드
esa-snappy-master/         # esa-snappy 공식 저장소 사본 (참고 문서·소스)
downloads/                 # 실행 결과물 (git 미추적)
  s1_stac_list_manifest.json / s1_stac_list_manifest_grd.json
  sentinel1/*.zip          # SLC 원본
  sentinel1_grd/*.zip      # GRD 원본 (COG SAFE, 씬ID가 _COG로 끝남)
  rtc/                     # SLC RTC dB + 날짜별 모자이크 VRT
  rtc_grd/                 # GRD RTC dB (+ DEM 비교 실험 산출물)
  hand/                    # HAND 타일 + hand_aoi.vrt
  dem/                     # NGII DEM AOI 클립
  water/                   # 수체 마스크 (baseline_water_union.tif 등)
```

## 데이터 처리 현황 (2026-07-14 기준)

| 구분 | 다운로드 | RTC | 비고 |
| --- | --- | --- | --- |
| GRD pre-event (`sentinel1_grd/`) | 14 / 14 완료 | 14 / 14 완료 | 6/25 S1A ×2, 6/26 S1C ×4, 7/1 S1C ×3, 7/2 S1D ×2, 7/3 S1C ×3 |
| GRD post-event | 3 / 3 완료 | ✅ 완료 (씬당 10.5~69.4분) | 7/13 21:39~21:40 UTC S1C 하강 패스 — 홍수일(7/8) 이후 최초 촬영. 모자이크는 `gdalbuildvrt` 직접 실행(스크립트가 GRD 미지원) |
| SLC (`sentinel1/`) | 14 / 14 완료 | 6 / 6 완료 (pre-event만) | post-event SLC 3개는 카탈로그엔 있으나 보류 중(아래) |

- **SLC RTC "실패 6건"은 정상입니다.** 나머지 SLC 8개(EBE9, 0C58, 7AB0, 65DC,
  D560, 43D6, 8105 등)는 footprint 대조 결과 홍수 AOI(경도 126.61~127.39,
  위도 35.91~36.72)와 **교차하지 않는** 인접/동부 swath 프레임이라 Subset 단계에서
  의도적으로 걸러집니다. 7/3 패스 3개는 경도 127.7° 동쪽 swath라 AOI 전체를 벗어남.
- 7/2 씬 `29B8_rtc_db.tif`가 11MB로 유독 작은 것도 정상 — 해당 프레임이 AOI 남쪽
  끄트머리만 걸쳐 서브셋 결과가 작을 뿐입니다.
- **post-event(홍수일 7/8 이후) GRD가 처음으로 확보됐습니다** (7/13 밤 촬영,
  7/14 카탈로그 게시). 아래 "위성 운영 상황" 참고. post-event SLC(3개, 씬ID
  `41E9`/`64C0`/`04E2`)는 카탈로그에는 있지만 다운로드는 보류 중 — 진행 상황은
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

참고 — 계획 KML로 확인된 다음 AOI 커버 촬영: **7/13 21:28~21:40 UTC S1C**(하강),
**7/14 09:30~09:31 UTC S1D**(상승, 폴리곤이 홍수 AOI 정확히 커버). 이것이 최초의
post-event 영상이 될 예정입니다.

## 설정 포인트

### AOI (관심 지역)

- **검색 AOI**: `main_s1_list*.py`의 `korea_geojson` — 현재 `South_Korea.geojson`
  (본토 간략 폴리곤, **제주도 미포함**이므로 제주가 필요하면 폴리곤 확장 필요)
- **전처리/수체탐지 AOI**: `Korea_flood_AOI.geojson` — SLC 서브셋과
  `build_baseline_water.py`의 기준 격자가 이 폴리곤(+0.1도 여유)을 따름

### 목표 시각

`main_s1_list*.py`의 `targets` 리스트. **타임존 오프셋(+09:00) 필수.**
`window_days`(현재 15일)가 검색 창을 결정합니다.

### 검색 결과 선별 방식

목표 시각 근접순 top-k(기본 10) + 검색에 등장한 위성별 최근접 1개 보장.
**같은 패스의 모든 프레임을 받는 방식이 아니므로**, 특정 날짜의 전체 프레임이
필요하면 후보에서 빠진 프레임을 ID 지정으로 별도 다운로드해야 합니다
(프레임 현황은 `export_frames_geojson.py` 결과를 QGIS로 확인).

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

- [SNAPPY_GUIDE_KR.md](SNAPPY_GUIDE_KR.md) — snappy/esa_snappy 개념, 설치, 방식 A(GPF)
  vs 방식 B(SNAPISTA/gpt), esa-snappy-master 전체 레퍼런스
- [TERRAIN_AUX_DATA_KR.md](TERRAIN_AUX_DATA_KR.md) — HAND 개념·다운로드·활용,
  NGII 5m DEM의 External DEM 사용법, DEM 비교 방법론
