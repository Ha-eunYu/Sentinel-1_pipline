# 인계 메모 — 2026-08-26 세션 (8/21~8/26 수집·RTC, 궤도 감사)

다음 세션이 이어받을 것만 적는다. 배경 설명은 링크로 넘긴다.

관련: [ORBIT_TYPE_AUDIT_KR.md](../pipeline/ORBIT_TYPE_AUDIT_KR.md) ·
[BBOX_RANGES_KR.md](../pipeline/BBOX_RANGES_KR.md) ·
[PREPROCESSING_SPEC_KR.md](../pipeline/PREPROCESSING_SPEC_KR.md)

---

## 1. 이 세션에서 끝난 것

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

### 1.2 RTC — 6 장 완료 (VH, Frost, 한반도 DEM)

8/21·8/23·8/24 분 6 장 전량 성공, 유효화소 42~59%.

```bash
conda run -n s1_snappy python -u -m s1.tools.preprocess.batch_grd_rtc_frost \
    --month 202608 --only <씬ID들> --pol VH \
    --out-dir downloads/rtc_grd_frost_vh --out-tag _vh \
    --dem downloads/dem_basin/korea_peninsula_cop30.tif --gpt-c 7G
```

> **DEM 은 `korea_peninsula_cop30.tif` 를 썼다.** 이 6 장은 전부 북한(남한 0.00%)
> 이라 `korea_full_cop30.tif`(북위 39.9° 상한)로는 **빈 산출물**이 나온다(ISSUES #17).
> 8/20 배치가 `korea_full` 을 쓰고 있었으므로 **기존 8월 산출물과 DEM 방식이 다르다**
> — 한 비교쌍에 섞지 말 것(DEM 교체 시 실측 P50 +0.4 dB 이동).

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

---

## 2. 지금 돌고 있는 것 (인계 시점 13:53)

8/25 r134 **7 장 중 6 장이 진행 중**이다.

| 배치 | 대상 | 상태 |
| --- | --- | --- |
| A (PID 252084) | F8B2, 4918, 8C52, 09F1 | **[1/4] F8B2** 처리 중 |
| B (PID 274124) | FB79, CB51, 10EE | **[2/3] CB51** 처리 중 |
| FB79 재처리 | FB79 | **B 종료 대기 중** (자동 이어받기 예약) |

- 로그: `temp/logs/rtc_r134_a.log`, `rtc_r134_b.log`, `rtc_r134_fb79.log`
- 확인: `ls downloads/rtc_grd_frost_vh/ | grep 012300` (7 개가 되면 완료)

> **FB79 는 한 번 실패했다.** `gpt` 4 개가 동시에 `-c 7G` 를 물던 시간대에
> `Native memory allocation (malloc) failed` 로 죽었다. 파이프라인은 정상
> 동작했다 — 부분 산출물을 지우고 다음 씬으로 넘어갔다(ISSUES #24 의 빈 껍데기
> 사고는 없었다). **이 머신(32 GB)에서 동시 `gpt` 는 2 개까지다.**

---

## 3. 다음 세션이 할 것

### 3.1 먼저 확인

```bash
ls downloads/rtc_grd_frost_vh/ | grep -c 012300     # 7 이면 r134 완료
grep "완료\|실패" temp/logs/rtc_r134_*.log
```

7 개가 안 되면 빠진 씬만 `--only` 로 재처리한다.

### 3.2 궤도 정합 — 둘 중 하나를 고른다

1. **2025 년 RESORB 9 장을 POEORB 로 재처리** (6D9F, 38C3, 6CFA, 47FE, 6951,
   F86B, 6EDB, CDCC, 037F) — 2025 년 내부 통일. **지금 가능하다.**
2. **2026-07 분 POEORB 재처리** — 캐시에 S1C 2026/07 8 개·S1D 9 개가 이미 있다.

**2026-08 분은 9 월 중순 이후**에나 POEORB 로 재처리할 수 있다(발행 +20 일).

### 3.3 남은 것

- **모자이크** — `s1.tools.mosaic.rebuild_mosaic_extdem --date <YYYYMMDD>`
  (8/21·8/23·8/24·8/26 분이 아직 안 돌았다)
- **로그없음 59 건** — 궤도 판정이 추론이다. 확정하려면 재처리뿐.

---

## 4. 주의

- **이 저장소는 여러 세션이 동시에 쓴다.** 커밋 전 `git status` 를 다시 보고,
  내가 만들지 않은 변경은 건드리지 않는다. 이 세션 인계 시점에도
  `README_KR.md`·`ISSUES_KR.md`·`PROGRESS_KR.md`·`batch_grd_rtc_frost.py` 가
  다른 세션 손에 열려 있었다.
- **`conda run ... > 파일` 은 Python 출력이 안 보인다.** `-u` 를 줘도 그랬다.
  진행 확인은 프로세스(`Get-Process gpt`)와 산출물 타임스탬프로 한다.
