# 궤도 종류 감사 — 어느 씬이 POEORB 로 처리됐고 어느 씬이 RESORB 인가 (2026-08-26)

`downloads/rtc_grd_frost_vh/` 의 VH RTC 산출물 **125 개 전량**을 대상으로,
SNAP 이 어떤 궤도파일을 썼는지 로그에서 되짚은 기록이다.

관련: [PREPROCESSING_SPEC_KR.md](PREPROCESSING_SPEC_KR.md)(전처리 규격 정본) ·
[BBOX_RANGES_KR.md](BBOX_RANGES_KR.md) · [ISSUES_KR.md](../worklog/ISSUES_KR.md)

전체 표: [orbit_map_202507_202608.csv](orbit_map_202507_202608.csv) (125 행)

---

## 1. 왜 봤나

POEORB(정밀궤도)는 촬영 후 **약 20 일 뒤** 발행된다. 그 전에 처리하면 SNAP 은
경고를 남기고 **RESORB(신속궤도)로 폴백한다** — 오류가 아니라서 그냥 지나간다.
궤도 종류가 다르면 기하 정합이 달라지므로, **DEM 을 섞지 말라는 것과 같은
성격의 교란**이다. 2025 년과 2026 년을 비교하기 전에 무엇이 섞여 있는지부터
확인해야 했다.

## 2. 판별 방법과 근거 등급

산출물 GeoTIFF 에는 궤도 정보가 **남지 않는다**(`gdalinfo` 로 확인 — TIFFTAG
해상도 태그뿐). **로그가 유일한 증거다.**

SNAP `ApplyOrbitFileOp` 의 출력으로 가른다.

| 등급 | 판별 | 개수 |
| --- | --- | ---: |
| **확정 · RESORB** | 블록에 `No valid orbit file found` → 폴백 | 44 중 대부분 |
| **확정 · POEORB** | 블록에 `POEORB/...EOF` 경로가 찍힘(내려받아 사용) | |
| **추정 · POEORB** | 블록이 정상 종료 + 경고 없음 → 캐시의 POEORB 사용 | 18 |
| **로그없음** | 처리 로그를 못 찾음. `~/.snap/auxdata/Orbits/POEORB/` 캐시가 촬영시각을 덮는지로 보조 판정 | 59 |
| **진행중** | 블록이 아직 안 끝나 판정 불가 | 3 |

> ⚠ **로그없음 59 건은 추론이다.** SNAP 은 받은 궤도파일을 지우지 않으므로
> "캐시에 없음 = POEORB 미사용"이 합리적이지만, 캐시를 청소한 적이 있으면
> 틀린다. 확실히 하려면 재처리 외에 방법이 없다.

> ⚠ **진행 중인 씬을 POEORB 로 오분류하지 말 것.** 경고는 그래프 초반에
> 찍히지만, 블록이 안 끝났으면 아직 안 나왔을 수도 있다. 첫 파서가 8/25 분
> CB51·F8B2 를 POEORB 로 잘못 셌다 — 2026/08 POEORB 는 **존재하지 않는다.**

## 3. 결과

| 시기 | 산출물 | POEORB | RESORB | 보류 |
| --- | ---: | ---: | ---: | ---: |
| 2025-07~08 | 30 | **20** | 9 | 1 |
| 2026-06~07 | 55 | 3 | **51** | 1 |
| 2026-08 | 40 | **0** | **38** | 2 |

### 3.1 "2025 년은 전부 정밀궤도" 가 아니다

2025 년분 30 개 중 **9 개가 RESORB** 다.

| 촬영일 | 위성 | 씬 |
| --- | --- | --- |
| 2025-07-18 | S1C | 6D9F, 38C3 |
| 2025-07-24 | S1A | 6CFA |
| 2025-07-25 | S1C | 47FE, 6951, F86B, 6EDB |
| 2025-08-11 | S1C | CDCC, 037F |

### 3.2 같은 날 같은 패스 안에서도 갈린다

- **2025-08-11 r127** — 2B35·9FBB·9F4F 는 POEORB, **CDCC·037F 는 RESORB**
- **2025-07-24** — S1A CC17·A1F0·9711 은 POEORB, **6CFA 만 RESORB**

**한 모자이크 안에 두 궤도가 섞여 있다는 뜻이다.**

### 3.3 2026-08 은 전량 RESORB

캐시의 `POEORB/S1C/2026/08`·`POEORB/S1D/2026/08` 은 **폴더만 있고 파일이 0 개**다
— SNAP 이 받으러 갔다가 발행 전이라 빈손으로 돌아온 흔적이다.

## 4. 비교 작업에 미치는 영향

2025 년 대 2026 년을 비교하면 **POEORB 20 장 대 RESORB 89 장**을 맞대는 구도가
된다. 정합을 맞추려면 두 방향이 있다.

1. **2025 년 RESORB 9 장을 POEORB 로 재처리** — 2025 년 내부를 통일한다.
   해당 시기 POEORB 는 이미 발행돼 있어 **지금 가능하다.**
2. **2026-07 분을 POEORB 로 재처리** — 캐시에 S1C 2026/07 8 개, S1D 9 개가
   이미 있어 상당수가 바로 된다. **2026-08 분은 9 월 중순 이후**에나 가능하다.

## 5. 재현

```bash
# 로그를 훑어 씬 -> 궤도 표를 만든다 (docs/pipeline/orbit_map_*.csv 생성)
# 판별: 블록에 'No valid orbit file found' 가 있으면 RESORB, 없으면 POEORB
grep -c "Using Sentinel Restituted" temp/logs/<로그>.log   # RESORB 폴백 횟수
grep -o "POEORB/S1[A-D]/[0-9/]*/\S*\.EOF" temp/logs/<로그>.log | head

# 캐시에 어느 시기 POEORB 가 들어와 있는지
find ~/.snap/auxdata/Orbits/Sentinel-1/POEORB -type f | wc -l
```
