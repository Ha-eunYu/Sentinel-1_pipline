# downloads/ 폴더 구성 (2026-08-17 정리)

산출물 폴더는 git에 올라가지 않아 무엇이 무엇인지 알 방법이 코드 주석뿐이었다.
이 문서가 그 지도다. 용량은 2026-08-17 기준.

## 정본 — 지우면 안 되는 것

| 폴더 | 용량 | 내용 |
| --- | ---: | --- |
| `sentinel1_grd/` 🔗 | 180 GB | **원본 GRD zip**. 모든 재처리의 입력. **junction → `E:\06_SAR_system_archive\sentinel1_grd`** |
| `sentinel1/` 🔗 | 102 GB | 원본 SLC zip. **junction → `D:\06_SAR_system_archive\sentinel1`** |
| `sentinel1_slc_202507/` | 17 GB | 25년 7월 SLC 4장 (간섭 분석용, 별도 수집). F: 실물 |

### 🔗 junction 주의

두 원본 폴더는 **다른 드라이브를 가리키는 junction**이다(2026-08-17 실측).
탐색기·스크립트에서는 `downloads/` 안에 있는 것처럼 보이지만 실제 데이터는
D:·E:에 있다. F: 용량을 확보하면서 스크립트 경로는 그대로 두려고 이렇게 했다.

```powershell
Get-ChildItem downloads -Directory | ForEach-Object {
    $i = Get-Item $_.FullName
    if ($i.LinkType) { "$($_.Name) -> $($i.Target)" }
}
```

- **junction 안의 파일을 지우면 D:·E:의 실물이 지워진다.** `downloads/` 안이라고
  가볍게 지우지 말 것.
- **`Remove-Item -Recurse`를 junction 자체에 쓰면 대상 폴더 내용까지 지워질 수
  있다.** 링크만 없애려면 `(Get-Item <경로>).Delete()` 를 쓴다.
- F:에 실제로 올라가 있는 `downloads/` 용량은 **346.8 GB**다(junction 제외).

**드라이브 역할** (2026-08-17): C: 294 GB 여유(SNAP 임시) · D: 178 GB(SLC 원본) ·
E: 812 GB(GRD 원본) · F: 243 GB(작업·산출물) · X:/Y: NAS
| **`rtc_grd_frost_vh/`** | **154 GB** | ★ **VH · Frost · external DEM RTC — 현행 정본** |
| `dem_basin/` | 2.6 GB | external DEM 입력. `korea_full_cop30.tif`가 기준 DEM |
| `water_otsu/` | 0.4 GB | 궤도별 Otsu 수체 지도 + **임계값·면적 CSV(git 추적)** |

## 참고·대조군 — 판단해서 정리할 것

| 폴더 | 용량 | 내용 | 비고 |
| --- | ---: | --- | --- |
| ~~`gtc/`~~ | — | **2026-08-25 삭제**(아래 삭제 이력) | [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md)에 결론 |
| ~~`water/`~~ | — | **2026-08-25 삭제** | 수치는 [WATER_AREA_KR.md](../water/WATER_AREA_KR.md) |
| `etc/` | 15 GB | RTC dB 16개 (한반도 0%·중복 등 분류 보류분) | |
| ~~`excluded_china_japan/`~~ | — | **2026-08-25 삭제** — 원본 zip 3개는 `E:\06_SAR_system_archive\excluded_china_japan\`로 이동 | 감사용 |
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

**2026-08-25**: 대조군·구방식 산출물 삭제 (**136 GB 확보**, F: 여유 112 → 248 GB)

전처리 대기 57건에 약 131 GB가 필요한데 F: 여유가 112 GB뿐이라 **끝나기 전에
공간이 떨어지는 상황**이었다. 세 폴더 모두 결론이 이미 문서에 반영됐고 원본
zip(E:)으로 재생성 가능해 지웠다.

| 폴더 | 삭제 | 내용 | 근거 문서 |
| --- | ---: | --- | --- |
| `gtc/` | 56 tif, 79.3 GB | GTC(Sigma0, TF 없음) 대조군 | [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md) |
| `water/` | 123 tif, 46.9 GB | 고정 임계값(−16 dB) 수체 마스크 | [WATER_AREA_KR.md](../water/WATER_AREA_KR.md) · Otsu 도입 전 방식 |
| `excluded_china_japan/` | 16 tif, 10.1 GB | 한반도 0% 프레임의 RTC | [SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md) · [FOREIGN_FRAME_COST_KR.md](FOREIGN_FRAME_COST_KR.md) |

**지우기 전에 옮긴 것** — 삭제 대상 안에 재생성 불가·소량 자료가 섞여 있었다.

- `excluded_china_japan/`의 **원본 zip 3개**(`B5F3`·`8B48`·`B2F4`, 2.0 GB)는
  E:에 사본이 없는 **유일본**이었다 →
  `E:\06_SAR_system_archive\excluded_china_japan\`로 이동. 타국 프레임 비용
  집계의 증거물이라 남긴다(다시 받으려면 CDSE 재다운로드).
- `water/flood_hotspots_{strict,relaxed}.geojson`(4.7 MB) →
  `downloads/_archive/water_meta/`로 백업.

**폴더 상수는 그대로 둔다.** `s1.core.paths`의 `GTC_DIR`·`WATER_DIR`·
`EXCLUDED_DIR`는 정의만 남아 있고, 해당 배치를 다시 돌리면 폴더가 새로 생긴다
(`batch_grd_gtc`, `build_water_per_date`, `flood_hotspots` 등). 지금 그 도구들을
돌리면 **빈 폴더에서 시작**한다는 것만 알고 있으면 된다.

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
5. **문서에 적힌 경로·용량을 그대로 믿지 말고 실측한다.** 이 문서의 초판도
   기존 문서의 "D:로 이동 후 junction"을 그대로 옮겨 적었다가, 실제로는
   `sentinel1_grd`도 junction(E:)이라는 점을 빠뜨렸다. `Get-Item`의 `LinkType`
   으로 확인하면 몇 초면 된다.
