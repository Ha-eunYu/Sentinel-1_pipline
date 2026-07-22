# GTC·RTC 처리 이력 (2026-07-22 기준)

이 프로젝트에서 어떤 지역·날짜의 어떤 Sentinel-1 GRD 촬영본을 RTC/GTC로
처리했는지, 그리고 각 처리의 과정(그래프 단계·파라미터)을 정리한 문서.
**왜** RTC를 기본으로 쓰고 GTC를 대조군으로 두는지에 대한 개념 설명은
[RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md)에 있고, 여기는 **무엇을 실제로 돌렸는지**의
기록이다. 관련 코드: [prepro_grd_gpt.py](prepro_grd_gpt.py)(그래프 정의),
[batch_grd_rtc.py](batch_grd_rtc.py)·[batch_grd_gtc.py](batch_grd_gtc.py)(배치 러너).

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
| Speckle 필터 | Refined Lee |
| DEM | Copernicus 30m Global DEM (자동 다운로드) |
| 리샘플링 | BILINEAR_INTERPOLATION (img·dem) |
| 픽셀 간격 | 10 m |
| 출력 | dB (LinearToFromdB), GeoTIFF-BigTIFF, EPSG:4326 |
| gpt 옵션 | `-q 8 -c 14G` |

### RTC 그래프 (기본 파이프라인, `build_grd_rtc_graph`)

```text
Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration(Beta0)
     → [Subset(AOI)*] → Speckle-Filter(Refined Lee)
     → Terrain-Flattening → Terrain-Correction → LinearToFromdB
     → Write(<씬ID>_rtc_db.tif)
```

- Calibration에서 **Beta0** 출력(Terrain-Flattening 입력 요건).
- Terrain-Flattening이 DEM 국지 입사각으로 지형 경사·향 밝기 왜곡을 정규화.
- `*` AOI Subset은 `--aoi` 옵션일 때만(배치에서는 전체 씬).

### GTC 그래프 (대조군, `build_grd_gtc_graph`)

```text
Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration(Sigma0)
     → [Subset(AOI)*] → Speckle-Filter(Refined Lee)
     → Terrain-Correction → LinearToFromdB
     → Write(<씬ID>_gtc_db.tif)
```

- Calibration에서 **Sigma0** 출력, **Terrain-Flattening 생략**.
- 기하 보정(지오코딩)만 하고 지형 밝기 왜곡은 그대로 남김 → RTC와 육안 비교용.
- 처리 시간은 RTC의 약 1/3 (씬당 TF가 60~70% 차지, 실측 [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md) 2절).

### 산출물 위치·명명

- 폴더: `downloads/rtc_grd/`
- 명명: `<씬ID>_rtc_db.tif` / `<씬ID>_gtc_db.tif` (같은 씬이 나란히 저장, 접미사로 구분)
- 일본/중국 전용(한반도 footprint 0%) 씬은 `downloads/excluded_china_japan/`로 분리 보관(2026-07-22, [SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md)).

---

## 2. 무엇을 처리했나 — 날짜·궤도·씬 인벤토리

관측 시각은 UTC 기준 파일명 날짜. KST는 +9h(저녁 21시대 UTC → 익일 06시대 KST).
지역 구분은 프레임 footprint 기준 개략값이며, 정밀 남/북 분리는
[FLOOD_TIMELINE_KR.md](FLOOD_TIMELINE_KR.md)·[FLOOD_NORTH_KOREA_KR.md](FLOOD_NORTH_KOREA_KR.md) 참고.

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

✅=완료, ⏳=GTC 배치 진행 중(2026-07-22 기준 GTC 31/한반도씬 완료, 나머지 순차 처리).

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
  이동 도구: [archive_gtc.ps1](archive_gtc.ps1).
- **GTC 코드·그래프**(`prepro_grd_gpt.py`의 `build_grd_gtc_graph`/`--gtc`,
  [batch_grd_gtc.py](batch_grd_gtc.py), `graphs/s1_grd_to_gtc_db.xml`): **재현용
  유지**.
- **일회성 스크립트**(`C_grd_down.py`, `C_grd_RTC.py`, FE43 단일 씬용): 유지.
- **`excluded_china_japan/`의 GTC 7개**: 감사용 rtc/gtc 짝을 유지하려 **그 폴더에
  그대로 둠**(원하면 `archive_gtc.ps1 -IncludeExcluded`로 함께 이동).

> **⏳ 이동 실행 시점 — 배치 종료 후**: 2026-07-22 기준 `batch_grd_gtc.py`가 아직
> 실행 중이라 `rtc_grd/`에 GTC를 계속 쓰고 있다. 실행 중에는 이동을 **하지 않는다**
> (배치가 쓰는 중인 tif는 윈도우 파일 잠금으로 이동이 실패해 건너뛰어지긴 하지만,
> 배치가 새 GTC를 계속 만들므로 완전 정리가 안 됨). **배치가 끝난 뒤 한 번**
> 아래를 실행하면 깔끔하게 이동된다(재실행 안전):
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File archive_gtc.ps1 -WhatIf   # 대상 미리보기
> powershell -ExecutionPolicy Bypass -File archive_gtc.ps1           # 실제 이동
> ```
>
> 이동 후에는 이 문서 1절의 "산출물 위치"(현재 `downloads/rtc_grd/`)와
> [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md) 4절의 392D GTC 경로를 `downloads/gtc/`로
> 갱신할 것.
