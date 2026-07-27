# RTC 속도·품질 벤치마크 — SNAP vs sarsen, DEM 소스 비교 (2026-07-27)

SNAP-free RTC(sarsen)가 이 프로젝트 S1C 데이터에서 동작함을 검증한 뒤
([RTC_SARSEN_KR.md](RTC_SARSEN_KR.md)), 실사용 관점에서 SNAP과 정량 비교한다.

측정 대상은 네 가지다.

1. **속도(Part 1)** — 파일 용량 3분위(소/중/대)에서 3장씩 총 9장을 SNAP RTC와
   sarsen RTC로 각각 처리해 시간을 재고, **왜 차이가 나는지**를 출력 픽셀수·
   throughput(Mpx/s)로 정량 분석.
2. **DEM 소스(Part 2)** — 같은 SNAP으로 **자동 다운로드 Copernicus 30m(C:)** vs
   **로컬 COP30(D:)** 로 RTC를 돌려 dB·지오코딩 차이 확인.
3. **Frost 동일 하이퍼파라미터(Part 3)** — SNAP(RTC+SNAP Frost) 총시간 vs
   sarsen(RTC)+로컬 Frost 총시간(윈도우·damping을 동일하게 맞춤).
4. **NGII 5m DEM(Part 4, 후속)** — NGII 5m로 SNAP·sarsen RTC → COP30 대비 처리
   시간, 지형보정(TC) 품질, 수체 탐지 정확도, 후방산란계수(γ0 dB) 분포 차이.

> **공정성 원칙(중요)**: 모든 *timing* 런은 **단독 실행**한다(다른 무거운 작업과
> 병행 금지). 목적은 이 머신에서 Sentinel-1 **한 장의 RTC 최단 처리시간**을 재는
> 것이므로, 자원 경쟁이 있으면 수치가 오염된다. 아래 시간은 그 원칙하에 측정.

---

## 1. 방법 / 표본

- **표본 선택**: `downloads/sentinel1_grd`의 45장을 파일 크기로 정렬해 3분위
  (소/중/대)로 나누고, 각 분위에서 크기가 고르게 벌어지도록 3장씩 선택
  (`benchmark_rtc.py: pick_scenes_by_bucket`). 선택된 9장:

  | 버킷 | 씬(끝 4자) | 용량 |
  | --- | --- | --- |
  | 소 | 754B / 9A73 / 392D | 434 / 910 / 1029 MB |
  | 중 | 3C22 / D298 / 5C8D | 1035 / 1160 / 1240 MB |
  | 대 | DD29 / 376D / 525F | 1253 / 1293 / 1679 MB |

- **순차·비병렬**: 한 씬에서 SNAP → sarsen → 로컬 Frost 순으로 하나씩. 두 도구를
  동시에 돌리지 않는다(`benchmark_rtc.py`가 실행 전 gpt/java 프로세스 감시).
- **측정 지표**:
  - `wall_s` — 프로세스 전체 벽시계(conda run·JVM/파이썬 기동·zip SSD 복사·추출·
    DEM 준비 등 실사용 오버헤드 포함).
  - `process_s` — 워커가 보고한 핵심 처리(`PROCESS_SECONDS`). SNAP=gpt 그래프 실행,
    sarsen=지형보정+dB.
  - `px`, `throughput(Mpx/s)` = 출력 픽셀수 / process_s. **해상도 차이를 보정한
    공정 지표**(SNAP 10m vs sarsen COP30 ~30m).
- **도구/환경**:
  - SNAP: `_snap_rtc_one.py`(env `s1_snappy`). Terrain-Flattening+Terrain-Correction,
    출력 10m, Frost 스펙클(윈도우·damping은 로컬과 동일하게 지정). DEM은 SNAP
    자동 Copernicus 30m(C: `.snap/auxdata/dem`로 자동 다운로드).
  - sarsen: `rtc_sarsen.py`(env `sarsen_clean`, sarsen 0.9.6 + xarray-sentinel main).
    로컬 COP30(D:) + EGM2008 보정, 스펙클 없음, 출력 ~30m(COP30 격자).
  - 로컬 Frost: sarsen dB 산출물을 linear로 되돌려 `filtering.frost_filter`
    (동일 윈도우·damping) 적용 후 dB(스펙클은 linear에서 걸어야 하므로).
  - 코드: `benchmark_rtc.py`, `_snap_rtc_one.py`, `compare_rtc.py`,
    `prepro_grd_gpt.py`(Speckle-Filter에 filterSizeX/Y·dampingFactor 주입 추가).

---

## 2. DEM 소스 비교 (SNAP, 씬 754B)

### ⚠️ SNAP 외부 DEM은 VRT/폴더를 못 읽는다

로컬 COP30를 SNAP 외부 DEM으로 바로 넣으면 실패한다:

```text
org.esa.snap.core.gpf.OperatorException:
No product reader found for D:\00_COP30\COP30_hh.vrt
  at org.esa.snap.dem.dataio.FileElevationModel.init(FileElevationModel.java:55)
```

SNAP `FileElevationModel`은 GDAL VRT(및 타일 폴더) 리더가 없다. 따라서 로컬
COP30(D: `00_COP30\COP30_hh`의 26,474개 타일을 묶은 `COP30_hh.vrt`)를 SNAP에
쓰려면 **씬 bbox로 단일 GeoTIFF를 클립**해 `externalDEMFile`로 넣어야 한다
(`gdalwarp`로 클립 → `cop30_754b_ortho.tif`, 13288×7304, ~30.9m).
sarsen은 `rtc_sarsen.py --external-dem`이 VRT를 내부에서 gdalwarp로 처리하므로
이 제약이 없다.

### 결과 (754B, speckle none): 이 씬에선 자동 DEM이 로컬 COP30보다 덜 채워졌다

같은 씬·같은 bbox인데 DEM 소스만 바꿔 비교:

| DEM 소스 | 산출물 | 격자(10m) | 유효 스와스 | 파일크기 |
| --- | --- | --- | --- | --- |
| SNAP 자동 Copernicus 30m (C:) 1·2차 | `_rtc_db_autoc(2).tif` | 32183×13678 | **1.9%** | 45 MB |
| 로컬 COP30 클립 (D:, EGM on) | `_rtc_db_cop30d.tif` | 32183×13678 | **59.7%** | 1119 MB |

754B(SE 해안·해상 위주 씬)에서 SNAP 자동 Copernicus가 두 번 다 DEM 타일을
**`N33/E127` 1개만** assemble 해(로그 확인) 유효 스와스가 1.9%에 그쳤다. 같은 씬을
로컬 COP30(D:)로 넣으면 59.7% 유효. 즉 **이 씬에서는 자동 DEM 경로가 커버리지를
놓쳤다**(원인은 자동 다운로드 타이밍/해상 커버리지로 추정, 씬 국한).

> **정정(2026-07-27)**: 처음엔 이를 "자동 DEM이 상시 불안정"으로 확대 해석했으나
> **틀렸다**. 기존 `rtc_grd_frost/`(자동 DEM) 산출물을 **0이 아닌 스와스 기준**으로
> 재검증하니 모두 **정상 γ0**였다 — 낮은 "유효%"는 DEM 실패가 아니라 **스와스가
> bbox 대비 작아 생긴 정상 0-채움**이었다:
>
> | 씬(끝) | 0-채움% | 스와스% | 스와스 median dB | 판정 |
> | --- | --- | --- | --- | --- |
> | 427D | 28.7 | 71.3 | −6.9 | ✅ 정상 |
> | 4265 | 30.8 | 69.2 | −6.4 | ✅ 정상 |
> | 74FD | 70.6 | 29.4 | −7.3 | ✅ 정상(작은 스와스) |
> | 6942 | 83.4 | 16.6 | −7.5 | ✅ 정상(작은 스와스) |
> | F040 | 95.7 | 4.3 | −6.9 | ✅ 정상(작은 스와스) |
>
> **결론: 자동 Copernicus DEM 파이프라인은 기존에 정상 동작했다.** 754B만 이번에
> 부족했던 것이며, 상시 문제가 아니다.

### 결론 (Part 2)

- **자동 Copernicus DEM(C:)은 육상 씬에서 정상**이며 기존 파이프라인에 문제 없었다.
  다만 754B처럼 특정 씬에서 자동 assemble이 커버리지를 놓칠 수 있으니, **재현성·
  완결성이 중요하거나 특정 씬이 의심되면 로컬 COP30(D:)로 클립해 external DEM**을
  쓰는 것이 안전한 대안이다.
- 벤치마크(Part 1)에서 SNAP·sarsen에 **동일하게 로컬 COP30(D:)** 를 쓰는 이유는
  "자동이 나빠서"가 아니라, 두 도구가 **완전히 같은 DEM**을 쓰게 해 속도 비교를
  공정하게 만들고(DEM을 변수에서 제거) 754B류 커버리지 편차를 배제하기 위해서다.
  sarsen은 VRT를 내부 gdalwarp로 처리, SNAP은 VRT를 못 읽어 클립 GeoTIFF가 필요.
- 신규 씬의 일상 처리는 **기존처럼 자동 DEM**으로 충분하다(육상 씬).

---

## 2.5 교차검증 — sarsen RTC vs SNAP RTC (동일 DEM, 754B)

같은 씬(754B)을 **같은 COP30(D:)** 으로 sarsen(EGM2008)과 SNAP(외부 COP30 클립,
EGM96)이 각각 지형보정한 결과를 `compare_rtc.py`로 대조(SNAP을 sarsen 격자로
리샘플 후 공통 유효화소 비교):

| 항목 | 값 | 해석 |
| --- | --- | --- |
| 공통 유효화소 | 27,474,257 (39.5%) | |
| **정합(정수 픽셀 시프트)** | **dy=0, dx=0에서 상관 최대 (r=0.879)** | ✅ **지오코딩 위치 완전 일치** |
| sarsen dB | mean −20.34 / median −20.08 | |
| SNAP dB | mean −21.78 / median −20.62 | |
| A−B (sarsen−SNAP) | median **+0.96** / mean +1.45 / std 3.0 dB | 라디오메트리 ~1 dB 수준 일치 |
| \|A−B\| ≤ 2 dB | 64.6% | |
| Pearson r | 0.879 | |

- **지오코딩**: 시프트 0에서 상관 최대 → sarsen의 Range-Doppler 지오코딩이 SNAP과
  **같은 위치**에 픽셀을 놓는다(계통적 위치 오차 없음). EGM2008 보정이 유효함을 방증.
- **후방산란(γ0 dB)**: 중앙값 차 **+0.96 dB**(sarsen이 약간 밝음), r 0.88. std 3 dB
  산포는 두 영상 모두 **스펙클 미필터** + **10m↔30m 해상도차 리샘플** 때문(예상 범위).
- **~1 dB 계통 오프셋의 원인**: sarsen γ0(David Small flattening-gamma)와 SNAP
  Terrain-Flattening의 면적 정규화 방식 차이 + EGM96 vs EGM2008(<1 m) + 해상도 차.
- **함의**: 고정 −16 dB 임계값 수체 탐지에 sarsen을 그대로 넣기 전, 이 ~1 dB
  오프셋을 반영(임계값을 ~−15 dB로 재보정하거나 Otsu 같은 적응형 임계값 사용)하면
  된다. 위치는 그대로 신뢰 가능.

---

## 3. Part 1 — SNAP vs sarsen RTC 속도, 그리고 "왜 다른가"

두 도구 모두 **로컬 COP30(D:)** 로 같은 씬을 단독 처리(SNAP은 클립 GeoTIFF external,
sarsen은 VRT 직접). SNAP은 파이프라인 표준 **10m**, sarsen은 COP30 native **~30m**.

### 전체 표 (9장, cop30 모드, Frost 5×5 d2)

씬당 `process_s`(핵심 처리: SNAP=gpt 그래프, sarsen=지형보정+dB), 출력 픽셀수,
throughput(Mpx/s)을 잰다. 9장 벤치마크 진행 중 — 표는 완료 후 `rtc_benchmark.csv`로
채운다. **첫 씬(754B, 소버킷) 확정치**:

| 씬 | 도구 | process | wall | 출력 px | 유효 | throughput |
| --- | --- | --- | --- | --- | --- | --- |
| 754B | SNAP(10m) | **27.9분** | 28.4분 | 440M | 60% | 0.26 Mpx/s |
| 754B | sarsen(30m) | **16.4분** | 17.3분 | 70M | — | 0.07 Mpx/s |

### 왜 다른가 (핵심 결론)

754B 기준, **sarsen이 절대 처리시간은 더 빠르다(16.4분 vs 27.9분, 0.59배)**. 그런데
이는 sarsen이 **더 거친 격자(COP30 30m)** 로 출력해 **픽셀수가 6.3배 적기** 때문이지,
엔진이 더 빨라서가 아니다.

- **해상도 = 1차 요인**: 처리시간은 입력 파일 용량보다 **출력 픽셀수**에 비례한다.
  SNAP은 10m(440M px), sarsen은 30m(70M px). IW GRD 스와스 크기는 씬마다 비슷하므로
  픽셀수 차이는 대부분 이 10m↔30m 해상도 차에서 온다.
- **throughput(해상도 보정)에선 SNAP이 더 빠르다**: SNAP 0.26 vs sarsen 0.07 Mpx/s
  → **픽셀당 SNAP이 ~3.7배 빠르다**. SNAP은 JVM 멀티스레드(`-q 8 -c 14G`) 타일
  스케줄러라 대량 픽셀을 병렬 처리하고, sarsen은 numpy+dask로 상대적으로 느리다.
- **정리**: "SNAP이 느리다"가 아니라 "SNAP이 더 조밀한 10m를 만든다". 같은 30m로
  맞추면 SNAP이 sarsen보다 빠를 것(픽셀당 3.7배). 반대로 sarsen을 10m로 올리면
  ~6배 느려진다. **실사용에선 coarse(30m)면 충분한 광역 수체 탐지에 sarsen이 유리**
  (더 빨리 끝남), **정밀 10m가 필요하면 SNAP이 유리**.
- **오버헤드(wall−process)**: SNAP wall에는 JVM 기동·orbit 자동 다운로드가, sarsen
  wall에는 zip 추출·COP30 클립·EGM 보정이 들어간다. 둘 다 씬당 ~0.5–1분 수준.
- **cop30 모드 부가비용**: SNAP external DEM용 COP30 클립(gdalwarp)은 씬당 ~6초로
  무시할 수준. 단 SNAP이 external DEM 전체를 유효 처리하므로(자동 DEM처럼 건너뛰지
  않음) 10m 전체 처리 시간이 정직하게 다 든다.

_9장 전체 표로 버킷(용량)별 경향까지 확인 후 위 결론을 정량 보강한다. IW GRD는
파일 용량이 달라도 스와스 픽셀수가 비슷해, 용량보다 해상도·씬 길이가 시간을
지배할 것으로 예상._

---

## 4. Part 3 — Frost 동일 하이퍼파라미터 총시간

같은 Frost 설정(윈도우·damping 동일)에서:

- (a) SNAP RTC + **SNAP Frost** (그래프 내부, `process_s`)
- (b) sarsen RTC + **로컬 Frost**(`filtering.frost_filter`, `process_s + frost_s`)

측정 중(9장 벤치마크에 통합). 로컬 Frost는 754B(69.5M px)에서 약 59s로 확인됨.

---

## 5. Part 4 — NGII 5m DEM vs COP30 (후속, 단독 실행)

- DEM: `D:\00_DEM\DEM_5m\dcd_5m_dem.tif`(남한 5m). NGII는 **북한·치악산 미포함** →
  **치악산 제외 남한 육상**에서만 비교(수체·해상 제외).
- 절차: 같은 씬을 (1) SNAP+NGII, (2) sarsen+NGII, (3) SNAP+COP30, (4) sarsen+COP30로
  RTC. 처리시간(단독)·TC 기하품질·수체 탐지 정확도·γ0 dB 분포를 비교.
- NGII는 투영좌표계(예: EPSG:5186)일 가능성 → WGS84 재투영·씬 bbox 클립 후 사용.
  정표고 기준이라 EGM 보정 적용(NGII 수직계가 EGM2008과 미세하게 다른 점은 명시).

본 파트는 Part 1–3 및 교차검증 종료 후 단독으로 진행한다.

---

## 6. 결론

모든 파트 종료 후 기입.
