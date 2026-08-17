# 확정 전처리 사양 — 한반도 VH RTC (2026-08-18)

한반도 전체 25·26년(→22~24년 확장) 시계열 비교를 위한 **전처리 규격 확정본**.
"무엇을 왜 이 값으로 정했는가"와 "어느 DEM을 써야 하는가"를 한 곳에 모은다.
바꾸려면 이 문서를 고치고, 이유를 적는다.

관련: [PROCESS_202507_202607_KR.md](PROCESS_202507_202607_KR.md)(전 과정 서술) ·
[FILTER_COMPARISON_KR.md](FILTER_COMPARISON_KR.md)(필터 근거) ·
[BASELINE_DESIGN_KR.md](../drought/BASELINE_DESIGN_KR.md)(비교 설계) ·
[ISSUES_KR.md](../worklog/ISSUES_KR.md)

---

## 1. DEM — 한반도 전체를 덮는 것은 하나뿐이다

### 1-1. 왜 external DEM인가

SNAP에 `demName="Copernicus 30m Global DEM"`(자동 다운로드·캐시)을 주면 **하구
수역을 무효로 해석해 결측을 만든다.** 영산강 제약면적의 **20.2%**가 그렇게
날아갔다(ISSUES #2). 같은 COP30 값이라도 **GeoTIFF로 구워 external로 물리면
결측이 0.00%**다.

재처리 실측이 이를 뒷받침한다 — `F336`(25-07-01)은 자동 DEM일 때 **0.05 GB**,
external DEM으로 다시 구우니 **1.16 GB**가 됐다(23배). 산출물 대부분이 결측
이었다는 뜻이다.

> ⚠ **VRT는 안 된다.** `externalDEMFile`에 GDAL VRT를 주면
> `No product reader found`로 그래프가 실패한다(ISSUES #1). **GeoTIFF로 구울 것.**

### 1-2. 보유 DEM과 커버리지

한반도 폴리곤 범위는 **lon 124.18~130.67, lat 33.11~43.00**이다.

| DEM | 범위 (lon / lat) | 용량 | 한반도 전체 |
| --- | --- | ---: | --- |
| **`korea_peninsula_cop30.tif`** | **123.50~131.30 / 32.80~43.30** | **1.6 GB** | ✅ **덮음** |
| `korea_full_cop30.tif` | 125.00~131.00 / 32.90~39.90 | 0.68 GB | ❌ 북쪽 39.9~43.0, 서쪽 124.2~125.0 부족 |
| `korea_cop30.tif` | 125.40~129.90 / 33.80~38.70 | 0.50 GB | ❌ 제주(33.1~33.6) 빠짐 |
| `han_cop30.tif` | 125.67~129.87 / 35.64~39.24 | 0.42 GB | ❌ 부산·목포·제주 빠짐 |
| `nakdong`·`geum`·`seomjin`·`yeongsan` | 유역별 clip | 0.2~0.4 GB | ❌ 해당 유역만 |

전부 **COP30 · EPSG:4326 · 해상도 0.000278°(≈30 m) · nodata −32768** 로 동일하다.
다른 것은 **범위뿐**이다.

### 1-3. 확정 — `korea_peninsula_cop30.tif`

**한반도 대상 처리는 전부 이것을 쓴다.**

```bash
--dem downloads/dem_basin/korea_peninsula_cop30.tif
```

- **DEM이 덮지 않는 영역은 산출물에서 무효(결측)로 남는다.** 유역 단위 작업에는
  유역 clip이 빠르지만, **범위가 다른 DEM으로 만든 산출물을 섞으면** 어떤 씬은
  제주가 있고 어떤 씬은 없는 상태가 된다. 오류 없이 숫자만 틀린다(ISSUES #13).
- 유역 clip DEM(`han_`·`nakdong_` 등)은 **유역 단독 분석 전용**으로만 남긴다.

> **⚠ 이미 처리한 79씬은 `korea_full_cop30.tif`로 구웠다.** 남한 궤도 위주라
> 남한·제주는 문제없지만, **북위 39.9° 이북(북한 북부)이 프레임에 걸린 씬은 그
> 구간이 결측**이다. 한반도 전체 비교로 확장할 때 이 씬들의 북부 결측 여부를
> 확인하고, 필요하면 `korea_peninsula_cop30.tif`로 재처리해야 한다
> ([TODO_KR.md](../worklog/TODO_KR.md) 추적).

### 1-4. DEM을 새로 구울 때

```bash
conda run -n s1_snappy python -m s1.tools.dem.make_basin_dem \
    --bounds 124.0,32.8,131.5,43.5 --name korea_peninsula
```

- COP30 타일을 모아 GeoTIFF로 굽는다(내부적으로 VRT를 거치지만 **최종 산출은
  GeoTIFF**).
- 여유를 0.5°쯤 두는 이유: 프레임 가장자리가 DEM 밖으로 나가면 그만큼 무효가
  된다. 반대로 DEM이 넓어도 처리 시간에는 거의 영향이 없다.

---

## 2. 전처리 그래프 — 확정 파라미터

SNAP `gpt`(snapista) 그래프. 정의는
[prepro_grd_gpt.py](../../s1/preprocess/prepro_grd_gpt.py)의 `build_grd_rtc_graph`.

```text
Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration(Beta0)
     → Speckle-Filter(Frost) → Terrain-Flattening → Terrain-Correction
     → LinearToFromdB → Write
```

| 항목 | **확정값** | 근거 |
| --- | --- | --- |
| **편파** | **VH** | GEE 수체탐지와 정합. VV 대비 물/육지 대비가 안정적이고 풍파에 덜 민감. VV와는 약 6 dB 오프셋이라 **절대 섞지 않는다** |
| **Speckle 필터** | **Frost** (SNAP 기본 3×3, damping 2.0) | VV·VH 양쪽에서 검증(3절) |
| **DEM** | **external `korea_peninsula_cop30.tif`** | 1절 |
| EGM 지오이드 보정 | **끄기**(`--dem-egm` 미사용) | COP30은 이미 타원체고. 이중 적용 시 약 25 m 어긋남(ISSUES #3) |
| 궤도 | Sentinel Precise (Auto Download), polyDegree 3, `continueOnFail=false` | 예측궤도는 수십 m 오차. 실패를 조용히 넘기지 않는다 |
| 열잡음 제거 | `removeThermalNoise=true` | 수체는 저후방산란이라 열잡음 비중이 크다 |
| 캘리브레이션 | **Beta0만** 출력 | Terrain-Flattening 입력 요건 |
| Terrain-Flattening | 적용 (BILINEAR) | 지형 밝기 왜곡 정규화 = RTC의 핵심. 없으면 산지 사면이 물로 오판 |
| Terrain-Correction | 10 m, BILINEAR(img·dem) | |
| 좌표계 | EPSG:4326 | |
| 출력 | dB, GeoTIFF-BigTIFF | |
| gpt 옵션 | `-q 8 -c 14G` (단독) / `-c 7G` (배치 2개 병렬) | gpt가 1코어 남짓만 써서 병렬이 유리. RAM 32 GB를 넘기지 않게 캐시를 나눈다 |

### 실행

```bash
conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc_frost \
    --month 202608 --pol VH --out-dir downloads/rtc_grd_frost_vh --out-tag _vh \
    --dem downloads/dem_basin/korea_peninsula_cop30.tif --gpt-c 7G --oldest-first
```

기존 산출물을 **다시 구울 때**는 배치가 건너뛰므로 삭제 후 재실행한다:

```bash
powershell -File scripts/rebake_vh_extdem.ps1 -Month 202608 -Scenes "…" -DryRun
```

---

## 3. Speckle 필터를 Frost로 확정한 근거

같은 씬을 필터만 바꿔 처리하고 4축으로 쟀다. **VV(2026-07-23)와 VH(2026-08-17)
양쪽에서 결론이 같다.**

**VH 실측** (26-07-20 `F314`, rel 134, crop 1024px)

| 필터 | ENL | 가는선 보존% | 경계 보존% |
| --- | ---: | ---: | ---: |
| **Frost** | 3.40 | **67.1** | **69.6** |
| Lee | 4.45 | 64.2 | 45.3 |
| Refined Lee | **8.33** | 49.4 | 20.0 |
| (무필터) | 1.78 | 100.0 | 100.0 |

- Refined Lee가 speckle은 가장 잘 잡지만 **가는 선을 절반, 경계를 80% 날린다.**
  소하천이 사라지면 수체 면적이 줄고, 경계가 뭉개지면 임계값이 흔들린다.
- **수체 판별의 기준은 ENL이 아니다.** 가는 수로·경계 보존이 우선이다.
- VH는 VV보다 speckle이 심하다(무필터 ENL 5.2 → 1.78). 같은 필터의 ENL이 낮게
  나오는 것은 이 때문이지 필터가 덜 듣는 게 아니다.

한계: 씬 1장·crop 1곳. 순위는 VV와 일치하나 절대 수치 인용 시 표본을 밝힐 것.

---

## 4. 씬 선별 기준

| 기준 | 값 | 이유 |
| --- | --- | --- |
| 판정 방법 | **footprint**(zip 안 `preview/map-overlay.kml`) | bbox는 기울어진 프레임의 빈 삼각형까지 "촬영"으로 세어, 100% 바다인 프레임을 육지로 오판한다 |
| 경계 | `Korea_Peninsula.geojson`(남북+제주) | ⚠ `South_Korea.geojson`은 부산·강릉·여수·해남·완도·제주를 제외한다(ISSUES #7) |
| 최소 겹침 | **1%** | 중국·일본 프레임이 모서리만 스치고 통과하는 것을 막는다 |
| 대조 키 | **관측 시작시각 + 절대궤도** | 씬 ID 끝 4hex는 제품 생성 해시라 같은 촬영도 다르게 센다(ISSUES #16) |

---

## 5. 수체 판별로 넘길 때의 규격 (참고)

이 저장소는 **RTC까지**다. 다음 단계에 넘기는 규격만 적어 둔다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 임계값 방식 | 궤도별 **타일기반 Otsu** | 전역 Otsu는 −8 dB대로 장면 절반을 물로 오판 |
| **VH fallback** | **−20 dB** (더 안전하게는 −19) | VH 골짜기 실측 중앙값 −22.15 dB + 여유 2 dB. **물을 놓치지 않는 쪽으로 민다** |
| 그룹 키 | (관측일, 절대궤도) | 궤도가 다르면 입사각·dB 분포가 다르다 |
| 비교 단위 | (상대궤도 × 대권역) | [BASELINE_DESIGN_KR.md](../drought/BASELINE_DESIGN_KR.md) |

VV 기준 fallback −16 dB를 VH에 그대로 쓰면 **물을 거의 못 잡는다.**

---

## 6. 산출물 규약

```text
downloads/rtc_grd_frost_vh/<입력 zip stem>_rtc_db_vh.tif
```

- 입력이 `..._6D9F.SAFE.zip`이면 산출물은 `..._6D9F.SAFE_rtc_db_vh.tif`가 된다.
  **씬 ID 뒤에 밑줄을 가정한 패턴(`_6D9F_`)으로 찾으면 놓친다**(ISSUES #15).
- 산출물에 **어떤 DEM을 썼는지 기록이 없다.** 지금은 실행 로그(`temp/logs/*.log`의
  `DEM:` 줄)를 뒤져야 안다 — 메타데이터에 남기는 것이 과제로 남아 있다.

## 7. 바뀌면 안 되는 것 (요약)

1. **편파 VH** — VV와 섞지 않는다(약 6 dB 오프셋)
2. **필터 Frost** — Refined Lee는 가는 수로를 절반 날린다
3. **DEM `korea_peninsula_cop30.tif`** — 범위가 다른 DEM을 섞지 않는다
4. **EGM 보정 끄기** — COP30은 타원체고
5. **10 m · EPSG:4326 · dB**
