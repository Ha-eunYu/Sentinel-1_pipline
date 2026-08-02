# 레이오버·섀도 마스크 산출 — 계획·실행·이슈

**2026-08-03 · `make_ls_mask.py`**

Terrain-Flattening은 **방사보정**이다. 밝기를 지형으로 정규화할 뿐, 그 화소가
**못 쓰는 화소라고 표시하지 않는다.** 그래서 섀도가 값으로 남고, 실측상
물 오탐 위험이 정상역의 **10배**다. OPERA는 섀도의 90% 이상을 nodata로 뺀다.
우리도 같은 처리를 하려면 **마스크가 필요하다.**

> 근거: [gee/ASF_HyP3/RTC_VS_OPERA_QUANT_KR.md](../gee/ASF_HyP3/RTC_VS_OPERA_QUANT_KR.md) §3-a
> 검증: `gee/Korea_WaterDetection_2025_2026/ls_mask_verify.py`

---

## 1. 왜 필요한가 — 실측

AOI 전체, 2026-07-20, SNAP γ⁰ vs OPERA γ⁰.

| 구간 | AOI 비율 | OPERA 유효 | SNAP 유효 | SNAP 중앙 | **−20 dB 미만** |
|---|---:|---:|---:|---:|---:|
| 정상 | — | 100% | 99% | −13.2 dB | 1.8% |
| layover | 1.2~3.7% | 100% | 100% | −14.6 dB | **0.4%** |
| **shadow** | 0.003~0.019% | **5~11%** | **86~93%** | **−16.8 dB** | **14.6~23.8%** |

**레이오버는 안전하고 섀도는 위험하다.** 같은 −1.4~−1.9 dB 과보정인데 결과가
반대인 이유는 **원래 밝기**다 — 레이오버는 여러 산란체가 겹쳐 원래 밝아서
임계에서 멀고, 섀도는 원래 어두워서 조금만 더 어두워져도 임계를 넘는다.

**총량은 현 유역에서 작다**(낙동강 오탐 추정 0.19 km², 탐지 수체의 0.06%).
다만 **산지 확장·ASC/DESC 혼용 시계열 전에는** 처리해야 한다 — 궤도마다 섀도
위치가 달라 **날짜 간 계단**이 생긴다.

---

## 2. 계획 — 왜 경량 그래프인가

마스크는 **DEM + 궤도 기하**만으로 정해진다. 방사정보가 전혀 안 들어간다.
그래서 방사보정 단계를 전부 건너뛸 수 있고, **기존 RTC 35장을 재처리하지
않아도 된다.**

```text
정식 RTC   Read → Orbit → TNR → Calibration(β⁰) → Speckle → TF → TC → dB
이 그래프  Read → Orbit → BandSelect → TC(mask only)
```

`prepro_grd_gpt.py`에는 `saveLayoverShadowMask="true"`를 넣었으므로
**앞으로 처리하는 것은 자동으로 마스크가 붙는다.** 이 스크립트는 그 전에
만든 것들을 메우는 용도다.

---

## 3. ⚠️ 이슈 — 실패 3건과 원인

### 3-1. `g.run()`에 gpt 옵션을 안 넘겨 **예외 없이** 죽었다

```python
g.run()                                      # ❌ 잘린 파일이 남는다
g.run(gpt_options=["-q", "8", "-c", "10G"])  # ✅
```

**증상**

- 프로세스가 죽는데 **예외도 스택트레이스도 없다.**
- 파일은 남지만 열면 `TIFFReadEncodedTile() failed`, `Using code not yet in table`.
- 쓰다 만 파일을 읽었더니 **전 밴드가 0**이었다 → "마스크가 비었다"고 오진했다.
- 파일이 **잠겨 있어 삭제도 실패**했고, `-ErrorAction SilentlyContinue`로
  조용히 넘어가 다음 실행이 "이미 있음"으로 건너뛰었다.

**원인** — 정식 배치(`batch_grd_rtc_frost.py`)는 `-q -c`를 넘기는데 이 스크립트는
안 넘겼다. 타일 캐시 기본값으로는 전 씬 10 m(8.5억 화소) 출력을 못 버틴다.

**교훈** — 쓰는 중인 파일을 읽고 판단하지 말 것. 프로세스 종료를 먼저 확인한다.

### 3-2. 출력 밴드를 없앨 수 없다

```python
saveSelectedSourceBand="false"   # ❌
```

```text
Error: [NodeId: Terrain-Correction]
       Please select output band for terrain corrected image
```

**SNAP은 출력 밴드를 최소 1개 요구한다.** 산출물이 6.8 GB(Amplitude + mask,
int32 2밴드)라 절반으로 줄이려던 시도였는데 거부당했다. 되돌렸고, 실제로는
압축이 먹어 30 m 산출물이 130 MB다.

### 3-3. 전 씬 10 m가 과했다

되돌린 뒤 재실행했는데 **11분간 0 MB에서 멈췄다.** 원인을 특정하지 못했다.

10 m 전 씬은 **35,339 × 24,001 = 8.5억 화소**다. Terrain-Correction이 화소마다
DEM을 조회해 레이더 기하로 투영하므로 비용이 화소 수에 비례한다.

**조치 — 30 m로 낮춰 성립시켰다.**

| | 10 m | **30 m** |
|---|---:|---:|
| 화소 수 | 8.5억 | **9,400만** (1/9) |
| 결과 | 3회 실패 | **410초 성공** |
| 산출물 | (미완) | 130 MB |

**디버깅 반복이 9배 빨라진 것이 결정적이었다.** 10 m에서는 매번 수십 분을
기다리며 세 번 실패했는데, 30 m에서는 7분 만에 성립하고 원인도 없었다.

### 3-4. 확인된 것 — 밴드명은 문제가 아니었다

이 프로젝트에서 "이름 틀리면 조용히 빈 결과"가 반복돼 의심했으나, 실측 결과
`BandSelect`의 `Amplitude_VH`는 맞았다.

```text
S1C GRD 1SDV 밴드: ['Amplitude_VH', 'Intensity_VH', 'Amplitude_VV', 'Intensity_VV']
```

⚠ 단일편파(1SSV/1SSH) 제품에는 해당 편파만 있다. 없는 편파를 요구하면 여기서
걸린다.

---

## 4. 검증 — OPERA `mask.tif`와 대조

### ⚠️ 비트 배정이 **뒤집혀 있다**

```text
SNAP  `layover_shadow_mask`   1=layover  2=shadow   3=둘 다
OPERA `mask.tif` v1.0         1=shadow   2=layover  3=둘 다
```

그대로 비교하면 레이오버를 섀도로 세어 **겹침이 0에 가깝게 나온다.**
`ls_mask_verify.py`가 명시적으로 변환한다.

### 결과 (2025-07-18, 씬 1장, 30 m)

| 유역 | 공통화소 | OPERA L/S | SNAP L/S | **재현율** | 정밀도 | IoU |
|---|---:|---:|---:|---:|---:|---:|
| **낙동강** | 44,387,135 | 144,706 | 1,169,264 | **90.7%** | 11.2% | 0.111 |
| **금강** | 22,595,847 | 16,287 | 278,137 | **70.9%** | 4.2% | 0.041 |
| 섬진강 | 13,271,360 | 24,783 | 6,435 | 13.4% | 51.5% | 0.119 |

**GEE 근사 RTC는 이 재현율이 0.8%였다.**

| | GEE 근사 RTC | **SNAP 마스크** |
|---|---:|---:|
| OPERA L/S 재현율 | **0.8%** | **70.9 ~ 90.7%** |

GEE는 **국소 경사**만 봐서 "급경사"를 찍고, SNAP은 **DEM+궤도 기하로 실제
가림**을 계산한다. 레이오버·섀도는 비국소 현상이라 후자만 잡을 수 있다.

### 정밀도가 낮은 것은 안전한 방향이다

SNAP이 OPERA보다 **8배 많이** 찍는다(낙동강 117만 vs 14만). 더 **보수적**이다.

우리 질문은 "OPERA가 못 쓴다고 한 화소를 우리도 뺄 수 있는가"다.
더 빼는 건 안전하고, 못 빼는 게 위험하다. **재현율 90.7%면 충분하다.**

### 섬진강만 반대인 이유

**씬 1장으로만 검증했다.** `6D9F` 씬이 섬진강을 일부만 덮어서 OPERA가 찍은
24,783화소 중 대부분이 씬 밖이다. 전량 처리하면 해소된다.

---

## 5. 실행

```bash
# 30 m, 5대강 커버 상위 granule만
conda run -n s1_snappy python make_ls_mask.py \
    --pol VH --gpt-c 7G --pixel-spacing 30 \
    --out-dir downloads/ls_mask30 --only <씬ID,...>

# 검증
python gee/Korea_WaterDetection_2025_2026/ls_mask_verify.py

# 제약 안 실제 영향
python gee/Korea_WaterDetection_2025_2026/ls_mask_impact.py --lakes
```

### 입출력

| 구분 | 경로 |
|---|---|
| 입력 GRD | `downloads/sentinel1_grd/*.zip` |
| 입력 DEM | SNAP 자동 캐시 `~\.snap\auxdata\dem\Copernicus 30m Global DEM\` |
| **출력 마스크** | `downloads/ls_mask30/*_lsmask.tif` (밴드 2 = 마스크) |
| 검증 기준 | `gee/ASF_HyP3/data/{basin}/*_mask.tif` (OPERA) |

### 30 m를 그대로 써도 되는가

**된다.** OPERA 마스크 자체가 30 m이고 검증도 30 m에서 했다. 10 m dB에 씌울
때는 **최근접 확대**하면 된다 — 범주형이라 값이 안 섞이고, 레이오버·섀도는
지형 규모 현상이라 10 m 단위로 들쭉날쭉하지 않다.

| | 10 m | 30 m |
|---|---:|---:|
| granule당 | 약 60분 | **6.8분** |
| 38장 (2병렬) | 약 19시간 | **2.2시간** |

---

## 6. DEM — 두 갈래로 갈려 있다

| 코드 | DEM | 실체 |
|---|---|---|
| `make_ls_mask.py`, `batch_grd_rtc_frost.py` (SNAP) | `demName="Copernicus 30m Global DEM"` | **SNAP 자동 다운로드** — `~\.snap\auxdata\dem\`, 112타일 3.0 GB |
| `ls_check.py`, `reservoir_series.py` (파이썬) | `D:\00_COP30\COP30_hh.vrt` | 로컬 전지구 사본 — 26,482타일 723 GB |

둘 다 Copernicus GLO-30이지만 **포장이 다르다**(타일 3600×3600 vs 3601×3601 —
가장자리 처리 차이). 값 자체는 같은 제품에서 왔다.

**엄밀히는 SNAP에 `externalDEMFile`로 로컬 VRT를 물리는 게 맞지만, RTC 35장이
이미 자동 캐시로 처리됐으므로 지금 바꾸면 그것들과 어긋난다. 현 상태 유지가
일관된다.**

### NGII DEM은 쓰지 않는다

| | |
|---|---|
| 남한만 | 한강 대권역은 **북한부를 포함**한다 |
| 결측 | **치악산이 빠져 있다** — 산지 경사 분석에 치명적 |
| 5m/1m | 1m는 5m의 리샘플이라 정보량이 같다 |

초판에 쓴 `ngii_5m_aoi.tif`는 거기에 AOI 클립까지 돼 있어 126.30~127.70E만
덮었고, 범위 밖이 0으로 채워져 **경사 0°가 "유효"로 통과**했다(이슈 #21).

---

## 7. 남은 일

- [ ] 38 granule 30 m 마스크 전량 (2병렬, 약 2.2시간) — **실행 중**
- [ ] 제약 안 실제 영향 측정 (`ls_mask_impact.py`) — L/S%가 커도 그 자리가
      물이 아니었으면 면적은 안 변한다. **재봐야 안다.**
- [ ] 섀도를 제약에서 빼는 처리를 `local_change.py`·`reservoir_series.py`에 반영
- [ ] 전량 마스크로 `ls_mask_verify.py` 재실행 — 섬진강 재현율 확인

---

## 관련 문서

- [gee/ASF_HyP3/RTC_VS_OPERA_QUANT_KR.md](../gee/ASF_HyP3/RTC_VS_OPERA_QUANT_KR.md) — γ⁰ 정량 평가
- [gee/ASF_HyP3/SLOPE_STRATIFICATION_KR.md](../gee/ASF_HyP3/SLOPE_STRATIFICATION_KR.md) — 경사 층화
- [gee/PITFALLS_KR.md](../gee/PITFALLS_KR.md) — 조용히 틀리는 함정
