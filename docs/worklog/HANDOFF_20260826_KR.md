# 인계 메모 — 2026-08-26~09-10 (8월 수집·RTC, 궤도 감사, POEORB 재처리, NAS 이관)

다음 세션이 이어받을 것만 적는다. 배경 설명은 링크로 넘긴다.

관련: [ORBIT_TYPE_AUDIT_KR.md](../pipeline/ORBIT_TYPE_AUDIT_KR.md) ·
[BBOX_RANGES_KR.md](../pipeline/BBOX_RANGES_KR.md) ·
[PREPROCESSING_SPEC_KR.md](../pipeline/PREPROCESSING_SPEC_KR.md)

**2026-09-10 현재 실행 중인 작업 없음.** 8/27 오전 이후 재처리는 멈춰 있다
(17/30). 3 절의 명령으로 재개한다.

**`downloads/rtc_grd_frost_vh/` 는 비어 있다** — 130 장(262 GB)을 NAS 로 옮기고
로컬에서 지웠다. 6 절 참조.

---

## 1. 끝난 것

### 1.1 수집 — GRD 13 장

| 촬영(UTC) | 장수 | 궤도 | 비고 |
| --- | ---: | --- | --- |
| 08-21 09:16 | 1 | S1D r156 | 북한 |
| 08-23 21:46~21:47 | 3 | S1C r105 | 북한 |
| 08-24 09:39~09:40 | 2 | S1D r25 | 북한 |
| 08-25 21:29~21:32 | 7 | S1C r134 | **북한 3 + 남한 4** |

- 도구: `download_scenes.py`, 검색 bbox **`123.0,32.5,131.5,43.5`**(한반도 전체 정본)
- 08-25 r134 는 KST 08-26 06:29~06:32 촬영. **8/21 이후 처음으로 남한을 제대로 찍은 패스**다
  (4918 이 한반도 87.9% / 남한 88.1% 로 중심).

### 1.2 RTC — 2026-08 분 13 장 전량 완료 (VH, Frost, 한반도 DEM)

`downloads/rtc_grd_frost_vh/` · 유효화소 42~70%.

```bash
conda run -n s1_snappy python -u -m s1.tools.preprocess.batch_grd_rtc_frost \
    --month 202608 --only <씬ID들> --pol VH \
    --out-dir downloads/rtc_grd_frost_vh --out-tag _vh \
    --dem downloads/dem_basin/korea_peninsula_cop30.tif --gpt-c 7G
```

> **DEM 은 `korea_peninsula_cop30.tif` 를 썼다.** 8/21~8/24 분 6 장은 전부 북한
> (남한 0.00%)이라 `korea_full_cop30.tif`(북위 39.9° 상한)로는 **빈 산출물**이
> 나온다(ISSUES #17). 8/20 배치가 `korea_full` 을 쓰고 있었으므로 **기존 8월
> 산출물과 DEM 방식이 다르다** — 한 비교쌍에 섞지 말 것(실측 P50 +0.4 dB 이동).

### 1.3 footprint 감사 — 8월 "누락" 은 누락이 아니었다

| 씬 | 한반도 교집합 | 판정 |
| --- | ---: | --- |
| 08-08 B5F3 (r54) | 0.00% | 스침 |
| 08-13 8B48 (r134) | 0.39% | 1% 미만 |
| 08-20 B2F4 (r54) | 0.00% | 스침 |

`download_scenes.py` 가 `min_overlap_pct=0` 으로 호출돼 **교집합이 0 보다 크기만
하면 통과**시키기 때문에 목록에 떴다. 받을 필요 없다.

**한반도를 아예 안 찍은 날:** 08-04, 08-15, 08-16, 08-17 (bbox 통과분 전부 0.00%).
8/15·8/17 이 감시 로그에 "신규"로 올라와 있는데, 그 시점 로그는 한반도 % 를
계산하지 않던 옛 형식이라 중국/일본 프레임이 그대로 올라온 것이다.

### 1.4 궤도 감사

[ORBIT_TYPE_AUDIT_KR.md](../pipeline/ORBIT_TYPE_AUDIT_KR.md) 로 분리. 요약만:
**2025-07~08 은 POEORB 20 / RESORB 9**(전부 정밀궤도가 아니다),
**2026 년은 사실상 전량 RESORB**.

### 1.5 2025-07/08 미처리 49 장 footprint 실측 — 제외 0 장

`classify_region`(KML 실측, STAC 공칭 아님)으로 전수 측정했다.

| 구분 | 장수 |
| --- | ---: |
| 7월 | 5 |
| 8월 | 44 |
| **1% 미만 제외** | **0** |

최저가 2.52%(0812 5D2C)라 **걸러낼 것이 없었다.** 2~9% 대가 다섯 장 있다
(5D2C 2.52 · 669C 5.27 · 7820 5.52 · 69C4 8.42 · D0BD 8.43) — 처리는 되지만
모자이크 기여는 작다.

측정 로그: `temp/logs/fp48.log`

---

## 2. POEORB 재처리 — 30 장 중 17 장 완료

2025-07/08 의 궤도·DEM 을 통일하는 작업. **기존 폴더는 손대지 않았다** —
새 폴더 `downloads/rtc_grd_frost_vh_poeorb/` 에 쌓는다(비교·롤백 가능,
`rtc_grd` → `rtc_grd_frost` 때 쓴 것과 같은 방법).

규격: **POEORB · `korea_peninsula_cop30.tif` · VH · Frost**

| 배치 | 대상 | 완료 | 남음 |
| --- | --- | ---: | ---: |
| A | RESORB 9 + 판정불가 1 + 추정 3 (13 장) | 9 | 4 |
| B | 추정 12 장 | 8 | 4 |
| C | 확정 POEORB 5 장(DEM 불일치) | 0 | 5 |
| **계** | **30** | **17** | **13** |

유효화소 55~72% 로 완료분 전량 정상이다.

> **C 배치가 왜 필요한가.** "확정 POEORB 5 장은 복사만 하면 된다"고 판단했다가
> 틀렸다. DEM 출처를 확인하니 **세 갈래**였다 —
> C942·FF05·AAB6 은 **DEM 지정 없음(SNAP 자동캐시 COP30)**,
> C40B·9A11 은 **`korea_full_cop30.tif`**. 복사하면 새 폴더가 DEM 3 종 혼합이
> 된다. 게다가 자동캐시 DEM 은 하구 수역을 무효로 해석해 결측을 만든다
> (영산강 제약면적 20.2% 손실). **5 장도 재처리해야 30 장이 통일된다.**

---

## 3. 저녁에 재개하는 방법

완료분은 `run_batch` 가 자동으로 건너뛴다. **같은 명령을 그대로 다시 돌리면 된다.**

```bash
# 1) POEORB 잔여 13장 — A·B 를 병렬로, C 는 그 다음에
conda run -n s1_snappy python -u -m s1.tools.preprocess.batch_grd_rtc_frost \
    --month 2025 --only 6D9F,38C3,6CFA,47FE,6951,F86B,6EDB,CDCC,037F,6B3C,EDCA,5AE2,5D79 \
    --pol VH --out-dir downloads/rtc_grd_frost_vh_poeorb --out-tag _vh \
    --dem downloads/dem_basin/korea_peninsula_cop30.tif --gpt-c 7G

# B: --only 0ABD,CC17,A1F0,9711,625F,4458,D0A4,E160,3EEB,2B35,9FBB,9F4F
# C: --only C942,FF05,AAB6,C40B,9A11

# 2) 7월 미처리 5장 (같은 규격, 같은 폴더)
#    --only 9F06,6512,D7EE,B855,2190

# 3) 8월 미처리 44장
#    3031,EFFE,4579,9072,EA9E,B5B4,4B66,C7F8,FEEA,FAA4,65BD,D0BD,839C,0E5A,85B9,
#    FD96,D77C,C236,DDC1,5D2C,CFF4,7D4B,8F3F,4645,646A,669C,7820,71A0,69C4,E814,
#    A5C9,0BE1,E8FF,09F6,3891,0225,96A6,98BB,6956,2AEC,2F13,4A51,C857
```

소요는 씬당 약 2 시간, 2 병렬 기준 — 잔여 13 장 ≈ 13 시간, 7월 5 장 ≈ 5 시간,
8월 44 장 ≈ 44 시간.

---

## 4. 반드시 지킬 것

### 4.1 동시 `gpt` 는 2 개까지

32 GB 머신에서 `-c 7G` 짜리 `gpt` 를 **4 개** 돌렸더니
`Native memory allocation (malloc) failed` 로 FB79 가 죽었다. 파이프라인은
정상 동작했다(부분 산출물을 지우고 다음 씬으로 넘어갔다). 다른 세션이 배치를
돌리고 있는지 **시작 전에 확인할 것.**

```bash
powershell -NoProfile -Command "@(Get-Process gpt -ErrorAction SilentlyContinue).Count"
```

### 4.2 `669C` 는 두 장이다

```text
20250821 21:47  S1C  669C  한반도 19.83%  남한 0.00%   (북한)
20250823 21:32  S1C  669C  한반도  5.27%  남한 5.26%   (남한)
```

`--only` 는 4 자리 ID 로 매칭하므로 **`669C` 를 주면 두 장이 함께 걸린다.**
8월 44 장을 배치로 쪼갤 때 `669C` 는 한쪽에만 넣고, 그 배치의 장수를 실제
매칭 수로 셀 것.

### 4.3 배치를 강제 종료하면 임시폴더가 남는다 — 대시보드가 오판한다

러너는 `finally` 에서 `%LOCALAPPDATA%\Temp\frostrtc_*` 를 지우는데,
`Stop-Process -Force` 로 죽이면 **그 코드에 도달하지 못한다.**
대시보드는 로그 줄이 아니라 **이 폴더의 존재로 '처리중'을 판정**하므로,
폴더가 남으면 끝난 씬이 영원히 처리중으로 보인다. **강제 종료했으면 반드시
폴더를 지울 것.**

```bash
ls -d /c/Users/chlwn/AppData/Local/Temp/frostrtc_*   # 배치가 0개일 때 남은 건 전부 stale
```

### 4.4 부모를 죽여도 `gpt` 자식은 안 죽는다 — 0 바이트 산출물이 남는다

이번에 실제로 겪었다. `gpt` 종료 후 **90 초** 유예를 주고 러너를 죽였는데,
러너가 다음 씬 zip 복사를 **51 초** 만에 끝내고 `gpt` 를 새로 띄운 뒤였다.
부모만 죽어 `gpt` 가 고아로 남았고, **0 바이트 tif** 가 만들어졌다.
그대로 뒀다면 다음 실행이 "이미 처리됨"으로 건너뛰어 **6D9F 가 영구히
빠졌을 것**이다(ISSUES #24 가 기록한 사고).

**유예는 15 초가 적당하다.** 유효화소 검사가 끊길 수 있지만, 그 검사는 하한
미달일 때만 파일을 지우므로 산출물은 안전하다. 검사 결과는 나중에 따로 잰다.

```bash
# 강제 종료 후 산출물 검증 (s1.core.rtc_qc.measure)
conda run -n s1_snappy python -c "
from pathlib import Path; from s1.core.rtc_qc import measure, VALID_FLOOR
st = measure(Path('<tif 경로>')); print(st.summary(), st.valid_frac >= VALID_FLOOR)"
```

### 4.5 로그의 `처리 시작` 만 보고 상태를 판단하지 말 것

강제 종료하면 `[n/m] 처리 시작` 뒤에 `완료`/`실패` 가 안 찍혀 **아직 도는 것처럼
보인다.** 실제 상태는 프로세스로 봐야 한다(4.1 의 명령).

### 4.6 이 저장소는 여러 세션이 동시에 쓴다

커밋 전 `git status` 를 다시 보고, 내가 만들지 않은 변경은 건드리지 않는다.
2026-08-26 인계 시점에 `README_KR.md`·`ISSUES_KR.md`·`PROGRESS_KR.md`·
`batch_grd_rtc_frost.py` 가 다른 세션 손에 열려 있었다(이후 커밋됨).

### 4.7 `conda run ... > 파일` 은 Python 출력이 안 보인다

`-u` 를 줘도 그랬다. 진행 확인은 프로세스와 산출물 타임스탬프로 한다.

---

### 4.8 PowerShell 은 변수명 대소문자를 구분하지 않는다

NAS 대조 스크립트에서 `$N`(해시테이블)을 루프 안의 `$n`(개수)이 덮어썼다.
`ContainsKey` 가 정수에서 호출돼 오류가 났는데, 누락 목록이 **빈 배열로 남아
"누락 0 건"으로 보였다.** 검사가 통과한 게 아니라 아예 수행되지 않은 것이다.
**262 GB 를 지우기 직전이었다.** 비교용 변수는 `$locMap`/`$nasMap` 처럼
서로 확실히 다른 이름을 쓸 것.

---

## 5. 남은 것

- **모자이크 VRT 92 개 재작성** — `downloads/water_otsu/vrt_vh/` 가
  `rtc_grd_frost_vh/` 를 경로로 참조하는데 **그 폴더를 비웠다.** 지금 전부 깨져
  있다. 연도별로 2025-07 32 · 2025-08 6 · 2026-07 37 · 2026-08 17 개다.
  어차피 POEORB 재처리 후 경로가 바뀌므로 그때 다시 만든다.
- **궤도 판정 로그없음 59 건** — 추론이다. 확정하려면 재처리뿐
  ([ORBIT_TYPE_AUDIT_KR.md](../pipeline/ORBIT_TYPE_AUDIT_KR.md) 2 절)
- **2026-07/08 분 POEORB 재처리 100 장** — **2026-09-10 부로 가능해졌다.**
  POEORB 는 발행 +20 일이라 8/21 이전 촬영분은 이미 나왔고 8/24·8/25 분도
  곧 나온다. 이걸 끝내야 2025·2026 이 같은 규격이 된다.

---

## 6. 저장소 정리 (2026-09-09~10)

F 가 **2.9 GB** 까지 차서 정리했다.

### 6.1 한 것

| 대상 | 용량 | 조치 |
| --- | ---: | --- |
| `rtc_grd_frost_vh/` 130 장 | **262 GB** | NAS 이관 후 로컬 삭제 |
| NAS 기존 자료 3 개 | 3.8 GB | 형제 폴더로 분리 |

- **NAS 경로** — `X:\02_Analysis\Sentinel-1_Drought\` (SMB).
  같은 곳을 SSH 로는 `root@192.168.0.184:/Ubuntu/02_Analysis/Sentinel-1_Drought/`
  로 접근한다(포트 923). X 드라이브로 진행 상황을 볼 수 있다.
- **F 여유: 2.9 GB → 264.9 GB**

원래 그 폴더에 있던 2021~2023 년 자료 3 개(`_Orb_Cal_Spk_dB_TC` 규격)는
`X:\02_Analysis\Sentinel-1_Drought_2021-2023\` 으로 옮겼다. **하위 폴더가 아니라
형제 폴더로 만든 이유**는 6.3 을 볼 것.

### 6.2 GTC·VV 정리 상태

| 대상 | 상태 |
| --- | --- |
| `gtc/`·GTC 파일 | **없음**(이전 세션에서 삭제, 136 GB 확보) |
| `rtc_grd/`(Refined Lee)·`rtc_grd_frost/`(VV) | **없음** |
| **`downloads/etc/` VV 14 개** | **남아 있음 · 14 GB** |

`downloads/etc/` 는 전부 VV(`_rtc_db.tif`, `_vh` 없음)이고 2026-07-03~20 촬영분이다.
VH 로 대체돼 이 파이프라인에서 쓰지 않는다(GEE 수체탐지가 VH 를 쓰고 실측 오프셋
약 6 dB). **NAS 백업 후 삭제 예정 — 아직 NAS 에 안 올라갔다.**

`downloads/_archive/rtc_grd_vv_meta/` 의 VV 모자이크 VRT 20 여 개는 4.9 MB 라
당시 기록으로 남겨둔다.

### 6.3 NAS 로 rsync 할 때

```bash
rsync -av --partial --progress -e "ssh -p 923" \
  /mnt/f/06_SAR_system/S1/downloads/<폴더>/ \
  root@192.168.0.184:/Ubuntu/02_Analysis/<대상>/
```

> ### ⚠ `--delete` 를 붙이지 말 것
>
> 로컬을 비운 뒤 `--delete` 로 다시 돌리면 **원본에 없는 것을 대상에서 지운다** —
> 방금 올린 것이 통째로 사라진다. NAS 안에 만든 하위 폴더도 같은 이유로 지워진다.
> 그래서 기존 자료를 하위가 아니라 **형제 폴더**로 뺐다.
>
> ### ⚠ `--partial` 을 붙일 것
>
> 9/9 전송이 S1D 구간에서 끊겼는데, `--partial` 이 없어 진행 중이던 파일을 통째로
> 버렸다. 파일명 순서(S1A → S1C → S1D)로 보내므로 **S1D 27 개가 통째로 누락**됐다.
> 파일 수만 보면 103/130 이라 눈치채기 쉽지만, 위성별로 갈라 보지 않으면
> "거의 다 갔다"고 오판하기 쉽다.

### 6.4 지우기 전 대조는 파일별 크기까지

파일 수와 총용량만 맞춰서는 부족하다. **이름별로 크기를 대조**하고, 위성별
개수도 따로 센다.

```powershell
$locMap = @{}; Get-ChildItem $localDir -File | ForEach-Object { $locMap[$_.Name] = $_.Length }
$nasMap = @{}; Get-ChildItem $nasDir  -File | ForEach-Object { $nasMap[$_.Name] = $_.Length }
@($locMap.Keys | Where-Object { -not $nasMap.ContainsKey($_) })                      # 누락
@($locMap.Keys | Where-Object { $nasMap.ContainsKey($_) -and $nasMap[$_] -ne $locMap[$_] })  # 크기 불일치
```

변수명은 4.8 의 함정을 피해서 지을 것.

### 6.5 F 드라이브 큰 폴더 (2026-09-09 실측, 3726 GB 중)

| 폴더 | GB |
| --- | ---: |
| `06_SAR_system` | 1505 |
| ├ `COP30_MGRS` | 520 |
| ├ `S2` | 519 |
| ├ **`S1`** | **379** |
| ├ `SAR_SYSTEM_LOCAL_ONLY` | 58 |
| └ `gee` | 29 |
| `microsat` | 789 |
| `OneDrive` | 721 |
| `02_Jeddah` | 372 |
| `14_Nepal_flood` | 122 |

**S1 은 셋 중 가장 작다.** `COP30_MGRS`(520 GB)는 S1 파이프라인이 참조하지 않는다
— `downloads/dem_basin/` 의 통합 GeoTIFF(4.2 GB)를 쓴다. 다른 작업 자료일 수 있어
손대지 않았다.

원본 zip 은 F 에 없다 — `sentinel1_grd` → E, `sentinel1` → D 심볼릭 링크다.
