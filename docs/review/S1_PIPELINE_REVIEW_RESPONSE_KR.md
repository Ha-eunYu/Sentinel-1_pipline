# 리뷰 요청 회신 — 파이프라인 코드 실측 점검 결과 (2026-07-29)

[S1_PIPELINE_REVIEW_KR.md](S1_PIPELINE_REVIEW_KR.md)의 9개 항목을 파이프라인
코드와 산출물로 직접 확인했습니다. 요청 순서대로 **② → ④ → ①** 을 먼저 다루고,
나머지는 뒤에 정리했습니다.

리뷰 문서의 부록이 "이미 처리된 항목이 있을 수 있다"고 적어 둔 대로, **③은
파이프라인 본선에서 이미 해결돼 있었고**(리뷰가 본 임계값은 파이프라인 산출물이
아님), **①의 조치 제안은 이미 수행된 상태**였습니다. 반면 **②는 지적이 전부
사실이며, 리뷰가 짚은 것보다 한 단계 위에 근본 원인이 하나 더 있습니다.**

## 검증 방법

- 코드: `F:/06_SAR_system/S1` 의 자체 작성 Python 62개 + SNAP 그래프 XML 3개
  (vendored `esa-snappy-master/`·`sarsen-*/`·`xarray-sentinel-*/`는 제외)
- 실측: `downloads/rtc_grd/*_rtc_db.tif` 58개, 원본 SAFE zip 52개의
  `manifest.safe`, `downloads/water_otsu/otsu_thresholds.csv`
- 감사 도구를 재현 가능하게 저장소에 추가:
  [footprint/audit_rtc_bbox_vs_footprint.py](../../s1/tools/audit/audit_rtc_bbox_vs_footprint.py)
  → `footprint/rtc_bbox_vs_footprint_audit.csv`, `footprint/rtc_phantom_land_audit.csv`
- 실행 환경: `conda run -n s1_pipeline`(shapely+rasterio) / `-n s1_snappy`(rasterio)

## 판정 요약

| # | 항목 | 판정 | 한 줄 결론 |
|---|------|------|-----------|
| 1 | footprint 필터 시점·재검증 | 🟢 **이미 처리** | 필터는 기본 동작(7/23 도입), 전량 재감사도 7/22에 완료. 잔여 리스크는 무효 확정된 **래스터 파일이 무표시로 남아 있는 것** |
| 2 | RTC footprint 소실 | 🔴 **사실 확정 + 근본 원인 추가** | 58개 전부 회전항 0. 게다가 footprint는 RTC가 아니라 **STAC 검색 요약 단계에서 이미 버려짐** |
| 3 | 임계값 근거 | 🟢 **해당 없음** | 파이프라인은 타일기반 split Otsu 자동 + CSV 로그. 리뷰가 본 −13/−11/−10은 QGIS 수동값이며 **전부 파이프라인 Otsu보다 느슨** |
| 4 | 전/후 차분 | 🟡 **차분은 있음, 그 산출물은 차분 전** | `Intersection.geojson` 12.163 km²는 **차분 전 단일시기 수체**. 북한에서 차분을 포기한 것은 문서화된 의도적 선택 |
| 5 | 공통 촬영영역 교집합 | 🟡 **픽셀 단위는 구현, 지역별 관측률은 없음** | 두 시점 교집합은 마스크로 반영됨. 군별 관측률·경고는 미구현 |
| 6 | shadow/layover | 🔴 **사실 확정** | 3개 그래프 전부 `saveLayoverShadowMask=false` |
| 7 | MMU 필터 | 🔴 **사실 확정(로컬), GEE엔 있음** | 수체 마스크에 MMU/형태학 연산 없음. GEE 경로엔 `connectedPixelCount` 있음 |
| 8 | 정확도 검증 | 🔴 **사실 확정** | 광학 대조·오탐률 산출 없음 |
| 9 | 계보·파라미터 로깅 | 🟡 **부분** | `update_tags` 호출 0건(래스터 내부 기록 없음). Otsu 경로만 CSV 로그 |

---

## ② RTC 산출물이 실제 footprint를 잃어버림 🔴

### 지적은 전부 사실입니다

`downloads/rtc_grd/*_rtc_db.tif` **58개 전부** geotransform 회전항 `b=d=0`.
리뷰가 인용한 씬을 그대로 확인했습니다.

```text
S1A_..._0999_COG_rtc_db.tif
  transform: a=8.983152841195215e-05 b=0.0 c=125.59313093582375
             d=0.0 e=-8.983152841195215e-05 f=35.91481203310183
  bounds: (125.59313, 33.77071) ~ (128.69196, 35.91481)  = 축정렬 직사각형
```

사이드카도 없습니다. [prepro_grd_gpt.py:212-220](../../s1/preprocess/prepro_grd_gpt.py#L212-L220)의
`Write` 노드는 GeoTIFF 한 장만 내보내고, footprint GeoJSON을 쓰는 코드는
파이프라인 어디에도 없습니다.

### 근본 원인은 RTC보다 한 단계 위입니다 (리뷰에 없는 부분)

footprint는 **RTC 처리 때 소실되는 게 아니라, STAC 검색 요약을 만드는 시점에
이미 버려집니다.** [stac/search_s1.py:99-113](../../s1/stac/search_s1.py#L99-L113)의
`extract_s1_summary()`가 `bbox=getattr(item, "bbox", None)`만 담고
`item.geometry`는 담지 않습니다. 실측으로 확인했습니다.

```text
downloads/s1_stac_list_manifest_grd.json candidate 필드:
  assets, bbox, datetime, id, instrument_mode, orbit_state, platform,
  polarization, product_href, product_id, product_type, relative_orbit, zipper_url
  -> geometry 저장? False
```

즉 ①의 footprint 필터는 검색 시점에 `item.geometry`를 **쓰고 나서 버립니다.**
같은 값을 요약에 한 줄 더 담기만 하면 하류 전체가 실제 footprint를 쓸 수
있는데, 지금은 그 뒤 어느 단계에서도 재사용이 불가능합니다.

프로젝트에 footprint 기록이 딱 하나 있습니다 —
[footprint/export_frames_geojson.py](../../s1/footprint/export_frames_geojson.py) 가
CDSE STAC을 **재조회**해 만드는 `downloads/s1_frames_report*.geojson`
(`geometry_source="stac_footprint"`). 그런데 대상이 "manifest 후보 ∪ 다운로드
폴더에 zip이 남은 씬"이라, manifest가 실행마다 덮어써지고(현재 타깃은 7/1·7/20
둘뿐) RTC 후 zip이 삭제되면 씬이 목록에서 사라집니다. 실제로 이 파일에는 29씬만
있고, **RTC 58씬 중 17씬만 매칭**됩니다.

### 실질 피해량 (신규 정량화)

원본 zip이 남은 43씬에 대해 `manifest.safe` footprint를 복원해 RTC bbox와
나란히 대조했습니다.

| 지표 | 값 |
|---|---|
| bbox가 "촬영했다"고 주장하는 한반도 육지 (43씬 합) | **1,006,658 km²** |
| 그중 실제로는 촬영하지 않은 **유령 육지** | **262,725 km² (26.1%)** |
| 씬별 유령비율 범위 | 7.5% ~ **55.9%** |
| 유령비율 최악 | `8E98`(7/1)·`1A5A`(7/13) 각 55.9% (4,779 km²) |

씬 단위 예시 — 리뷰의 `3167`·`5C3C` 사례와 같은 구조입니다.

| 씬 | bbox 한반도 겹침 | 실제 footprint | 유령 육지 |
|---|---|---|---|
| `1A5A` (7/13) | 14.65% | **8.94%** | 4,779 km² (55.9%) |
| `8E98` (7/1) | 14.65% | **8.95%** | 4,779 km² (55.9%) |
| `2DA8` (7/15) | 17.50% | **12.41%** | 4,955 km² (48.1%) |
| `9A73` (7/3) | 21.70% | **16.78%** | 5,853 km² (43.9%) |
| `74FD` (7/6) | 24.94% | **19.86%** | 6,218 km² (41.8%) |

현재 RTC 58씬 안에는 `bbox_false_positive`(bbox는 겹침·footprint는 0%)가
**0건**입니다. 리뷰가 겪은 `3167`·`5C3C` 같은 완전 오판 씬들은 ①의 재감사에서
이미 격리됐기 때문입니다(→ ①절). 남은 문제는 "0%냐 아니냐"가 아니라 **어느
행정구역을 찍었는지 판정할 때 최대 56%가 유령**이라는 쪽입니다.

### 리뷰의 두 번째 제안(유효 픽셀 마스크)은 실현 가능합니다

RTC tif는 `nodata=None`이지만 실무상 0이 무효값이고(파이프라인 전체가
`db != 0`으로 판정), 실제 형상이 픽셀에 그대로 남아 있습니다.

```text
S1C_..._93FC_COG_rtc_db.tif (37102x21261)
  유효(0 아님) 픽셀 비율 = 56.0%          <- bbox 대비 실제 촬영 면적
  좌상/우상/좌하/우하 코너블록 유효율 = 각 0.0%   <- 평행사변형의 삼각형 여백
```

네 코너가 전부 비어 있으니 유효 픽셀 마스크에서 실제 외곽선을 뽑을 수 있습니다.
다만 **원본 `manifest.safe`가 남아 있는 43씬은 그쪽이 정확하고 훨씬 쌉니다.**

### 하류 오판의 코드상 출처

[downloads/rtc_grd/get_tif_shooting_area.py:122-139](../../downloads/rtc_grd/get_tif_shooting_area.py#L122-L139)
의 `raster_corner_polygon()`이 래스터 네 모서리를 지리좌표로 변환해 footprint를
만들고, 이걸 행정경계와 중첩해 "촬영 지역"을 산출합니다. docstring은 "회전된
GeoTIFF도 처리할 수 있도록 단순 bounds가 아니라" 라고 적혀 있지만, **RTC 입력에는
회전항이 없으므로 결과가 정확히 bbox**입니다. 리뷰의 제주·고성군 오판이 나온
지점입니다.

### 권고 (비용순)

1. `extract_s1_summary()`에 `geometry=getattr(item, "geometry", None)` 한 줄 추가
   → manifest부터 footprint가 보존되고 ②의 하류 문제 대부분이 사라집니다.
2. RTC 출력 시 `<씬ID>_footprint.geojson` 사이드카 저장 (파일당 수 KB).
   원본 zip이 아직 52개 남아 있으니 **기존 43씬은 지금 소급 생성이 가능**합니다.
3. `get_tif_shooting_area.py`가 래스터 코너 대신 사이드카 footprint를 참조.
4. 원본이 없는 15씬(`0999`·`FAC3`·`A392`·`D578`·`1A5D`·`303C`·`3A16`·`02C6`·
   `194A`·`BE31`·`E265`·`BB45`·`6EBE`·`3043`·`794A`)은 CDSE STAC 재조회가 유일한
   복원 경로입니다. **이 중 `303C`는 리뷰 ③ 표의 임계값 대상 씬**입니다.

---

## ④ 전/후 차분(상시 수체 제거) 단계 존재 여부 🟡

### 결론: 차분 단계는 있습니다. 그리고 리뷰가 본 산출물은 차분 **전** 단계입니다

리뷰가 남긴 두 갈래 중 **①번(차분 전 단계라 당연한 것)** 이 맞습니다.

파이프라인의 차분 구현 —
[detect_flood_grd_v2.py:214-217](../../s1/tools/water/detect_flood_grd_v2.py#L214-L217):

```python
baseline_water = valid & (base_db < args.db)
total_water    = valid & (post_min < args.db)
relaxed        = valid & total_water & (~baseline_water)      # 상시수체 제거
strict         = relaxed & (diff <= args.drop)                # + 하락폭 -3 dB
```

세 단계를 **동시에** 내보내고 파일명이 다릅니다(`flood_water_total_*` /
`_relaxed_*` / `_strict_*`). 즉 `total`이 차분 전, `relaxed`·`strict`가 차분 후
입니다. [detect_flood_grd.py](../../s1/tools/water/detect_flood_grd.py)(v1)는 처음부터 3중조건
보수판만 냅니다.

### 12.163 km²가 차분 전이라는 근거 3가지

1. **리뷰 자신의 산술이 이미 답입니다.** 12.163 − 4.4443 = **7.719 km²** →
   리뷰가 정한 "차분 반영" 구간(7~8 km²대)에 정확히 들어옵니다. 즉 12.163은
   차분 전 값이고, 차분 후 값이 7.72입니다. 두 후보 수치가 같은 데이터의
   before/after였습니다.

2. **파이프라인 문서가 이 산출물의 성격을 명시해 뒀습니다.**
   [FLOOD_NORTH_KOREA_KR.md](../flood/FLOOD_NORTH_KOREA_KR.md) 7절 "참고 — baseline 무관
   단일시기 수체 지도"가 `flood_water_total_<날짜>` 계열을 "변화가 아니라 상태"로
   규정하고, **"레이더 그림자·상시수체·바다 포함이므로 판독 시 감안"** 이라고
   못 박아 뒀습니다. 리뷰가 측정한 상시수체 36.5% 포함은 이 설명과 일치합니다.

3. **실측 재현.** 이천군 근사 AOI(126.70~127.10°E, 38.28~38.62°N)에서 7/25
   관측(`mosaic_20260725_o008705.vrt`, 59A8 포함)과 6/26 관측
   (`mosaic_20260626_o008282.vrt`)을 직접 비교했습니다. 두 시점 공통 관측 100%:

   | 임계값 | 7/25 수체 | 6/26 수체 | 교집합(상시) | 차분 후 신규 |
   |---|---|---|---|---|
   | −14.85 dB (파이프라인 Otsu) | 29.563 km² | 15.774 | 14.274 (**48.3%**) | 15.289 |
   | −10 dB (QGIS 수동) | 56.046 km² | 213.372 | 33.691 (**60.1%**) | 22.355 |

   상시수체 비율이 48~60%로, 리뷰의 36.5%와 같은 크기대입니다(경계 폴리곤·
   임계값·baseline 날짜가 달라 값 자체는 다릅니다 — AOI가 이천군 실경계가 아닌
   사각형 근사라 절대 면적은 리뷰의 약 2배입니다).

### before 영상 선정 기준

두 경로가 있습니다.

- **v3 합성 baseline**: [build_baseline_composite_grd.py](../../s1/tools/water/build_baseline_composite_grd.py)
  가 pre-event 최신관측을 합성(`s1_rtc_db_composite_latest_pre.vrt`). `--fallback-dates`
  로 정식기간(≤7/3) 관측이 없는 빈 구역만 7/4·7/6·7/7로 채웁니다.
- **동일궤도 단일 쌍**(정공법): `detect_flood_grd_v2.py --baseline <pre 모자이크>
  --tag`. 같은 relative orbit의 pre 1장 ↔ post 1장만 차분합니다
  (FLOOD_NORTH_KOREA_KR.md 5절: 7/14↔7/1, 7/18↔7/6, 7/19↔6/25).

### 왜 북한에서 차분을 안 썼는가 — 누락이 아니라 문서화된 의도적 선택

[FLOOD_NORTH_KOREA_KR.md](../flood/FLOOD_NORTH_KOREA_KR.md) 0·6절이 결론을 명시해
뒀습니다: **"마른 pre-event baseline이 애초에 존재하지 않는다."** SPN 「오늘의
북한 날씨」로 교차검증한 결과 baseline 후보 6/25·7/1·7/6이 **전부 강수일**
이었고, SAR 습윤도 진단에서도 7/1이 7/13보다 4.1배 넓게 젖어 있었습니다
(13,114 vs 3,189 km²). 그래서 문서는 북한 침수량 정량화를 포기하고 7절의
단일시기 수체로 후퇴할 것을 권고합니다.

즉 **차분 누락이 아니라, 차분의 전제가 깨져서 의도적으로 차분을 포기한 것**입니다.
문제는 그 전제가 보고 단계까지 전달되지 않아, "상시수체 포함"이라는 성격이 붙은
채로 침수 면적처럼 읽힌 것입니다.

### 상시 수체 마스크 옵션 — 로컬엔 없고 GEE 경로엔 있습니다

- 로컬 SAR 차분 경로에 JRC Global Surface Water 사용은 없습니다. 대신
  [build_baseline_water_grd.py:149](../../s1/tools/water/build_baseline_water_grd.py#L149)가
  HAND(`dB < 임계 AND HAND < 10 m`)를 쓰고, `water_frequency_grd.tif`
  (관측일수 중 물로 잡힌 횟수)로 상시수체 후보를 뽑을 수 있습니다.
- **GEE 경로에는 이미 구현돼 있습니다** —
  [gee/geeflood/sar.py:88-91](gee/geeflood/sar.py#L88-L91):
  `JRC/GSW1_4/GlobalSurfaceWater` seasonality ≥ 10 을 상시수체로 제거하고,
  Otsu 자동 임계 + `connectedPixelCount(25).gte(min_connected)` MMU까지
  한 번에 적용합니다. 로컬 파이프라인에 이식할 기성 참조 구현이 사내에 있는
  셈입니다.

---

## ① footprint 필터 적용 시점과 과거 산출물 재검증 🟢

리뷰의 체크리스트 5개 전부 확인했고, **조치 제안(일괄 재검증)은 이미 수행된
상태**였습니다.

| 확인 항목 | 결과 |
|---|---|
| `exclude_non_korea`가 기본 동작인가 | ✅ **기본 True** — [stac/search_s1.py:151](../../s1/stac/search_s1.py#L151) |
| 언제부터 적용됐나 | 커밋 `429d717`, **2026-07-23 12:51 KST**. 이후 `e687730`(7/27) footprint 모듈 통합 → `0baa1cf`(7/28) `footprint/` 폴더 정리 |
| 경계 파일이 `Korea_Peninsula.geojson`인가 | ✅ [footprint/footprint_aoi.py:46](../../s1/footprint/footprint_aoi.py#L46). 제주 포함도 실측 확인 — `93DD` footprint 겹침을 독립 계산하니 **5.27%**, 문서에 기록된 값과 정확히 일치 |
| 느슨한 bbox 검색 + 사후 정밀 판정 구조인가 | ✅ [main_s1_list_grd.py:117-121](../../s1/tools/download/main_s1_list_grd.py#L117-L121) — `KOREA_SEARCH_BBOX = [123.0, 32.5, 131.5, 43.5]`, `intersects_geojson=None`. 정밀 판정은 검색 후 `touches_korea` |
| 필터 이전 산출물이 남아 인용되는가 | ⚠️ **아래 참조** |

### 재검증은 이미 끝나 있습니다

[SCENE_FOOTPRINT_REAUDIT_KR.md](../pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md)가 **필터 도입
하루 전인 2026-07-22**에 `downloads/sentinel1_grd/` zip 79개 전량의 footprint를
CDSE STAC에서 재조회해 재대조한 기록입니다. 리뷰가 제안한 절차보다 넓습니다.

- 7/8 `1.64 km²`·7/10 `69.06 km²`를 **물 픽셀 point-in-polygon으로 한반도
  내부 0.0%(표본 3,000개 중 0개)** 확정 → 무효 처리
- RTC+GTC까지 완료됐던 7씬을 `downloads/excluded_china_japan/`으로 격리
  (14개 파일 현존 확인). 감사용으로 삭제하지 않고 보존
- 미처리 13개 zip은 배치 대상에서 삭제(79→66)
- 7/17 근거(`D298`·`3191`·`4C7C`, 궤도 003704)도 7/28에 추가 무효 확정 —
  본 감사에서 독립 재확인: `3191`·`4C7C` 는 **bbox·footprint 모두 0.00%**

그래서 재검증 범위 질문의 답은 **"신규 재검증은 불필요, 이미 전량 완료"** 입니다.

### 남은 리스크 — 무효 확정된 래스터가 무표시로 남아 있습니다

문서에는 ❌로 표시됐지만, **파일 자체는 유효 산출물과 구분 없이 그대로**
있습니다. 파일명만 보고 QGIS로 열면 무효인지 알 수 없습니다.

| 남아 있는 무효 산출물 | 내용 |
|---|---|
| `downloads/water/flood_water_relaxed_20260708.tif` | 7/8 1.64 km²의 근거 (한반도 내부 0%) |
| `downloads/water/flood_water_relaxed_20260710.tif` | 7/10 69.06 km²의 근거 (동일) |
| `downloads/water/diff_min_2026070{8,10}_vs_baseline.tif` | 위 두 건의 dB 차분 |
| `downloads/water_otsu/flood_water_total_20260716_o003704.tif` | `3191`·`4C7C` 단독 산출물 — 전량 먼바다 |
| `downloads/water_otsu/otsu_thresholds.csv` 의 `20260716,003704` 행 | `fallback,-16.0,...,209.697 km²` — **무효 표시 없이 유효 행들과 나란히** 있음 |

필터 도입(7/23) 이전에 생성된 `downloads/water*` 래스터는 총 **110개**입니다.
개별 재계산은 불필요하지만(근거 씬 단위로 이미 판정 완료), 무효 확정분에
`_INVALID` 접미사를 붙이거나 별도 폴더로 격리하고 CSV에 무효 열을 추가하는
쪽을 권합니다. `excluded_china_japan/` 격리와 같은 방식이면 일관됩니다.

---

## ③ 수체 임계값 결정 로직·근거 🟢 (해당 없음 — 단, 중요한 대조 결과)

**파이프라인 본선은 이미 자동 임계값입니다.**
[build_water_per_date_otsu.py](../../s1/tools/water/build_water_per_date_otsu.py)가
Martinis(2009)·Chini(2017) 방식의 **타일기반 split Otsu**를 궤도별로 적용하고,
근거를 `downloads/water_otsu/otsu_thresholds.csv`에 남깁니다 — 임계값,
채택/후보 타일 수, 분리도 η, `method`(tile-otsu/fallback), 면적, 유효 픽셀 수.
전역 Otsu가 육지 분포를 갈라 −8 dB로 튀는 문제, 이봉 타일 부족·임계값이
정상 범위(−25~−10 dB)를 벗어날 때의 fallback까지 처리돼 있습니다.

**리뷰가 본 −13/−11/−10은 파이프라인 산출물이 아닙니다.** 코드 전체에
`polgonize`/`polygonize` 문자열이 **0건**입니다(QGIS GUI 작업의 흔적).

### 대조 결과: 수동 임계값 5건 전부 파이프라인 Otsu보다 느슨합니다

리뷰의 씬을 궤도로 역추적해 같은 관측의 Otsu 값과 대조했습니다.

| 씬 | 날짜(궤도) | 파이프라인 Otsu | QGIS 수동 | 차이 |
|---|---|---|---|---|
| `303C` | 6/26 (o008282) | −15.05 dB | −13 dB | **+2.05 dB 느슨** |
| `8EF1` | 7/14 (o003675) | −12.15 dB | −11 dB | +1.15 dB 느슨 |
| `392D` | 7/20 (o008632) | −14.35 dB | −13 dB | +1.35 dB 느슨 |
| `DD29` | 7/20 (o008632) | −14.35 dB | −10 dB | **+4.35 dB 느슨** |
| `59A8` | 7/25 (o008705) | −14.85 dB | −10 dB | **+4.85 dB 느슨** |

5건 전부 **면적 과대 방향**입니다. 리뷰가 ⑦에서 관찰한
`polgonize_clip_DD29_-10` 의 폴리곤 198,458개는 이 4.35 dB 과탐으로 설명됩니다.

### 민감도 (리뷰 ③의 마지막 체크 항목)

이천군 근사 AOI, 7/25 관측 기준으로 임계값만 바꿔 측정했습니다.

| 임계값 | 수체 면적 | Otsu 대비 |
|---|---|---|
| −16 dB | 27.878 km² | 0.94x |
| **−14.85 dB (Otsu)** | **29.569 km²** | 1.00x |
| −13 dB | 32.534 km² | 1.10x |
| −11 dB | 40.023 km² | 1.35x |
| −10 dB | 56.097 km² | **1.90x** |

Otsu 근처에서는 ±1 dB가 약 ±5~7%지만, −11 → −10 한 칸에서 **+40%**가
튀어오릅니다. 즉 수동으로 쓴 −10 dB는 곡선이 폭발하는 불안정 구간이고,
"±1 dB 변동폭 병기"는 Otsu 값 근처에서만 의미가 있습니다.

**남아 있는 하드코딩**: `DB_THRESHOLD_DEFAULT = -16.0`
([detect_flood_grd_v2.py:80](../../s1/tools/water/detect_flood_grd_v2.py#L80),
[build_baseline_water_grd.py:36](../../s1/tools/water/build_baseline_water_grd.py#L36),
[footprint/verify_scene_footprint.py:47](../../s1/tools/audit/verify_scene_footprint.py#L47)),
`FALLBACK_DB_DEFAULT = -16.0`. 차분 경로(v2)는 아직 Otsu를 쓰지 않으므로,
Otsu 경로의 임계값을 v2에 주입하면 두 경로의 일관성이 확보됩니다.

---

## ⑤ 전/후 공통 촬영영역 교집합 🟡

- **픽셀 단위 교집합은 구현돼 있습니다** —
  [detect_flood_grd_v2.py:211](../../s1/tools/water/detect_flood_grd_v2.py#L211):
  `valid = np.isfinite(post_min) & np.isfinite(base_db)`. 두 시점 모두 유효한
  픽셀만 판정에 들어가므로, "before가 안 덮은 구역을 새 물로 오인"하는 함정은
  차단됩니다. 분석 격자도 `baseline ∩ post 씬 합집합`으로 좁힙니다(:138-173).
  교차 커버리지 %도 출력합니다(FLOOD_NORTH_KOREA_KR.md 5절의 39.3/34.1/43.7%).
- **지역별 관측률 산출·속성 내보내기·저관측 경고는 없습니다.**
  [split_flood_area_nk_sk.py](../../s1/tools/water/split_flood_area_nk_sk.py)는 위도 38.3°로 남/북만
  단순 이분합니다. 행정구역 단위 관측률을 내는 코드는
  `downloads/rtc_grd/get_tif_shooting_area.py` 하나인데 **그게 bbox 기반(②)**
  이라 그 수치를 그대로 믿을 수 없습니다.
- 리뷰가 좋은 실무로 꼽은 `_fin.gpkg`의 군별 관측률이 수작업이라는 관찰은
  맞습니다. ② 1~3번 권고를 적용하면 `after_footprint ∩ before_footprint ∩
  행정구역`을 자동 산출할 수 있게 됩니다.

## ⑥ shadow / layover 마스크 🔴 (사실 확정)

- `saveLayoverShadowMask=false` — [graphs/s1_grd_to_rtc_db.xml:130](../../graphs/s1_grd_to_rtc_db.xml#L130),
  [graphs/s1_grd_to_gtc_db.xml:111](../../graphs/s1_grd_to_gtc_db.xml#L111),
  [graphs/s1_slc_to_rtc_db.xml:171](../../graphs/s1_slc_to_rtc_db.xml#L171). **3개 전부**
  꺼져 있어 저장도, 적용도 안 됩니다.
- Speckle-Filter: **Frost** (2026-07-23 Refined Lee → Frost 변경, 근거는
  FILTER_COMPARISON_KR.md §6 "가는 수로 보존"). window/damping 미지정 시 SNAP
  기본값(Frost 3×3, damping 2) — [prepro_grd_gpt.py:83,93-95](../../s1/preprocess/prepro_grd_gpt.py#L83)에
  문서화돼 있습니다.
- DEM: **Copernicus 30m Global DEM** 기본, External DEM(NGII, `externalDEMApplyEGM=true`)
  옵션. 출력 화소 간격 10 m — [prepro_grd_gpt.py:48-67,194](../../s1/preprocess/prepro_grd_gpt.py#L48-L67).
- 리뷰의 우려(산지 음영 → 물 오탐)는 프로젝트도 인지하고 있습니다 —
  FLOOD_NORTH_KOREA_KR.md 8절 2번이 min-across-observations 설계와 결합될 때의
  위험을 명시해 뒀습니다. 다만 **마스크가 없어 정량화가 안 되는 상태**입니다.

## ⑦ 스페클 잔여·최소 면적(MMU) 필터 🔴 (로컬 사실 확정)

- 수체 마스크 생성부에 MMU도, 형태학 연산도 없습니다.
  [build_water_per_date_otsu.py:215-240](../../s1/tools/water/build_water_per_date_otsu.py#L215-L240)의
  `write_water()`는 `db < threshold` 픽셀 임계값만 적용합니다.
- [water_area_report.py](../../s1/tools/water/water_area_report.py)의 `--min-area-m2`는 **면적 보고·
  GeoJSON 내보내기 단계 전용**이고 기본값 `0.0`입니다. 마스크 자체는 안 고칩니다.
- **GEE 경로엔 있습니다**: `connectedPixelCount(25).gte(min_connected)`,
  기본 `min_connected=8` ([gee/geeflood/config.py:26](../../s1/core/config.py#L26)).
  로컬에 이식할 참조 구현이 됩니다.
- 참고로 리뷰가 센 폴리곤 수(DD29 198,458개)는 ③의 4.35 dB 과탐이 상당 부분
  원인이므로, **MMU 도입 전에 임계값을 Otsu로 통일하는 것만으로도 크게 줄어듭니다.**

## ⑧ 정확도 검증 절차 🔴 (사실 확정)

- 광학(Sentinel-2) 대조는 없습니다. 코드 전체에서 S2 참조는
  `gee/legacy_water_mask_march2025.js` 한 곳뿐이고 검증 용도가 아닙니다.
- 오탐률·누락률 등 정확도 지표 산출 코드도 없습니다.
- 있는 것: [qa/](../../qa) 모듈(스페클 필터 QA — ENL/지표 비교),
  RTC_BENCHMARK_KR.md·FILTER_COMPARISON_KR.md,
  [footprint/verify_scene_footprint.py](../../s1/tools/audit/verify_scene_footprint.py)
  (물 픽셀의 경계 내부 비율 사후 검증 — ①의 무효 판정에 실제로 쓰인 도구).
  즉 **"제대로 처리했나"는 검증 체계가 있고, "맞게 판독했나"는 없습니다.**
- 리뷰가 제안한 오차원 각주 표는 그대로 채택할 만합니다. FLOOD_NORTH_KOREA_KR.md
  8절과 FLOOD_DETECTION_KR.md에 같은 취지의 서술이 이미 흩어져 있으니, 표로
  묶어 보고 템플릿에 고정하는 편이 좋겠습니다.

## ⑨ 산출물 계보·파라미터 로깅 🟡 (부분)

- **래스터 내부 기록 없음**: 코드 전체에서 `update_tags` 호출 **0건**. GeoTIFF
  프로파일에 `driver/dtype/crs/transform/nodata/compress`만 넣고 임계값·씬 ID·
  DEM·필터 설정·처리 일시는 남기지 않습니다.
- 있는 것: `otsu_thresholds.csv`(임계값 계보 — Otsu 경로만),
  `downloads/rtc_benchmark*.csv`, 파일명 규칙(날짜·절대궤도 `_o######`·
  `_frost`/`_gtc` 접미사), `graphs/*.xml`(그래프 파라미터 스냅샷).
- `flood_nk_20260725.gpkg`를 직접 열어 보니 속성이
  `id / 지역 / after_date / after_scen / date_1 / scene_1 / date_2 / scene_2`
  로, **before/after 씬 계보를 사람이 손으로 적어 넣은 형태**였습니다(10개 군).
  `gpkg_metadata`에는 QGIS가 쓴 XML 한 건뿐이고 처리 파라미터는 없습니다.
  → 파이프라인이 `update_tags`로 임계값·씬 ID·DEM·처리일시를 넣어주면 이 수작업
  컬럼이 그대로 자동화됩니다.

---

## 권고 조치 (효과/비용 순)

1. **`extract_s1_summary()`에 `geometry` 한 줄 추가** — ②의 근본 원인. 이 한
   줄이 ②·⑤와 리뷰가 겪은 촬영지역 오판 전체의 상류입니다.
2. **RTC 출력에 footprint 사이드카** + `get_tif_shooting_area.py`가 그걸 참조.
   원본 zip 52개가 아직 있어 **43씬은 지금 소급 생성 가능**.
3. **무효 확정 산출물 격리·표시** — 위 5건 + `otsu_thresholds.csv` 무효 열.
   `excluded_china_japan/` 방식과 일관되게.
4. **차분 경로(v2)에 Otsu 임계값 주입** — 지금 `-16.0` 하드코딩이라 Otsu 경로와
   임계값이 어긋납니다. QGIS 수동 작업도 Otsu 값을 쓰도록 유도.
5. **`saveLayoverShadowMask=true`** 로 바꾸고 수체 판정에서 제외. 산지 대상지
   (신평·세포·천마)에 영향이 크다는 리뷰 지적이 타당합니다.
6. **MMU 도입** — GEE 경로의 `connectedPixelCount` 방식을 로컬로 이식.
7. **`update_tags`로 산출물에 파라미터 기록** — ⑨의 수작업 컬럼 자동화.

## 리뷰 문서에 반영하면 좋을 정정

- ③ "왜 그 값을 골랐는지 기록이 없다" → 파이프라인에는 `otsu_thresholds.csv`로
  있습니다. 기록이 없는 것은 **QGIS 수동 작업 쪽**입니다.
- ① "조치 제안: 일괄 재검증" → **2026-07-22에 79개 zip 전량 완료**
  (SCENE_FOOTPRINT_REAUDIT_KR.md). 남은 것은 무효 파일 표시뿐입니다.
- ④ "차분을 누락한 것인지" → 차분 구현은 있고, 북한에 대해서만 **마른 baseline
  부재를 근거로 의도적으로 포기**했습니다(FLOOD_NORTH_KOREA_KR.md 6절).
- 관련 문서 링크가 `README.md`·`TODO.md`로 적혀 있는데, 실제 파일명은
  [README_KR.md](../../README_KR.md)·[TODO_KR.md](../worklog/TODO_KR.md)입니다.
- 리뷰 표의 `scripts/build_inventory.py`·`ref/*.gpkg`는 상위 프로젝트에
  동일본이 없습니다(보고용 폴더 전용). 상위에는
  `downloads/rtc_grd/get_tif_shooting_area.py`가 대응하는데, 그게 바로 ②의
  bbox 문제를 가진 도구입니다.
