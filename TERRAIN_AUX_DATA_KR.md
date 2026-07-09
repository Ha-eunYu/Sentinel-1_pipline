# 지형 보조 데이터 가이드 — HAND & NGII 5m DEM

홍수 수체 탐지 파이프라인에서 쓰는 지형 보조 데이터 두 가지(HAND, NGII 고해상도 DEM)의
출처·다운로드·사용법 정리. 관련 스크립트: [download_hand.py](download_hand.py),
[prepro_grd_gpt.py](prepro_grd_gpt.py), [prepare_ngii_dem.py](prepare_ngii_dem.py)

---

## 1. HAND (Height Above Nearest Drainage)

### 1.1 개념

HAND는 각 픽셀의 고도를 "해발"이 아니라 **가장 가까운 하천(배수망)으로부터의 상대 높이**로
나타낸 지형 지표입니다. DEM에서 배수망을 추출한 뒤, 각 픽셀이 물이 흘러 내려가 닿는
하천 지점과의 고도차를 계산한 것입니다.

### 1.2 SAR 홍수 탐지에서 왜 필요한가

dB 임계값 기반 수체 탐지의 대표적 오탐 두 가지를 걸러줍니다:

- **레이더 그림자(shadow)**: 산 뒤쪽 사면은 신호가 닿지 않아 물처럼 어둡게 나오지만,
  HAND가 큰(하천에서 높이 떨어진) 곳이므로 침수일 수 없음
- **매끈한 인공면**(아스팔트, 활주로 등): 어둡게 나오지만 역시 HAND가 크면 배제 가능

적용 방법: `수체 후보 (dB < 임계값) AND (HAND < 5~15 m)` — ASF HydroSAR 등
운영 홍수 매핑 시스템들이 쓰는 표준 기법입니다. 임계값은 지형에 따라 조정
(평야 지역은 15m까지 여유 있게, 산간은 5m 수준으로 좁게).

### 1.3 데이터 출처와 다운로드

- **데이터**: ASF GLO-30 HAND — Copernicus GLO-30 DEM(30m)에서 유도한 전지구 HAND
- **접근**: AWS Open Data (인증 불필요), Copernicus DEM과 같은 1°×1° 타일 격자
- **URL 규칙**: `https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_<N36>_00_<E127>_00_HAND.tif`
- **스크립트**: [download_hand.py](download_hand.py) — 홍수 AOI(+0.1°)를 덮는 타일을
  자동 계산·다운로드하고 VRT 모자이크 생성

```bash
conda run -n s1_snappy python download_hand.py
```

### 1.4 현재 보유 데이터

| 파일 | 내용 |
| --- | --- |
| `downloads/hand/Copernicus_DSM_COG_10_N35~N36_E126~E127_*_HAND.tif` | 타일 4개 (약 264MB) |
| `downloads/hand/hand_aoi.vrt` | 모자이크 — QGIS/rasterio에서 이거 하나만 열면 됨 |

RTC dB 산출물(10m)과 격자가 다르므로(30m), 수체 탐지 시 rasterio/gdalwarp로
RTC 격자에 맞춰 리샘플해서 사용합니다.

---

## 2. NGII 5m DEM (국토지리정보원 고해상도 DEM)

### 2.1 보유 데이터

- **위치**: `D:\00_DEM\DEM_5m\Korea_GSC_5m.tif` (16GB)
- **사양** (gdalinfo 확인): EPSG:4326 경위도(재투영 불필요), 5m급(0.0000512°),
  남한 전역(124.96~131.95°E / 33.02~38.41°N), Float32,
  표고 -0.9~1944m, NoData = -3.4e38
- 이미 WGS84 경위도라서 [prepare_ngii_dem.py](prepare_ngii_dem.py)의 재투영 단계는
  필요 없고, **AOI 클립 + NoData 정리만** 하면 SNAP External DEM으로 바로 사용 가능

### 2.2 SNAP External DEM으로 쓰기

SNAP Terrain-Flattening / Terrain-Correction의 기본 DEM(Copernicus 30m 자동 다운로드)
대신 로컬 DEM을 쓰려면 그래프 파라미터를 다음처럼 바꿉니다:

```xml
<demName>External DEM</demName>
<externalDEMFile>F:\06_SAR_system\S1\downloads\dem\ngii_5m_aoi.tif</externalDEMFile>
<externalDEMNoDataValue>-9999.0</externalDEMNoDataValue>
<externalDEMApplyEGM>true</externalDEMApplyEGM>
```

- **externalDEMApplyEGM=true인 이유**: SNAP은 타원체고(ellipsoidal height)를 기대하는데
  NGII DEM은 인천만 평균해수면 기준 정표고(orthometric)이므로, EGM96 지오이드
  보정을 켜서 변환해줘야 기하 정확도가 맞습니다.
- NoData는 원본의 -3.4e38 대신 클립 단계에서 **-9999로 통일** (SNAP 파라미터 입력 편의)

준비 명령 (AOI+0.3° 클립, 압축 저장):

```bash
gdalwarp -te 126.3 35.6 127.7 37.0 -dstnodata -9999 \
    -co COMPRESS=DEFLATE -co TILED=YES \
    "D:\00_DEM\DEM_5m\Korea_GSC_5m.tif" downloads/dem/ngii_5m_aoi.tif
```

[prepro_grd_gpt.py](prepro_grd_gpt.py)는 `--dem <경로>` 옵션으로 External DEM 처리를
지원하며, 산출물 파일명에 `_ngiidem` 접미사가 붙어 Copernicus 결과와 구분됩니다.

### 2.3 Copernicus 30m vs NGII 5m 비교 방법

같은 GRD 씬을 두 DEM으로 각각 RTC 처리한 뒤:

1. **분포 비교**: 육지 Gamma0 dB 백분위(p1~p99) — 방사보정 차이 총량 확인
2. **차분 맵**: `dB(NGII) - dB(Copernicus)` — 차이가 몰리는 곳이 어디인지
   (경사 급한 산지·계곡에서 크게 나타나면 지형보정 품질 차이, 평지에서도 크면 datum/지오이드 문제 의심)
3. **기하 확인**: 도로·하천 등 선형 지물이 실제 위치(정사영상/지도)와 맞는지

기대: 5m DEM이 지형 굴곡을 더 정확히 반영 → 산지 사면의 radiometric 왜곡 보정이
개선되고, 평지(홍수 관심 지역)에서는 차이가 작을 것. 수체 탐지가 주로 평지에서
이뤄지므로 Copernicus 30m로도 충분할 수 있으며, 이 비교로 확인한다.

---

## 3. 수체 탐지에서의 종합 활용 구도

```text
RTC dB (SLC 또는 GRD, prepro*_gpt.py)
        │
        ├─ dB < 임계값 (예: -16dB)  ──────────┐
        │                                      ├─ AND ─→ 침수/수체 마스크
GLO-30 HAND (hand_aoi.vrt)                     │
        └─ HAND < 임계값 (예: 10m) ────────────┘

NGII 5m DEM: RTC 전처리 단계의 지형보정 품질 향상 (External DEM 옵션)
```
