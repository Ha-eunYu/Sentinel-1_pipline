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

## S1C/S1D 지원 — 소스 레벨 분석과 해법 (2026-07-24)

이 프로젝트 데이터는 전부 **Sentinel-1C/D COG GRD**다. sarsen/xarray-sentinel의
버전에 따라 되고 안 되고가 갈려, 실제 소스를 읽어 원인을 확정하고 해법을 잡았다.

### A. 왜 구버전(PyPI sarsen 0.9.3 + xarray-sentinel 0.9.5)은 실패하는가 — 소스 근거

1. **애노테이션 파서 정규식이 A/B만 인식** — `xarray_sentinel/esa_safe.py`
   `parse_annotation_filename()`:

   ```python
   re.match(r"([a-z-]*)s1[ab]-([^-]*)-[^-]*-([^-]*)-([\dt]*)-", ...)   # 0.9.5
   ```

   `s1[ab]`라 `s1c-…`/`s1d-…` 파일명은 매치 실패.
2. **매치 실패 파일은 조용히 스킵** — 같은 파일 `parse_manifest_sentinel1()`
   (163~172행)이 각 dataObject에 위 함수를 부르고 `except ValueError: continue`.
   즉 S1C는 **모든 애노테이션/측정/캘리브레이션 파일이 files 딕셔너리에서 빠진다**
   → 그룹 0개(`Invalid group 'IW/VV'`). 게다가 `@functools.lru_cache`(106행)라
   한 번 빈 결과가 캐시된다. → **`sarsen_pin`(구스택)에서 GCP 빈 결과·크래시의 원인.**
3. **궤도 시각 ns 단정** — `sarsen/orbit.py`(0.9.3, 37/70/82행)
   `assert time.dtype.name in ("datetime64[ns]", ...)`. 최신 pandas는 `datetime64[us]`
   를 주므로 AssertionError. → modern 스택에서 실행조차 막던 요인(패치로 우회했었음).

즉 구버전은 **S1C/D 출시 이전 코드**이고 개발이 중단돼, 패치를 하나 넘으면 다음
비호환이 계속 나온다(정규식→ns→GCP→interp).

### B. 해법 — sarsen 0.9.6 + xarray-sentinel main(≥0.9.6) + 모던 스택

로컬에 확보한 최신 소스가 이 문제들을 이미 해결하고 있다(소스로 확인):

- **`xarray-sentinel-main`**: `esa_safe.py`의 정규식이 **`s1[abcd]`** — S1A/B/**C/D**
  전부 지원(유일 하드코딩 지점). GCP도 XSD(`resources/sentinel1/*.xsd`) 기반으로 재작성.
- **`sarsen-0.9.6`**(정식 릴리스, `sarsen-0.9.6.tar.gz`): `pyproject`가
  **numpy≥1.26 / pandas≥2.2 / xarray≥2023.12 / xarray-sentinel≥0.9.6**을 요구
  → **모던 스택 전용**. apps.py가 대폭 리팩터(`OrbitPolyfitInterpolator`,
  `do_terrain_correction`, `product.interp_sar`)돼 pandas2 datetime을 자체 처리.

**설치(모던 env `sarsen_clean`: numpy2.3/pandas2.3/xarray2025.4 유지, `--no-deps`)**:

```bash
# xarray-sentinel은 반드시 editable(-e) — 일반 설치 시 wheel에 XSD 리소스가
# 빠져 GCP 파싱이 URLError(s1-level-1-product.xsd 없음)로 실패한다.
conda run -n sarsen_clean pip install --no-deps --force-reinstall -e xarray-sentinel-main/xarray-sentinel-main
conda run -n sarsen_clean pip install --no-deps --force-reinstall    sarsen-0.9.6
```

설치 결과: `sarsen 0.9.6`, `xarray-sentinel 999`(main). 이후 `rtc_sarsen.py`를
`sarsen_clean`에서 그대로 실행.

### C. rtc_sarsen.py의 호환 패치(방어적)

`rtc_sarsen.py`의 몽키패치는 **버전 감지 후 필요할 때만** 적용되도록 고쳤다:
`s1[a-d]` 정규식 패치는 main(abcd)에선 무해, ns 패치는 클래스명이 바뀐 0.9.6에선
자동으로 건너뛴다(`OrbitPolyfitIterpolator` 부재 감지). 따라서 rtc_sarsen.py는
구/신 버전 어디서 돌려도 안전하다.

### D. ✅ 검증 완료 (2026-07-27): sarsen으로 S1C RTC 가능

**"SARSEN으로 RTC를 진행할 수 있는가?" → 가능하다(실증).** sarsen 0.9.6 +
xarray-sentinel main + 모던 스택으로 이 프로젝트의 S1C COG GRD를 실제로
지형보정해 **유효한 γ0(dB) 출력**을 얻었다.

검증 씬: `754B`(7/3 09:22 UTC 상승, S1C, 해안/해상 위주). 처리 15.8분
(지형보정+dB, `PROCESS_SECONDS=947.9`). 산출물 `downloads/rtc_grd_bench_sarsen/
S1C_..._754B_..._rtc_db.tif`:

| 지표 | 값 |
| --- | --- |
| 격자 | 11848×5864, EPSG:4326, float32, nodata=NaN |
| 유효 픽셀 | 27,474,257 (39.5% — 스와스 밖은 nodata) |
| dB 분포 | min −48.2 / p50 −20.1 / mean −20.3 / p95 −13.4 / max 32.0 |
| 물(<−16dB) | 84.5% (해상 위주 씬과 부합) |

빈 NaN(구버전 실패)도, 쓰레기도 아닌 **정상 SAR γ0 dB 분포** → S1C 읽기 장벽
(정규식·GCP·footprint)과 geocoding·interp까지 모두 정상 통과.

**남은 검증/후속 (진행 상황)**

- ✅ **교차검증 완료(2026-07-27)**: 같은 COP30로 sarsen vs SNAP(754B) 대조 →
  **지오코딩 위치 완전 일치(시프트 0, r 0.88)**, γ0 dB는 중앙값 **+0.96 dB** 차·
  r 0.88(스펙클 미필터+해상도차 감안 예상 범위). 상세는
  [RTC_BENCHMARK_KR.md](RTC_BENCHMARK_KR.md) §2.5. → 고정 −16dB 탐지 전 ~1 dB
  오프셋만 반영(또는 Otsu 적응형)하면 됨.
- 🔄 **속도 비교(B) 진행 중**: 용량 버킷별 9장 SNAP vs sarsen(단독 실행). 결과는
  [RTC_BENCHMARK_KR.md](RTC_BENCHMARK_KR.md) §3.
- ⚠️ **DEM 주의**: SNAP 자동 Copernicus DEM은 이 데이터 일부 씬에서 타일을 일부만
  받아 무효 출력(재현됨). sarsen은 로컬 COP30(D:)을 직접 써서 이 문제 없음
  ([RTC_BENCHMARK_KR.md](RTC_BENCHMARK_KR.md) §2).
- ✅ `sarsen_pin`(pandas1.5 핀 env) **삭제 완료**(막다른 길: main이 pandas≥2.2 요구).
- rtc_sarsen.py 기본 실행 env는 `sarsen_clean`(0.9.6+main).
