# 북한 홍수 지역별 수체 면적 산정 (2026-07-25) — 워크플로 & 코드

**목적**: 2026-07-25 북한 홍수에 대해, QGIS로 그린 **10개 지역(군/댐) 폴리곤**별로
**홍수일(after) + 비교일(before) 수체 면적(km²)** 을 구한다. 지역별 before/after 비교로
상시수 대비 홍수 확대분을 본다.

관련: [FLOOD_NORTH_KOREA_KR.md](../FLOOD_NORTH_KOREA_KR.md), [OTSU_SPLIT_BASED_KR.md](../OTSU_SPLIT_BASED_KR.md),
[WATER_AREA_KR.md](../WATER_AREA_KR.md)

---

## 1. 입력

### 1-1. 지역 폴리곤 — `flood_nk_20260725.gpkg`

QGIS로 그린 GeoPackage. 레이어 `flood_nk_20260725`, **10 MultiPolygon, EPSG:4326**,
범위 lon 124.85–127.60 / lat 38.32–40.05(북한 서·중부).

| 필드 | 뜻 |
| --- | --- |
| `id`, `지역` | 지역 번호·이름(군/댐) |
| `after_date`, `after_scen` | 홍수일(7/25) 관측일·씬ID |
| `date_1`, `scene_1` | 비교(before) 관측 1 |
| `date_2`, `scene_2` | 비교(before) 관측 2 (없는 지역은 공란) |

### 1-2. 수체 지도 — `downloads/water_otsu/flood_water_total_<YYYYMMDD>_o<절대궤도>[_frost].tif`

`build_water_per_date_otsu.py`가 만든 **날짜·궤도별 수체 지도**. 값 **0=비수체,
1=수체, 255=미관측**, 10m, EPSG:4326. `_frost`=Frost 스펙클 기반, 무접미사=Refined Lee.

### 1-3. (선택) 씬 단위 지도 — `downloads/water/scene_water/<씬>_<임계값dB>.tif`

특정 씬을 고정 dB 임계로 만든 수체 지도(예 `59A8_-12.tif`). 특정 지역·관측을 이걸로
덮어쓸 때(override) 사용.

---

## 2. 처리 흐름 (3단계)

```text
[1] 씬 RTC          Sentinel-1 GRD → γ0 dB (SNAP Frost 10m; 없으면 Refined Lee)
       │              prepro_grd_gpt.py / batch_grd_rtc_frost.py / _snap_rtc_one.py
       ▼              → downloads/rtc_grd_frost/*_rtc_db.tif  (또는 rtc_grd/)
[2] 수체 탐지       날짜·궤도별 split-based tile-Otsu → water map(0/1/255)
       │              build_water_per_date_otsu.py
       ▼              → downloads/water_otsu/flood_water_total_<date>_o<orbit>[_frost].tif
[3] 면적 산정       폴리곤 마스킹 → 수체 화소 × 위도보정 화소면적 → km²
                      nk_flood_water_area.py  → nk_water_before_after_20260725.csv
```

### 2-1. 수체 탐지 임계값 (이번 산정에 사용)

궤도별 split-based Otsu(이봉 타일 풀링, [OTSU_SPLIT_BASED_KR.md](../OTSU_SPLIT_BASED_KR.md)):

| 날짜 | 궤도 | 필터 | Otsu 임계값 |
| --- | --- | --- | --- |
| 2026-07-25 (after) | o008705 | Frost | **−14.85 dB** |
| 2026-07-13 | o008530 | Frost | −13.75 dB |
| 2026-07-19 | o003741 | Frost | −14.75 dB |
| 2026-07-20 | o008632 | Frost | −14.35 dB |
| 2026-06-26 | o008282 | Refined Lee | (RL 자체 Otsu) |

### 2-2. 면적 산정 (핵심 계산)

각 폴리곤을 해당 관측일 water map에 `rasterio.mask`로 잘라 **수체(값 1) 화소 수**를
세고, **위도 보정 화소 지상면적**으로 km² 환산:

```text
화소면적(m²) = (px_w_deg · 111320 · cos φ) × (px_h_deg · 111320)
수체(km²)   = (수체 화소 수) × 화소면적 / 1e6      # φ = 폴리곤 중심 위도
```

10m 격자를 EPSG:4326(도 단위)로 저장해 경도 방향 지상길이가 위도에 따라 줄어드는 것을
`cos φ`로 보정한다. 한 날짜에 궤도맵이 여럿이면 관측 화소가 가장 많은 맵을 쓴다.

---

## 3. 코드 & 실행

| 단계 | 코드 | 역할 |
| --- | --- | --- |
| [2] 수체 탐지 | **`build_water_per_date_otsu.py`** | 날짜·궤도별 tile-Otsu 수체 지도 |
| [3] 면적 산정 | **`nk_flood_water_area.py`** | gpkg 폴리곤별 before/after 수체 면적 → CSV |

```bash
# [2] before 날짜 Frost 수체 지도 생성 (after 7/25는 이미 생성됨)
conda run -n s1_snappy python build_water_per_date_otsu.py \
    --source-dir downloads/rtc_grd_frost --suffix rtc_db --out-suffix _frost \
    --dates 20260713,20260719,20260720

# [3] 지역별 before/after 수체 면적 표
conda run -n gis_clean python nk_flood_water_area.py
#   → nk_water_before_after_20260725.csv
```

`nk_flood_water_area.py`의 **OVERRIDES** 딕셔너리로 특정 지역·관측을 `scene_water` 지도로
덮어쓴다. 이번엔 **안변군 after = `scene_water/59A8_-12.tif`**(59A8 단독, −12 dB).

---

## 4. 결과 (2026-07-25 북한 지역별)

| id | 지역 | after | after_scen | 수체km² | date_1 | scen_1 | 수체km²_1 | date_2 | scen_2 | 수체km²_2 |
| --- | --- | --- | --- | --: | --- | --- | --: | --- | --- | --: |
| 1 | 황주군 | 07-25 | 59A8 | 21.52 | 07-13 | 93FC | 18.94 | | | |
| 2 | 안악군 | 07-25 | 59A8 | 11.83 | 07-13 | 93FC | 7.39 | 07-19 | 0B91 | 6.94 |
| 3 | 신평군 | 07-25 | 59A8 | 19.50 | 07-13 | 93FC | 9.36 | | | |
| 4 | 연탄군 | 07-25 | 59A8 | 8.30 | 07-13 | 93FC | 3.68 | | | |
| 5 | 판교군 | 07-25 | 59A8 | 4.75 | 07-13 | 93FC | 1.72 | 07-20 | 392D | 2.95 |
| 6 | 천마군 | 07-25 | 59A8 | 10.45 | 07-13 | AEB7 | 7.74 | 07-19 | 3194 | 9.64 |
| 7 | 박천군 | 07-25 | 4303,59A8 | 3.62 | 07-13 | AEB7,93FC | 2.48 | | | |
| 8 | 안변군 | 07-25 | 59A8¹ | 5.37¹ | 06-26 | 303C | 3.56 | 07-20 | 392D | 5.73 |
| 9 | 곽산군 | 07-25 | 4303,59A8 | 5.62 | 07-13 | AEB7,93FC | 3.62 | 07-19 | 0B91 | 4.60 |
| 10 | 황강댐 | 07-25 | 59A8 | 21.28 | 07-13 | 93FC | 17.92 | 07-20 | DD29 | 25.93 |

CSV: `nk_water_before_after_20260725.csv`

**해석(예)**: 신평군 9.36→19.50(+10.1), 연탄군 3.68→8.30(+4.6), 안악군 7.39→11.83(+4.4)
= 7/13 대비 7/25 수체 확대(홍수 신호). 황강댐은 7/13 17.92 → 7/20 25.93(피크) → 7/25
21.28 로, 7/20에 저수지가 최대였다 7/25 감소(방류 정황).

---

## 5. 주의 / 한계

1. **임계값 혼재**: 1~10행의 after/before는 **궤도별 tile-Otsu**(−14~−16 dB)로 계산.
   단 **안변군 after¹만 `59A8_-12.tif`(−12 dB, 더 완만)** 를 지정 사용 → 안변군 after는
   다른 행과 임계값 기준이 달라 직접 비교 시 유의(−12는 값이 크게 나옴). gpkg 속성의
   `after_scen`은 4303이나, 실제 계산은 안변군을 온전히 덮는 **59A8** 지도로 함.
2. **커버리지**: 안변군 after는 폴리곤의 **83.4%만 관측**(동쪽 16.6%는 7/25 스와스 밖).
   나머지 지역은 ~100% 관측. before(303C·392D)는 안변군 100% 관측.
3. **필터**: after·7/13·7/19·7/20 = **Frost**, 6/26(303C)만 **Refined Lee**(Frost 없음).
4. **수체 = 상시수 + 홍수**: 하천·저수지(황강댐 등)가 포함됨. **홍수 순증분**은
   `after − before`로 봐야 한다(같은 지역의 before 열과 차분).
5. **면적법**: 10m EPSG:4326 격자를 위도 보정(`cos φ`)해 km² 환산. 폴리곤 면적은
   UTM 52N(EPSG:32652) 기준.

---

## 6. 산출물

- `flood_nk_20260725.gpkg` — 입력 지역 폴리곤(10개).
- `downloads/water_otsu/flood_water_total_2026072[0359...]_o*[_frost].tif` — 날짜·궤도별 수체 지도.
- `nk_water_before_after_20260725.csv` — 지역별 before/after 수체 면적표.
- `nk_flood_water_area.py`, `build_water_per_date_otsu.py` — 재현 코드.
