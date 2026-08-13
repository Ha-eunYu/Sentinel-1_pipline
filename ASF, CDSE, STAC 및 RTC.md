---

title: "Sentinel-1 데이터 수신 경로 비교: ASF, CDSE, STAC 및 RTC 제품"
date: 2026-08-05
tags:

* Sentinel-1
* ASF
* CDSE
* STAC
* RTC
* HyP3
* SAR
* Remote-Sensing

---

# Sentinel-1 데이터 수신 경로 비교: ASF, CDSE, STAC 및 RTC 제품

## 1. 질문 배경

Sentinel-1 영상은 다음과 같은 경로를 통해 검색하거나 내려받을 수 있다.

* ASF DAAC
* CDSE
* STAC API

그러나 이 세 가지는 동일한 종류의 서비스가 아니다.

> **ASF와 CDSE는 실제 Sentinel-1 데이터를 저장하고 배포하는 플랫폼이고, STAC은 위성영상 메타데이터를 검색하고 파일 위치를 표현하는 표준이다.**

사용자가 말한 `CDF`는 문맥상 `CDSE`, 즉 **Copernicus Data Space Ecosystem**을 의미하는 것으로 해석하였다.

---

# 2. ASF, CDSE, STAC의 차이

## 2.1 ASF DAAC

ASF DAAC는 미국 NASA 산하 Alaska Satellite Facility에서 운영하는 SAR 전문 데이터 플랫폼이다.

주요 특징은 다음과 같다.

* Sentinel-1 RAW, SLC, GRD 검색 및 다운로드
* NASA Earthdata 계정 사용
* ASF Vertex 웹 검색
* Python `asf_search` 라이브러리 지원
* Sentinel-1 Burst 검색
* 궤도 방향, 상대궤도, 편파, 촬영 모드 기반 검색
* HyP3를 통한 RTC 및 InSAR 주문형 처리
* OPERA RTC-S1 등 별도 ARD 제품 제공

ASF는 단순한 파일 다운로드 플랫폼을 넘어, SAR 영상 검색과 후처리에 특화되어 있다.

---

## 2.2 CDSE

CDSE는 Copernicus Sentinel 데이터를 제공하는 공식 데이터 생태계다.

정식 명칭은 다음과 같다.

```text
Copernicus Data Space Ecosystem
```

주요 접근 방식은 다음과 같다.

* Copernicus Browser
* OData API
* STAC API
* S3 Object Storage
* Sentinel Hub API
* 주문형 처리 서비스

CDSE에서는 Sentinel-1뿐 아니라 Sentinel-2, Sentinel-3, Sentinel-5P 및 기타 Copernicus 자료를 통합적으로 검색할 수 있다.

CDSE에서 제공되는 Sentinel-1 제품에는 다음과 같은 유형이 포함될 수 있다.

* RAW
* SLC
* GRD
* COG_SAFE
* RTC
* 기타 분석 준비 자료

---

## 2.3 STAC

STAC은 데이터를 보관하는 기관이나 저장소 이름이 아니다.

정식 명칭은 다음과 같다.

```text
SpatioTemporal Asset Catalog
```

STAC은 다음 정보를 표준화된 형태로 제공한다.

* 촬영 날짜와 시간
* 공간 범위
* 위성 및 센서
* 편파
* 궤도 방향
* 상대궤도
* 제품 유형
* 파일 Asset URL
* 썸네일
* 메타데이터
* 실제 다운로드 파일 위치

STAC 검색 결과는 일반적으로 다음 구조로 구성된다.

```text
Collection
└── Item
    ├── Geometry
    ├── Bounding Box
    ├── Properties
    └── Assets
        ├── VV
        ├── VH
        ├── SAFE
        ├── COG
        ├── Thumbnail
        └── Metadata
```

따라서 다음 표현이 더 정확하다.

```text
CDSE에서 STAC API를 이용해 Sentinel-1 영상을 검색한다.
```

다음 표현은 엄밀히는 부정확하다.

```text
CDSE와 STAC이라는 서로 다른 두 저장소에서 영상을 받는다.
```

---

# 3. 비교표

| 구분            | ASF DAAC                  | CDSE                                 | STAC                |
| ------------- | ------------------------- | ------------------------------------ | ------------------- |
| 정체            | SAR 데이터 저장·배포 플랫폼         | Copernicus 공식 데이터 플랫폼                | 메타데이터 및 검색 API 표준   |
| 운영 주체         | NASA ASF                  | European Commission 및 ESA Copernicus | 여러 기관에서 구현          |
| 실제 파일 저장      | 예                         | 예                                    | 구현에 따라 다름           |
| Sentinel-1 검색 | Vertex, `asf_search`, API | Browser, OData, STAC, S3             | `/search` 기반        |
| 인증            | NASA Earthdata            | CDSE OAuth 및 S3 자격증명                 | 제공 기관에 따라 다름        |
| 대표 장점         | SAR 검색 및 HyP3 처리          | 공식 Copernicus 데이터 접근                 | 다양한 위성을 동일한 방식으로 검색 |
| Python 도구     | `asf_search`              | `requests`, `boto3`                  | `pystac-client`     |
| 주요 용도         | 원본 SAR, Burst, RTC, InSAR | 원본 Sentinel 자료 및 ARD                 | 공간·시간 기반 자동 검색      |

---

# 4. ASF와 CDSE에서 받은 원본 GRD는 같은가?

ASF와 CDSE에서 다음과 같이 동일한 Sentinel-1 제품 ID를 검색했다고 가정한다.

```text
S1C_IW_GRDH_1SDV_20260720T213054_20260720T213119_008632_01119F_392D
```

동일한 원본 GRD 제품이라면 기본적으로 다음 정보는 같아야 한다.

* 촬영 시작 시각
* 촬영 종료 시각
* 절대궤도
* 상대궤도
* Ascending 또는 Descending
* 촬영 모드
* 편파
* Datatake ID
* Slice 번호
* 공간 범위

그러나 파일이 바이트 단위로 완전히 동일하다고 단정해서는 안 된다.

차이가 발생할 수 있는 항목은 다음과 같다.

* ZIP 압축 방식
* 파일 패키징 방식
* Manifest 구성
* 체크섬
* 재처리 시점
* Processing Baseline
* Processor Version
* 원본 SAFE와 COG_SAFE 여부

따라서 ASF와 CDSE 제품을 비교할 때는 파일명만 확인하지 말고 다음 항목도 확인해야 한다.

```text
Product Type
Processing Baseline
Processor Version
Generation Time
Absolute Orbit
Relative Orbit
Datatake ID
Slice Number
Measurement Dimensions
Checksum
```

---

# 5. `_COG` 제품의 의미

예시:

```text
S1D_IW_GRDH_1SDV_20260714T213201_..._B126_COG
```

여기서 `_COG`는 일반적으로 Cloud Optimized GeoTIFF 구조로 변환된 Sentinel-1 제품을 의미한다.

COG의 목적은 클라우드나 원격 스토리지에서 전체 파일을 내려받지 않고 필요한 부분만 효율적으로 읽는 것이다.

## 5.1 COG에서 변경되는 사항

* 내부 타일 구조
* Overview 생성
* 압축 방식
* HTTP Range Request 지원
* Manifest 내 경로와 파일 크기
* 체크섬
* 파일 패키징 구조

## 5.2 COG가 의미하지 않는 것

```text
COG ≠ RTC
COG ≠ 지형보정 완료
COG ≠ Sigma0 변환 완료
COG ≠ Gamma0 변환 완료
COG ≠ dB 변환 완료
COG ≠ Speckle Filtering 완료
```

COG는 주로 **파일 저장 구조와 접근 효율성**에 관한 형식이다.

---

# 6. CDSE OData와 CDSE STAC의 차이

CDSE OData와 CDSE STAC은 서로 다른 데이터 저장소가 아니다.

둘 다 CDSE에 저장된 데이터를 검색하는 서로 다른 API 방식이다.

## 6.1 OData 방식

```text
CDSE Catalogue
└── OData 검색
    └── Product UUID 확보
        └── 전체 제품 다운로드
```

OData는 다음 작업에 적합하다.

* 제품명 검색
* Collection 검색
* Product UUID 확보
* 전체 SAFE 다운로드
* 제품 속성 필터링
* 자동 다운로드 파이프라인

---

## 6.2 STAC 방식

```text
CDSE STAC
└── Collection 검색
    └── STAC Item 반환
        └── Asset URL 접근
```

STAC은 다음 작업에 적합하다.

* 날짜 범위 검색
* Bounding Box 검색
* Polygon 검색
* 위성 간 통합 검색
* 공간 Footprint 확인
* Asset 단위 파일 접근
* `pystac-client` 기반 자동화

---

# 7. 사용자의 작업 흐름을 어떻게 알았는가?

이전 답변에서는 사용자의 주요 작업 목적을 다음과 같이 정리하였다.

* 한국과 북한 Sentinel-1 영상 자동 검색
* GRD 다운로드
* RTC/GTC 자체 수행
* 촬영영역 확인
* ASC/DS 확인
* 장기 자동 처리
* 서버 운영

이 내용은 외부 개인정보를 조회해서 알게 된 것이 아니다.

이전 대화에서 사용자가 직접 요청하거나 설명한 내용을 종합한 것이다.

## 7.1 대화에서 확인된 내용

### 한국 및 북한 Sentinel-1 검색

사용자는 다음과 같은 작업을 반복해서 요청하였다.

* 한국 지역 Sentinel-1 검색
* 북한 홍수 지역 영상 검색
* 특정 날짜의 촬영 영상 확인
* Sentinel-1C 및 Sentinel-1D 장면 확인
* 촬영영역과 지역명 정리

### GRD 다운로드

사용자는 다음과 같은 요소를 다뤘다.

* CDSE STAC 검색
* CDSE OData 다운로드
* Sentinel-1 GRD 파일
* SAFE 및 COG_SAFE
* 장면 ID와 다운로드 URL

### RTC/GTC 자체 수행

사용자는 다음 처리 환경과 파이프라인을 설명하였다.

* SARSEN RTC/GTC
* Sentinel-1 RTC 전처리
* 자체 서버 처리
* GAMMA 기반 SAR 처리
* RTC의 Back Projection 속도 개선
* CUDA 개발 계획

### 촬영영역 및 ASC/DS 확인

사용자는 다음 항목을 반복해서 확인하였다.

* 실제 영상 촬영영역
* Bounding Box
* Ascending
* Descending
* 상대궤도
* 촬영 시각
* KST 변환
* Scene 이름

### 자동 처리 서버

사용자가 제공한 발표 및 개발 계획에는 다음 내용이 있었다.

* 단일 서버
* Docker Compose
* 자동 보고서
* 처리 시스템 운영 효율화
* RTC 처리 속도 개선
* CUDA 기반 개발 예정

---

## 7.2 표현상 수정이 필요한 부분

이전 답변에서 이를 다음처럼 단정적으로 표현한 것은 다소 과도했다.

```text
사용자의 주요 목적은 다음과 같다.
```

더 정확한 표현은 다음과 같다.

> 지금까지의 대화에서 확인되거나 합리적으로 추정한 사용자의 현재 Sentinel-1 업무 흐름

특히 다음 항목은 사용자의 단일 문장을 그대로 옮긴 것이 아니라 여러 대화 내용을 종합한 추론이다.

```text
장기적인 자동 처리 서버 운영
```

따라서 명시적 사실과 추론을 구분하여 표현하는 것이 적절하다.

---

# 8. ASF HyP3 RTC와 CDSE RTC의 차이

ASF HyP3 RTC와 CDSE RTC를 비교할 때는 먼저 제품 유형을 구분해야 한다.

다음 세 제품은 서로 다르다.

```text
1. ASF HyP3 On-Demand RTC
2. ASF에서 배포하는 OPERA RTC-S1
3. CDSE Sentinel-1 RTC
```

단순히 `ASF RTC`와 `CDSE RTC`라고만 표현하면 서로 다른 제품이 혼동될 수 있다.

---

# 9. ASF HyP3 RTC

ASF HyP3는 사용자가 선택한 Sentinel-1 GRD를 주문형으로 RTC 처리하는 서비스다.

## 9.1 주요 특징

* 입력: Sentinel-1 GRD
* 주문형 처리
* GAMMA 기반
* UTM 투영
* 출력 해상도 선택 가능
* Sigma0 또는 Gamma0 선택 가능
* Linear Power, Amplitude 또는 dB 선택 가능
* Speckle Filter 옵션
* DEM Matching 옵션
* Layover 및 Shadow Mask 제공
* DEM 및 입사각 부가 레이어 제공 가능

## 9.2 대표 기본 설정

| 항목 | HyP3 기본 설정 예 |
| ------------------- | ----------------- |
| 입력 | Sentinel-1 GRD |
| 프로세서 | GAMMA |
| Radiometry | Gamma0 |
| Scale | Linear Power |
| Pixel Spacing | 30 m |
| Projection | WGS84 UTM |
| DEM | Copernicus GLO-30 |
| DEM Matching | 사용 안 함 |
| Speckle Filter | 사용 안 함 |
| Layover/Shadow Mask | 포함 |

HyP3는 작업 제출 시 일부 설정을 변경할 수 있다는 점이 중요하다.

---

# 10. CDSE RTC

CDSE의 Sentinel-1 RTC는 미리 처리되어 제공되는 분석 준비 자료 성격의 제품이다.

일반적으로 다음 사항을 확인해야 한다.

* 입력 GRD
* 적용 DEM
* Radiometry
* 좌표계
* 출력 Grid
* Pixel Spacing
* Terrain Flattening 방식
* Mask 구성
* 부가 레이어
* Processing Version

CDSE RTC는 HyP3처럼 사용자가 처리 옵션을 선택하여 매번 생성하는 주문형 결과라기보다, 일정한 제품 규격으로 사전에 생성된 Collection으로 이해할 수 있다.

---

# 11. ASF HyP3 RTC와 CDSE RTC를 어디서 확인하는가?

두 제품을 직접 나란히 비교해 주는 단일 공식 페이지는 없다.

따라서 다음 세 단계로 확인해야 한다.

## 11.1 처리 알고리즘 문서 확인

### ASF HyP3

다음 공식 문서 항목을 확인한다.

* Sentinel-1 RTC Product Guide
* RTC Algorithm Theoretical Basis Document
* HyP3 Processing Options
* Naming Convention
* DEM
* Radiometry
* Pixel Spacing
* Speckle Filter
* DEM Matching

### CDSE RTC

다음 공식 문서 항목을 확인한다.

* CDSE Sentinel-1 RTC Collection 설명
* CARD4L 또는 CEOS ARD 관련 제품 규격
* OData Collection 정의
* S3 저장 구조
* Product Metadata
* Processing Baseline

---

## 11.2 동일한 원본 장면으로 제품 확보

비교할 때는 반드시 동일한 Sentinel-1 원본 GRD를 사용해야 한다.

예:

```text
Source GRD:
S1D_IW_GRDH_1SDV_20260719T093955_20260719T094025_...
```

비교 대상:

```text
ASF HyP3 RTC generated from the source GRD
CDSE RTC generated from the same source GRD
```

원본 장면이 다르면 처리 알고리즘 차이와 관측조건 차이를 분리할 수 없다.

---

## 11.3 개별 제품 메타데이터 확인

다운로드한 제품에서 다음 정보를 확인한다.

```text
Source GRD Product ID
Processing Date
Processor Name
Processor Version
Orbit Type
Radiometry
Scale
DEM
DEM Version
Vertical Datum
Projection
Pixel Spacing
Resampling Method
Speckle Filter
DEM Matching
Layover Mask
Shadow Mask
NoData Value
```

---

# 12. CDSE RTC 검색 방법

CDSE OData에서는 `SENTINEL-1-RTC` Collection을 검색할 수 있다.

Python 예시는 다음과 같다.

```python
import requests

url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

params = {
    "$filter": (
        "Collection/Name eq 'SENTINEL-1-RTC' "
        "and ContentDate/Start gt 2026-07-01T00:00:00.000Z "
        "and ContentDate/Start lt 2026-07-02T00:00:00.000Z"
    ),
    "$orderby": "ContentDate/Start desc",
    "$top": 10,
    "$expand": "Attributes,Locations",
}

response = requests.get(url, params=params, timeout=60)
response.raise_for_status()

products = response.json().get("value", [])

for product in products:
    print("Name:", product.get("Name"))
    print("Id:", product.get("Id"))
    print("S3Path:", product.get("S3Path"))
    print("GeoFootprint:", product.get("GeoFootprint"))
    print()
```

---

# 13. CDSE S3에서 RTC Collection 확인

CDSE S3에서는 다음 Prefix 형태로 RTC Collection을 확인할 수 있다.

```text
s3://eodata/Sentinel-1-RTC/
```

AWS CLI 예시:

```bash
aws s3 ls s3://eodata/Sentinel-1-RTC/ \
  --endpoint-url https://eodata.dataspace.copernicus.eu
```

CDSE S3 Access Key와 Secret Key 설정이 필요하다.

---

# 14. GeoTIFF 자체 확인 방법

제품 문서만 보지 말고 실제 GeoTIFF의 메타데이터를 확인하는 것이 가장 확실하다.

## 14.1 전체 정보 확인

```bash
gdalinfo product_VV.tif
```

## 14.2 JSON 저장

```bash
gdalinfo -json product_VV.tif > product_VV_gdalinfo.json
```

## 14.3 통계 확인

```bash
gdalinfo -stats product_VV.tif
```

## 14.4 주요 확인 항목

```text
Coordinate System
Raster Size
Origin
Pixel Size
Data Type
NoData Value
Band Description
Scale
Offset
Metadata
Compression
Block Size
Overview
```

---

# 15. RTC 제품 비교를 위한 최소 체크리스트

| 구분                 | 비교 항목                           |
| ------------------ | ------------------------------- |
| 원본                 | 동일한 Sentinel-1 GRD Product ID인지 |
| 프로세서               | GAMMA, SNAP, 기타                 |
| 버전                 | Processor 및 Plugin Version      |
| 궤도                 | Precise, Restituted, Predicted  |
| 방사보정               | Gamma0 또는 Sigma0                |
| 값 형식               | Linear Power, Amplitude, dB     |
| DEM                | DEM 종류와 버전                      |
| 수직기준               | Ellipsoid 또는 Geoid              |
| 좌표계                | UTM, EPSG:4326 등                |
| 해상도                | 10 m, 20 m, 30 m 또는 Degree Grid |
| Multilooking       | 적용 여부와 Look 수                   |
| Terrain Flattening | 알고리즘 및 정규화 기준                   |
| DEM Matching       | 적용 여부                           |
| Speckle Filter     | 필터 종류와 Window                   |
| Resampling         | Nearest, Bilinear, Cubic 등      |
| Mask               | Layover, Shadow, Border Noise   |
| 부가자료               | DEM, Angle, Area, Mask          |
| NoData             | 값과 적용 방식                        |
| 처리일                | Processing Date                 |
| Grid Alignment     | Pixel Origin 및 Grid 일치 여부       |

---

# 16. 직접 픽셀값을 비교하기 전 주의사항

ASF HyP3 RTC와 CDSE RTC의 픽셀값은 다음 조건을 일치시키기 전에는 직접 비교해서는 안 된다.

```text
Radiometry
Scale
Projection
Pixel Spacing
Grid Origin
Resampling
DEM
Mask
NoData
Source GRD
```

예를 들어 다음 두 자료는 같은 Gamma0 영상처럼 보여도 직접적인 픽셀 단위 비교가 어렵다.

```text
HyP3:
Gamma0 Linear Power
UTM
30 m

CDSE:
Gamma0 Linear Power
Geographic Grid
별도 고정 Grid
```

한쪽 영상을 단순히 재투영하는 것만으로 모든 차이가 제거되지는 않는다.

차이가 남을 수 있는 원인은 다음과 같다.

* Terrain Flattening 구현 차이
* DEM 전처리 차이
* 재표본화 이력
* 궤도 파일 차이
* Mask 처리 차이
* Border Noise 제거 차이
* NoData 처리 차이
* Grid Alignment 차이

---

# 17. 사용자 파이프라인에 적합한 역할 분담

사용자의 Sentinel-1 작업 흐름에는 다음 구성이 적합하다.

```text
1. CDSE STAC
   └── 날짜, 영역, 궤도, 편파 기반 장면 검색

2. STAC Item 확인
   ├── Product ID
   ├── Footprint
   ├── ASC/DS
   ├── Relative Orbit
   └── Asset 종류 확인

3. 원본 SAFE 다운로드
   ├── CDSE OData
   ├── CDSE S3
   └── ASF를 대체 경로로 활용

4. 자체 RTC/GTC 수행
   ├── SARSEN
   ├── GAMMA
   ├── SNAP
   └── 자체 Python Pipeline

5. 결과 저장
   ├── GeoTIFF
   ├── COG
   ├── Linear
   ├── dB
   └── 통계 및 홍수 분석
```

---

# 18. 목적별 권장 경로

| 목적                    | 권장 방식                   |
| --------------------- | ----------------------- |
| 날짜와 공간 기반 빠른 검색       | STAC                    |
| Copernicus 공식 원본 SAFE | CDSE OData 또는 S3        |
| Sentinel-1 원본 대체 다운로드 | ASF                     |
| Burst 검색              | ASF                     |
| InSAR Pair 검색         | ASF                     |
| 주문형 RTC               | ASF HyP3                |
| 사전 생성 RTC Collection  | CDSE RTC                |
| 자체 RTC/GTC            | 원본 GRD SAFE             |
| 클라우드 부분 읽기            | COG                     |
| ASC/DS 및 Footprint 확인 | STAC Metadata           |
| 장기 자동화                | STAC 검색 + OData/S3 다운로드 |

---

# 19. 최종 요약

```text
ASF
= NASA에서 운영하는 SAR 전문 데이터 저장·검색·처리 플랫폼

CDSE
= Copernicus Sentinel 데이터의 공식 제공 생태계

STAC
= 영상을 검색하고 실제 Asset 위치를 표현하는 표준 API

COG
= 클라우드 접근에 최적화된 GeoTIFF 저장 구조

HyP3 RTC
= ASF에서 사용자가 옵션을 선택해 생성하는 주문형 RTC

CDSE RTC
= CDSE에서 일정한 제품 규격으로 제공하는 사전 처리 RTC Collection
```

따라서 비교 대상은 단순히 다음과 같이 설정해서는 안 된다.

```text
ASF vs CDSE vs STAC
```

보다 정확한 비교 단위는 다음과 같다.

```text
ASF Original GRD SAFE
vs
CDSE Original GRD SAFE
vs
CDSE COG_SAFE
vs
ASF HyP3 RTC
vs
ASF OPERA RTC-S1
vs
CDSE Sentinel-1 RTC
```

RTC 제품을 연구에 이용하려면 반드시 동일 원본 GRD를 기준으로 방사보정 방식, DEM, 좌표계, 해상도, Grid, Mask 및 처리 버전을 확인해야 한다.
