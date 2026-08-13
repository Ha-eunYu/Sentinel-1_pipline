# GTC·RTC 처리 이력 (2026-07-30 갱신)

> 2~5절은 **2026-07-22 시점** 기록이다. 그 이후(Frost 전면 재처리, 7월 후반
> 씬, 남한 궤도 선별)는 **6절**에 이어 적는다.

이 프로젝트에서 어떤 지역·날짜의 어떤 Sentinel-1 GRD 촬영본을 RTC/GTC로
처리했는지, 그리고 각 처리의 과정(그래프 단계·파라미터)을 정리한 문서.
**왜** RTC를 기본으로 쓰고 GTC를 대조군으로 두는지에 대한 개념 설명은
[RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md)에 있고, 여기는 **무엇을 실제로 돌렸는지**의
기록이다. 관련 코드: [prepro_grd_gpt.py](../../s1/preprocess/prepro_grd_gpt.py)(그래프 정의),
[batch_grd_rtc.py](../../s1/tools/preprocess/batch_grd_rtc.py)·[batch_grd_gtc.py](../../s1/tools/preprocess/batch_grd_gtc.py)(배치 러너).

---

## 1. 처리 과정 (그래프 단계)

두 산출물 모두 SNAP `gpt`를 snapista로 구동하며, 입력 zip을 C: SSD 임시
폴더로 복사한 뒤 처리하고(HDD/네트워크 랜덤읽기 병목 회피) 복사본은
삭제한다. 처리 파라미터는 공통이고 **딱 한 단계(Terrain-Flattening)와
캘리브레이션 기준만 다르다.**

### 공통 파라미터

| 항목 | 값 |
| --- | --- |
| 편파 | VV |
| 궤도 | Apply-Orbit-File, Sentinel Precise (Auto Download), 없으면 RESORB 대체 |
| Thermal Noise | 제거 (removeThermalNoise=true) |
| Speckle 필터 | **Frost (3×3, damping 2.0)** — 2026-07-23 Refined Lee에서 변경 (아래 주의) |
| DEM | Copernicus 30m Global DEM (자동 다운로드) |
| 리샘플링 | BILINEAR_INTERPOLATION (img·dem) |
| 픽셀 간격 | 10 m |
| 출력 | dB (LinearToFromdB), GeoTIFF-BigTIFF, EPSG:4326 |
| gpt 옵션 | `-q 8 -c 14G` |

> **⚠️ 2026-07-23 speckle 필터 기본값 변경 (Refined Lee → Frost)**:
> [FILTER_COMPARISON_KR.md](FILTER_COMPARISON_KR.md) §2·§6 권고(Frost가 speckle
> 억제는 동등하면서 가는 수로·경계 보존이 우수)에 따라 `prepro_grd_gpt.py`의
> 기본 `speckle_filter_name`을 **Frost(SNAP 기본 3×3, damping 2.0)**로 바꿨다.
> **주의**: 이 문서 2절 인벤토리의 기존 RTC/GTC 65개는 전부 **Refined Lee(7×7)**로
> 처리된 것이다. 앞으로 새로 돌리는 산출물은 Frost라 기존과 필터가 섞인다.
> dB 절대값이 필터에 따라 조금 달라지므로, 고정 임계값(-16dB)으로 날짜·궤도를
> 넘나드는 비교를 계속하려면 **전 씬을 Frost로 재처리하는 것을 권장**한다
> (재처리 전까지는 필터 혼재를 감안). 현재 실행 중인 GTC 배치는 이미 로드된
> 옛 기본값(Refined Lee)으로 남은 씬을 마저 처리한다(GTC는 육안 비교 전용이라 영향 작음).

### RTC 그래프 (기본 파이프라인, `build_grd_rtc_graph`)

```text
Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration(Beta0)
     → [Subset(AOI)*] → Speckle-Filter(Frost, 기본)
     → Terrain-Flattening → Terrain-Correction → LinearToFromdB
     → Write(<씬ID>_rtc_db.tif)
```

- Calibration에서 **Beta0** 출력(Terrain-Flattening 입력 요건).
- Terrain-Flattening이 DEM 국지 입사각으로 지형 경사·향 밝기 왜곡을 정규화.
- `*` AOI Subset은 `--aoi` 옵션일 때만(배치에서는 전체 씬).

### GTC 그래프 (대조군, `build_grd_gtc_graph`)

```text
Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration(Sigma0)
     → [Subset(AOI)*] → Speckle-Filter(Frost, 기본)
     → Terrain-Correction → LinearToFromdB
     → Write(<씬ID>_gtc_db.tif)
```

- Calibration에서 **Sigma0** 출력, **Terrain-Flattening 생략**.
- 기하 보정(지오코딩)만 하고 지형 밝기 왜곡은 그대로 남김 → RTC와 육안 비교용.
- 처리 시간은 RTC의 약 1/3 (씬당 TF가 60~70% 차지, 실측 [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md) 2절).

### 산출물 위치·명명

- 폴더: RTC는 `downloads/rtc_grd/`, **GTC는 `downloads/gtc/`**(2026-07-23 분리 완료, 5절).
- 명명: `<씬ID>_rtc_db.tif`(rtc_grd) / `<씬ID>_gtc_db.tif`(gtc). 접미사로 구분.
- 일본/중국 전용(한반도 footprint 0%) 씬은 `downloads/excluded_china_japan/`로 분리 보관(2026-07-22, [SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md)).

---

## 2. 무엇을 처리했나 — 날짜·궤도·씬 인벤토리

관측 시각은 UTC 기준 파일명 날짜. KST는 +9h(저녁 21시대 UTC → 익일 06시대 KST).
지역 구분은 프레임 footprint 기준 개략값이며, 정밀 남/북 분리는
[FLOOD_TIMELINE_KR.md](../flood/FLOOD_TIMELINE_KR.md)·[FLOOD_NORTH_KOREA_KR.md](../flood/FLOOD_NORTH_KOREA_KR.md) 참고.

### 2.1 한반도 관련 씬 (`downloads/rtc_grd/`)

| 관측일(UTC) | 위성 | 촬영시각대 | 씬(4자리 ID) | RTC | GTC |
| --- | --- | --- | --- | --- | --- |
| 06/25 | S1A | 09:31 (아침 상승) | 0999·FAC3 | ✅ | ✅ |
| 06/25 | S1D | 09:39 (아침 상승) | 3043·794A | ✅ | ✅ |
| 06/26 | S1C | 21:29 (저녁 하강) | A392·D578·1A5D·303C·3A16·02C6·194A·BE31 | ✅ | ✅ |
| 07/01 | S1C | 21:37 (저녁 하강) | E265·5C8D·54D9·0FEB·EC8B·8E98 | ✅ | ✅ |
| 07/02 | S1D | 09:30 (아침 상승) | EF53·5469 | ✅ | ⏳ |
| 07/03 | S1C | 21:21 (저녁 하강) | 32AE·64DE·9A73·BB45 | ✅ | ✅ |
| 07/03 | S1C | 21:21 (저녁 하강) | 6942 | ✅ | ⏳ |
| 07/04 | S1D | 09:16 (아침 상승) | 1571 | ✅ | ⏳ |
| 07/06 | S1C | 21:46 (저녁 하강) | 427D·74FD·F040 | ✅ | ⏳ |
| 07/07 | S1D | 09:39 (아침 상승) | 5D47·525F | ✅ | ⏳ |
| 07/13 | S1C | 21:38 (저녁 하강, post-event) | 93FC·3C22·1A5A·4265·AEB7 | ✅ | ⏳ |
| 07/14 | S1D | 09:30/21:31 | 376D·FE43·8EF1·B126 | ✅ | ⏳ |
| 07/15 | S1C | 09:21 (아침 상승) | 2DA8·AC28·C278 | ✅ | ⏳ |
| 07/16 | S1D | 21:16 (저녁 하강) | 3191·4C7C·9FFF | ✅ | ⏳ |
| 07/18 | S1C | 21:46 (저녁 하강) | 2B06·6EBE·C9CC | ✅ | 2B06·6EBE ✅ / C9CC ⏳ |
| 07/19 | S1D | 09:39 (아침 상승) | 0B91·3194 | ✅ | ⏳ |
| 07/20 | S1C | 21:30 (저녁 하강, 최신 패스) | CE47·0CEF·392D·DD29·F314·74BD·93DD | ✅ | ✅ |
| 07/25 | S1C | 21:38 (저녁 하강) | 3804·4303·59A8·BE24·D74B | Frost만 | — |
| 07/26 | S1D | 09:30 (아침 상승) | 772C | Frost만 | — |
| 07/27 | S1C | 21:21 (저녁 하강) | DF80·32ED·08EE·9B8B | Frost만 | — |
| 07/28 | S1D | 09:16 (아침 상승) | 639F | Frost만 | — |

✅=완료, ⏳=GTC 배치 진행 중(2026-07-22 기준 GTC 31/한반도씬 완료, 나머지 순차 처리).
"Frost만"=Refined Lee 산출물 없이 `rtc_grd_frost/`에만 존재(6절). GTC는 육안
비교용이라 7/20 이후로는 돌리지 않았다.

### 2.2 일본/중국 전용 씬 (`downloads/excluded_china_japan/`, 한반도 footprint 0%)

RTC·GTC 둘 다 이미 끝나 있어 삭제 대신 감사용으로 분리 보관. **소스 zip은
삭제**(재작업 무의미, NAS에서 재취득 가능), RTC/GTC tif만 보존.

| 관측일 | 위성 | 씬 | RTC | GTC | 실제 위치 |
| --- | --- | --- | --- | --- | --- |
| 06/26 | S1C | FAA4 | ✅ | ✅ | 제주 남쪽 먼바다 |
| 06/27 | S1A | 88AF·E215 | ✅ | ✅ | 대한해협~일본 방향 |
| 06/28 | S1C | 9919·D440 | ✅ | ✅ | 대마도~규슈 방향 |
| 07/18 | S1C | 3883 | ✅ | ✅ | 동해상(사용자 보류 궤도) |
| 07/20 | S1C | B5A5 | ✅ | ✅ | 남해상(사용자 보류 궤도) |

---

## 3. 소스 zip 정리 (2026-07-22)

- **RTC·GTC 둘 다 끝난 zip은 삭제**(산출 tif가 있으므로 소스 불필요, NAS에서
  재취득 가능): `sentinel1_grd/`에서 31개 + `excluded_china_japan/`에서 7개 = **38개 삭제**.
- 아직 GTC 대기 중인 씬(RTC만 완료)의 zip은 배치가 써야 하므로 **보존**.
- 한반도 footprint 0%로 확인됐지만 아직 미처리였던 씬(13개)은 zip 자체를
  삭제해 GTC 배치 대상에서 제외([SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md)).

## 4. 요약 카운트 (2026-07-22 기준)

| 구분 | RTC | GTC |
| --- | --- | --- |
| `rtc_grd/` (한반도) | 58 | 31 (진행 중) |
| `excluded_china_japan/` (일본/중국) | 7 | 7 |
| **합계** | **65** | **38 (계속 증가)** |

## 5. GTC 산출물 정리 (2026-07-22)

GTC는 **육안 비교 전용**(수체 탐지 미사용, [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md))
이라 비교가 끝나면 작업 폴더에서 분리한다. 정리 방침(결정):

- **GTC tif(`*_gtc_db.tif`)**: 삭제하지 않고 **별도 폴더 `downloads/gtc/`로 이동
  보관**. 작업 폴더 `rtc_grd/`에서 RTC 산출물과 섞이지 않게 하되, 필요 시
  `batch_grd_gtc.py`로 언제든 재생성 가능(원본 유지가 목적).
  이동 도구: [archive_gtc.ps1](../../scripts/archive_gtc.ps1).
- **GTC 코드·그래프**(`prepro_grd_gpt.py`의 `build_grd_gtc_graph`/`--gtc`,
  [batch_grd_gtc.py](../../s1/tools/preprocess/batch_grd_gtc.py), `graphs/s1_grd_to_gtc_db.xml`): **재현용
  유지**.
- **일회성 스크립트**(`C_grd_down.py`, `C_grd_RTC.py`, FE43 단일 씬용): 유지.
- **`excluded_china_japan/`의 GTC 7개**: 감사용 rtc/gtc 짝을 유지하려 **그 폴더에
  그대로 둠**(원하면 `archive_gtc.ps1 -IncludeExcluded`로 함께 이동).

> **✅ 이동 완료 (2026-07-23)**: `batch_grd_gtc.py` 배치가 끝난 뒤
> `archive_gtc.ps1`을 실행해 `rtc_grd/`의 GTC 산출물 **59개(tif + 사이드카)**를
> `downloads/gtc/`로 옮겼다(0개 건너뜀). `rtc_grd/`에는 이제 RTC(_rtc_db.tif)만
> 남는다. `excluded_china_japan/`의 GTC 7개는 감사 짝 유지를 위해 그대로 두었다.
> 재실행 안전(idempotent)하므로 이후 새 GTC가 생기면 다시 돌리면 된다:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File archive_gtc.ps1 -WhatIf   # 대상 미리보기
> powershell -ExecutionPolicy Bypass -File archive_gtc.ps1           # 실제 이동
> ```

---

## 6. Frost 재처리 완료와 남한 궤도 선별 (2026-07-30)

### 6.1 26년 7월 RTC(Frost) 전량 완료

2026-07-23에 기본 speckle 필터를 Refined Lee → Frost로 바꾼 뒤(1절 주의),
7/27~7/30 배치로 **26년 7월 GRD 57씬을 전부 `downloads/rtc_grd_frost/`에
재처리**했다. 마지막까지 남아 있던 7/27 4씬 중 **남한 footprint가 걸리는
2씬(08EE·9B8B)만** 처리하고, 남한 0%인 2씬(DF80·32ED)은 돌리지 않았다
(수체 판독 대상이 26년 7월 **남한**이므로).

씬을 골라 돌리기 위해 [batch_grd_rtc_frost.py](../../s1/tools/preprocess/batch_grd_rtc_frost.py)에
`--only` 옵션을 추가했다(파일명 부분일치, 미지정 시 종전대로 전체):

```bash
conda run -n s1_snappy python batch_grd_rtc_frost.py --month 202607 --only 08EE,9B8B
```

### 6.2 궤도그룹별 남한 커버율 (footprint 실측)

bbox가 아니라 **원본 zip의 `preview/map-overlay.kml` footprint**를
`geojson/South_Korea.geojson`과 point-in-polygon 대조해 산정했다(bbox를 쓰면
기운 평행사변형의 빈 삼각형까지 "촬영"으로 오판한다 —
[SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md),
[footprint/FOOTPRINT_AOI_KR.md](FOOTPRINT_AOI_KR.md)).

26년 7월 20개 궤도그룹 중 **남한 궤도 11개**:

| 날짜 | 궤도 | 프레임 | 남한 최대 | 프레임별 남한 비율 |
| --- | --- | ---: | ---: | --- |
| 07/01 | o008355 | 5 | 17.9% | EC8B 18 · 0FEB 7 · 8E98 6 · 54D9 0 · 5C8D 0 |
| 07/02 | o003493 | 2 | 54.7% | 5469 55 · EF53 31 |
| 07/03 | o008384 | 4 | 11.2% | 6942 11 · 9A73 10 · 32AE 0 · 64DE 0 |
| 07/13 | o008530 | 5 | 17.9% | 3C22 18 · 93FC 7 · 1A5A 6 · 4265 0 · AEB7 0 |
| 07/14 | o003668 | 2 | 54.7% | FE43 55 · 376D 31 |
| 07/14 | o003675 | 2 | 71.5% | 8EF1 72 · B126 70 |
| 07/15 | o008552 | 3 | 59.0% | AC28 59 · C278 45 · 2DA8 2 |
| 07/20 | o008632 | 8 | 80.2% | F314 80 · DD29 71 · 74BD 23 · 392D 2 · 나머지 4개 0 |
| 07/25 | o008705 | 5 | 17.9% | BE24 18 · 59A8 7 · D74B 6 · 3804 0 · 4303 0 |
| 07/26 | o003843 | 1 | 39.6% | 772C 40 |
| 07/27 | o008734 | 2 | 38.2% | 9B8B 38 · 08EE 10 |

남한 0%로 제외한 9개 궤도: 07/03 o008377, 07/04 o003522, 07/06 o008428,
07/07 o003566, 07/16 o003697, 07/16 o003704, 07/18 o008603, 07/19 o003741,
07/28 o003872.

> **궤도그룹은 통째로 쓴다.** 남한 0%인 프레임이 섞여 있어도 그 프레임만
> 빼지 않는다. 타일 기반 Otsu는 궤도 전체 히스토그램에서 이봉 타일을 골라야
> 임계값이 안정적이라, 프레임을 미리 잘라내면 표본이 줄어 임계값이 흔들린다.
> 남/북 분리는 판정 **후** [split_flood_area_nk_sk.py](../../s1/tools/water/split_flood_area_nk_sk.py)
> 단계에서 한다.

### 6.3 25년·26년 혼재 방지

25년 7월 RTC가 **같은 폴더(`downloads/rtc_grd_frost/`)** 에 순차로 올라오고
있고(2026-07-30 기준 20250707 1씬 도착), 25년 Otsu는 추후 별도로 돌린다.
연도가 섞이지 않도록:

- [build_water_per_date_otsu.py](../../s1/tools/water/build_water_per_date_otsu.py)의 `--dates`를
  **접두사 일치**로 바꿨다: `--dates 2026`(그 해) / `202607`(그 달) /
  `20260703`(하루). 궤도 목록을 잊어도 연도가 고정된다.
- `--orbits`(절대궤도 화이트리스트)를 추가했다. 셸이 `008632`를 숫자로 읽어
  앞의 0을 떨구는 사고가 있어 스크립트에서 `zfill(6)`으로 정규화한다.
- 산출물 파일명에 관측일이 들어가므로(`flood_water_total_<날짜>_o<궤도>_frost.tif`)
  25·26년이 같은 출력 폴더에 있어도 덮어쓰지 않는다.

결과는 [WATER_AREA_KR.md](../water/WATER_AREA_KR.md) "26년 7월 남한 궤도" 절 참고.
