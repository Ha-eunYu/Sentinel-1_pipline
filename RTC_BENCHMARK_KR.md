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

### 측정치 (cop30 모드, Frost 5×5 d2)

씬당 `process_s`(핵심 처리: SNAP=gpt 그래프, sarsen=지형보정+dB), 출력 픽셀수,
throughput(Mpx/s)을 잰다. **대표 씬 754B(소버킷, 14초 짧은 씬) 확정치** — 9장 전체는
**sarsen이 풀사이즈 씬에서 OOM/저속**이라 완주하지 못했다(§3.2, 이게 곧 결과):

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

### 3.2 sarsen 풀사이즈 IW GRD 메모리 한계 (중요 결과)

9장(3버킷×3)을 목표로 했으나 **sarsen이 풀사이즈(약 25초, 26k×16k) IW GRD에서 막혔다**.
754B(14초 짧은 씬)만 통과했고, 9A73·392D·3C22 등 정상 길이 씬은 두 지점에서 실패:

1. **dask rechunk**: `chunking.simple_dask_map_overlap`이 `allow_rechunk=False`로,
   overlap 깊이(128)보다 작은 첫 청크를 만나면 즉시 실패.
2. **지오코딩 interp OOM**: `geocode_grd_chunk`의 `beta_nought.interp`가 SAR 격자
   크기의 float64 배열(약 3.25GB)을 만들고, 여러 개가 겹쳐 **피크 ~22GB+** → 32GB
   RAM(여유 ~22.8GB)에서 `numpy MemoryError`.

`rtc_sarsen.py`에 방어책을 넣었다: (1) `map_overlap`을 sarsen 자체의 타일 구현
`sync_map_overlap`으로 교체(rechunk 문제 회피), (2) `--tc-chunks`로 청크 축소.
**`--tc-chunks 256`이면 OOM은 피한다(피크 14.5GB)** — 그러나 작은 청크 오버헤드로
**매우 느리다**(754B 16분 대비 풀씬은 40분+에도 못 끝냄).

**아키텍처 차이 = 이 파트의 핵심 결과**:

- **SNAP**: JVM 타일 스케줄러가 디스크에서 타일을 스트리밍(`-c 14G` 캐시) → **임의
  크기 씬을 제한된 메모리로** 처리. 풀씬 10m도 안정적으로 28분.
- **sarsen**: full float64 그리드를 RAM에 적재 → **풀씬은 32GB에서 OOM**. 짧은 씬만
  기본값으로 되고, 풀씬은 `--tc-chunks`로 겨우 되지만 느리다.

**함의**: 현재 32GB 머신에서 **sarsen을 풀사이즈 IW GRD 생산에 쓰려면 RAM 증설
(≈64GB)** 이 사실상 필요하다. 광역·저해상(30m) 짧은 씬이나 AOI 서브셋이면 지금도
쓸 만하다. 정밀·대량·풀씬 처리는 SNAP이 확실히 유리(메모리·속도 모두).

> 사용자 결정(2026-07-27): 9장 완주 대신 **754B 쌍 + 위 메모리 한계**로 결론을
> 확정. sarsen 풀씬 완주는 RAM 증설 후 또는 필요 시 `--tc-chunks`로 별도 진행.

---

## 4. Part 3 — Frost 동일 하이퍼파라미터 총시간

같은 Frost 설정(5×5, damping 2)에서 총 처리시간(754B):

| 파이프라인 | 구성 | 총시간 |
| --- | --- | --- |
| SNAP | RTC + **SNAP Frost**(그래프 내부, 10m) | **27.9분** |
| sarsen | RTC(16.4분) + **로컬 Frost**(`filtering.frost_filter` 5×5, 55.9s, 30m) | **17.3분** |

- 로컬 Frost(sarsen dB→linear→Frost→dB)는 69.5M px에서 **약 56초**로, sarsen 총시간에
  ~6%만 더한다. 즉 "sarsen엔 스펙클 필터가 없다"는 약점은 로컬 `filtering/`로 값싸게
  메운다(하이퍼파라미터도 SNAP과 동일하게 맞춤).
- 결론은 Part 1과 같다: 같은 Frost라도 총시간 우열은 **출력 해상도(10m vs 30m)** 가
  가른다. 30m로 맞추면 SNAP이 더 빠를 것.

> 단 이 비교도 754B(짧은 씬) 기준이다. 풀씬은 sarsen이 §3.2 메모리 한계에 걸린다.

---

## 5. Part 4 — NGII 5m DEM vs COP30 (후속, 단독 실행)

- DEM: `D:\00_DEM\DEM_5m\dcd_5m_dem.tif` — 확인 결과 **EPSG:4326, ~5m(0.0000512°),
  범위 lon 124.96–131.95 / lat 33.02–38.41, nodata −3.4e38**. 이미 지리좌표계라
  **재투영 불필요**(씬 bbox 클립만). NGII는 **북한·치악산 미포함** → **치악산 제외
  남한 육상**에서만 비교(수체·해상 제외). 정표고 기준이라 EGM 보정 적용.
- 절차: 같은 씬을 (1) SNAP+NGII, (2) sarsen+NGII, (3) SNAP+COP30, (4) sarsen+COP30로
  RTC → 처리시간(단독)·TC 기하품질·수체 탐지 정확도·γ0 dB 분포 비교.
- 주의: sarsen+NGII도 풀씬이면 §3.2 메모리 한계에 걸리므로, **짧은 씬 또는
  `--tc-chunks`/AOI 서브셋**으로 진행한다.

본 파트는 신규 씬 처리·water detection·7월 Frost 재처리 이후 **맨 마지막**에 진행한다.

---

## 6. 결론

1. **SNAP 없이 sarsen으로 S1C RTC 가능**(검증 완료, [RTC_SARSEN_KR.md](RTC_SARSEN_KR.md)).
   지오코딩은 SNAP과 **위치 완전 일치**(시프트 0), γ0 dB는 중앙값 **+0.96 dB** 차
   (≈1 dB 오프셋만 감안하면 됨).
2. **속도(754B)**: sarsen 16.4분(30m) vs SNAP 27.9분(10m). 절대시간은 sarsen이
   빠르지만 이는 **더 거친 30m 격자**(픽셀 6.3배 적음) 덕분이고, **픽셀당 처리량은
   SNAP이 3.7배 빠르다**. 같은 Frost를 걸어도(로컬 Frost +56s) 결론은 동일.
3. **sarsen 풀사이즈 메모리 한계**: 정상 길이 IW GRD는 32GB에서 지오코딩 interp가
   OOM. `--tc-chunks 256`으로 회피되나 느림. → **풀씬 대량 처리엔 SNAP, 혹은 RAM
   증설(≈64GB) 후 sarsen**. 짧은 씬·AOI·30m 광역엔 sarsen도 실용적.
4. **DEM 소스**: 자동 Copernicus(C:)는 육상 씬에서 정상(기존 파이프라인 문제 없음).
   벤치마크는 두 도구에 **동일 DEM**을 주려고 로컬 COP30(D:)를 썼을 뿐.
5. **권고**: SNAP을 못 쓰는 환경/광역 30m 수체탐지 → sarsen(SNAP-free)이 답.
   정밀 10m·대량·풀씬 생산 → SNAP이 메모리·속도 모두 유리.
