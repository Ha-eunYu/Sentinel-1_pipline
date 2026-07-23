# SNAP 없이 Sentinel-1 RTC — sarsen 기반 (2026-07-23)

SNAP을 설치할 수 없는 환경에서 Sentinel-1 GRD를 RTC(γ0)/GTC로 지형보정하는
방법. ESA SNAP의 Terrain-Flattening + Terrain-Correction을 순수 파이썬
([sarsen](https://github.com/bopen/sarsen) + xarray-sentinel + rasterio)으로
대체한다. 스크립트: [rtc_sarsen.py](rtc_sarsen.py). 실행 환경: conda `sarsen_clean`
(sarsen 0.9.3).

## 왜 sarsen인가 / 대안 비교

| 방법 | SNAP 필요? | 비고 |
| --- | --- | --- |
| **sarsen** | ❌ | 순수 파이썬. GRD/SLC γ0-RTC(David Small flattening-gamma) + GTC. **채택** |
| pyroSAR | ✅(SNAP/GAMMA 래핑) | 결국 SNAP/GAMMA 설치 필요 → 제외 |
| ISCE3 / OPERA-RTC | ❌ | 설치 무겁고 GRD보다 SLC 중심 → 과함 |
| 직접 구현(Range-Doppler+flattening) | ❌ | sarsen이 이미 정확히 구현 → 재발명 불필요 |
| Java | — | SNAP 엔진 jar 임베드 외 순수 자바 대안 없음 → 사실상 SNAP |

`sardem-sarsen-main/`은 이 워크플로의 참조 앱(sardem으로 DEM 다운 + sarsen).
우리는 DEM을 매번 받지 않고 **로컬 COP30 VRT**를 쓰고, 아래 2가지 필수 보정을
추가했다.

## ⚠️ 이 데이터에서 반드시 필요한 두 가지 (실측 확인)

### 1. S1C/S1D 지원 몽키패치
xarray-sentinel 0.9.5의 애노테이션 파서 정규식이 **`s1[ab]`로 하드코딩**
(esa_safe.py:99)돼 있어 **Sentinel-1C/D를 인식하지 못한다** — 그룹 0개로
`ValueError: Invalid group 'IW/VV'`. 이 프로젝트 데이터는 전부 S1C/S1D라 그대로는
한 장도 못 읽는다. `rtc_sarsen.py`는 임포트 시 그 함수를 `s1[a-d]`로 런타임
몽키패치한다(설치 파일·네트워크 불변, 유일한 하드코딩 지점). 패치 후 정상 로드
확인: `product_type=GRD, 26362×16664`.

### 2. DEM 수직기준 EGM2008 → 타원체고
COP30(및 NGII)은 **EGM2008 지오이드(정표고)** 기준인데 sarsen의 Range-Doppler
지오코딩은 **타원체고**를 가정한다. SNAP은 이 보정을 내부에서 했지만
(`externalDEMApplyEGM`) sarsen은 안 한다. 안 하면 급경사에서 수십 m 위치편차가
생긴다. `rtc_sarsen.py`는 PROJ 데이터의 `us_nga_egm08_25.tif`(EGM2008 undulation
N)를 DEM 격자에 리샘플해 **h_타원체 = h_정표고 + N**으로 변환한다. 392D 스와스
실측: 평균 **+23.74 m**(21.0~26.8), 한국 EGM2008 지오이드고와 일치. `--no-egm`로
끌 수 있다.

## 입력 데이터 (이 시스템 기준)

- **COP30**: `D:/00_COP30/COP30_hh.vrt` (전지구, 26,482 타일, EPSG:4326 30m,
  Float32, EGM2008 지오이드 기준). gdalwarp가 bbox만 클립하므로 전지구라도 빠름.
- **외부 DEM(NGII 등)**: `--external-dem <경로>`. EPSG:4326으로 자동 재투영·클립.
  정표고 기준이면 EGM 보정도 동일 적용(NGII 수직기준이 EGM과 다르면 --no-egm 후
  별도 보정 고려).
- **EGM2008 그리드**: `pyproj` 데이터의 `us_nga_egm08_25.tif` 자동 탐색
  (`--egm-grid`로 지정 가능).

## 실행

```bash
# RTC(γ0) — 기본 COP30
conda run -n sarsen_clean python rtc_sarsen.py --zip downloads/sentinel1_grd/<GRD>.zip
# GTC(지형평탄화 생략)
conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD>.zip --gtc
# 외부 DEM(NGII)
conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD>.zip \
    --external-dem downloads/dem/ngii_5m_wgs84.tif
# DEM 준비까지만 검증(지형보정 제외)
conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD>.zip --dry-run
```

산출물: `downloads/rtc_grd_sarsen/<씬ID>_rtc_db.tif`(또는 `_gtc_db.tif`).
dB(10log10) 단일밴드, EPSG:4326, nodata=NaN — 기존 파이프라인(`water_otsu`,
`filtering/` 등)과 호환. 스펙클 필터는 sarsen에 없으므로 필요 시 `filtering/`
(Frost/Refined Lee)로 후처리한다.

## 처리 단계 (rtc_sarsen.py)

1. GRD zip → `.SAFE` 추출(임시)
2. 씬 bbox 산출(측정 그룹 geospatial 속성 → 없으면 GCP)
3. DEM 구성: COP30 VRT(또는 외부 DEM)를 bbox+여백으로 gdalwarp 클립
4. EGM2008 보정: N 리샘플 후 정표고+N → 타원체고 DEM
5. `sarsen.terrain_correction`(RTC `gamma_bilinear` / GTC) → linear γ0
6. dB 변환 → `_rtc_db.tif`

## 한계 / 검증 상태

- 2~4·6단계와 S1C 패치는 **실측 검증 완료**(dry-run). 5단계(sarsen 실제
  지형보정)는 이 문서 작성 시점 기준 미실행(무거워 별도 실행 예정) — 첫 실행 후
  SNAP RTC 산출물과 dB 분포·지오코딩을 교차검증할 것.
- sarsen γ0(flattening-gamma)과 SNAP Terrain-Flattening은 알고리즘이 유사하나
  동일하진 않다. 절대 dB 기준이 미세하게 다를 수 있으므로, 고정 임계값(-16dB)을
  쓰는 탐지에 넣기 전 SNAP RTC와 대조 권장.
