# downloads/ 폴더 구성 (2026-08-17 정리)

산출물 폴더는 git에 올라가지 않아 무엇이 무엇인지 알 방법이 코드 주석뿐이었다.
이 문서가 그 지도다. 용량은 2026-08-17 기준.

## 정본 — 지우면 안 되는 것

| 폴더 | 용량 | 내용 |
| --- | ---: | --- |
| `sentinel1_grd/` | 180 GB | **원본 GRD zip**. 모든 재처리의 입력 |
| `sentinel1/` | 102 GB | 원본 SLC zip (D:로 이동 후 junction) |
| `sentinel1_slc_202507/` | 17 GB | 25년 7월 SLC 4장 (간섭 분석용, 별도 수집) |
| **`rtc_grd_frost_vh/`** | **154 GB** | ★ **VH · Frost · external DEM RTC — 현행 정본** |
| `dem_basin/` | 2.6 GB | external DEM 입력. `korea_full_cop30.tif`가 기준 DEM |
| `water_otsu/` | 0.4 GB | 궤도별 Otsu 수체 지도 + **임계값·면적 CSV(git 추적)** |

## 참고·대조군 — 판단해서 정리할 것

| 폴더 | 용량 | 내용 | 비고 |
| --- | ---: | --- | --- |
| `gtc/` | 82 GB | GTC(Sigma0, TF 없음) | [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md)의 근거 |
| `water/` | 47 GB | 고정 임계값(−16 dB) 수체 마스크 97개 | Otsu 도입 전 방식 |
| `etc/` | 15 GB | RTC dB 16개 (한반도 0%·중복 등 분류 보류분) | |
| `excluded_china_japan/` | 9.0 GB | 한반도 footprint 0% 씬 | 감사용 |
| `rtc_extdem/` | 4.8 GB | 유역 clip DEM RTC 패치본 | 범위가 좁다(ISSUES #13) |
| `rtc_dem_test/` | 4.6 GB | COP30 vs NGII DEM 비교 실험 4개 | |
| `ls_mask30/` | 2.8 GB | 레이오버·섀도 마스크 | [LS_MASK_KR.md](LS_MASK_KR.md) |
| `rtc/` | 1.8 GB | SLC 기반 RTC (홍수 AOI 서브셋) | |
| `water_otsu_gtc/` | 0.3 GB | GTC 기반 Otsu 비교 실험 | |
| `rtc_grd_bench_snap/`·`rtc_grd_bench_sarsen/`·`rtc_grd_demcmp/`·`dem_test/` | 3.1 GB | 벤치마크·실험 | |
| `hand/`·`dem/` | 3.1 GB | HAND 타일, DEM 원본·VRT | |

## 보관 (2026-08-17 신설)

| 폴더 | 내용 |
| --- | --- |
| `_archive/rtc_grd_vv_meta/` | 삭제된 VV RTC(`rtc_grd/`)의 **메타데이터만** — 모자이크 VRT 정의 17개, footprint 감사 결과(geojson·csv), tree.txt. 어떤 조합의 모자이크를 만들었는지 기록으로 남긴다. **VRT는 참조 tif가 없어 열리지 않는다.** |

## 삭제 이력

**2026-08-17**: VH external DEM 통일 완료 후 VV RTC 삭제 (176 GB 확보)

| 폴더 | 삭제 | 내용 |
| --- | ---: | --- |
| `rtc_grd/` | 61 tif, 82.8 GB | VV · Refined Lee · 자동 DEM |
| `rtc_grd_frost/` | 71 tif, 93.3 GB | VV · Frost · 자동 DEM |

- `rtc_grd_frost`는 **원본 zip 81개가 있어 재생성 가능**하다:
  `python -m s1.tools.preprocess.batch_grd_rtc_frost --month 202607`(기본값이
  VV·Frost·자동 DEM).
- `rtc_grd`의 **2026-06 12씬 + 2026-07 3씬(6EBE·BB45·E265)은 원본 zip도 없어**
  로컬에서 완전히 사라졌다. 필요하면 CDSE 재다운로드.
- VV 기반 분석 **수치**는 `water_otsu/otsu_thresholds.csv`·
  `water_area_perrow.csv`(git 추적)와
  [WATER_AREA_KR.md](../water/WATER_AREA_KR.md)에 남아 있다.

## 죽은 VRT

`water_otsu/vrt/` 안에 **참조 tif가 사라진 VRT**가 있다(삭제된 VV Frost를
가리키던 것들). QGIS에서 열면 오류가 난다. 지우지 않고 남긴 이유는 어떤
프레임 조합이었는지가 기록이기 때문이다. VV를 재생성하면 그대로 다시 열린다.

## 정리 규칙

1. **원본 zip은 함부로 지우지 않는다.** 지우면 재처리가 불가능해진다. NAS
   업로드 후 삭제할 때는 반드시 NAS 쪽 크기를 대조한다.
2. **산출물을 지우기 전에 "원본으로 재생성 가능한가"를 먼저 확인한다.**
   확인 스크립트는 `s1/core/scene.py`의 `parse_scene`으로 씬 ID를 맞춰보면 된다.
3. **폴더 이름이 아니라 내용으로 말한다.** `rtc_grd_frost`가 아니라
   "VV·Frost·자동 DEM RTC"라고 적어야 오해가 없다.
4. 실험·벤치마크 산출물은 결론이 문서에 반영되면 지워도 된다. 결론이 어느
   문서에 있는지 먼저 확인할 것.
