# SAR Speckle 필터 비교: SNAP 4종 vs `filtering` 폴더 + `qa` 폴더 리뷰

- **작성일**: 2026-07-15
- **대상 영상**: `S1C_IW_GRDH_1SDV_20260713T214005..._1A5A` (7/13 post-event GRD, 남서해안)
- **요청**: ① Multi-look만 / Refined Lee / Lee / Frost RTC를 SNAP으로 처리해 비교,
  ② `S1/filtering` 폴더(자체 구현 필터)와 비교, ③ `S1/qa` 폴더 리뷰.

---

## 0. 한눈에 (TL;DR)

1. **SNAP 필터 4종**: multilook-only(필터 없음) 대비 Refined Lee/Lee/Frost는 speckle
   억제도(ENL)를 **약 2배(5.2 → 10~11)** 로 올린다. 대신 가는 선·경계가 다소 희생된다.
   셋 중 **Frost가 가장 균형이 좋다**(가는 선·경계 보존 모두 상위). Refined Lee는
   speckle은 잘 잡지만 **가는 선 보존이 가장 나쁘다**(42~48%).
2. **SNAP vs `filtering` 폴더**: **윈도우 크기를 맞추면 폴더 구현이 SNAP을 5~9% 이내로
   재현**한다 (Lee 3×3: ENL 10.5=10.5, Frost 3×3: 10.3≈10.1). 즉 폴더의 순수 파이썬
   필터는 SNAP과 사실상 동등한 검증된 재구현이다. **단 하나의 예외가 Refined Lee**로,
   폴더 구현이 SNAP보다 약 2배 더 강하게 평활화한다(원인은 폴더가 **의도적으로
   단순화**한 알고리즘 — 아래 3-B).
3. **가장 큰 손잡이는 필터 종류가 아니라 윈도우 크기**다. 같은 Lee라도 3×3(ENL 10)에서
   7×7(ENL 36)로 키우면 speckle 억제가 3배 이상 강해지는 대신 경계 보존이 65%→45%로
   떨어진다.
4. **`qa` / `filtering` 폴더는 완성도가 매우 높다.** 4축 정량 QA(speckle 억제·가는 선
   보존·경계 보존·수면 분리도), 참조문헌 카탈로그, 블록/halo 동등성 테스트, 과거
   버그 수정 이력까지 코드에 남아 있어 신뢰할 만하다.

---

## 1. 방법론 (어떻게 쟀나)

### 처리한 것

동일한 GRD 씬 하나(1A5A)에 대해 `prepro_grd_gpt.build_grd_rtc_graph`로 **speckle 필터만
바꿔** 4개의 RTC(dB) 산출물을 만들었다 (SNAP `gpt`, `s1_snappy` 환경):

| 산출물 접미사 | 필터 | SNAP 처리시간 |
| --- | --- | --- |
| `_rtc_db_nofilter` | 없음 (multilook-only) | 9.2분 |
| `_rtc_db` | Refined Lee (파이프라인 기본값) | (기존) |
| `_rtc_db_lee` | Lee | 10.3분 |
| `_rtc_db_frost` | Frost | 10.0분 |

- SNAP 그래프에서 필터는 `Calibration → [Subset] → **Speckle-Filter** →
  Terrain-Flattening → Terrain-Correction → LinearToFromdB` 순서로, **지형보정 이전
  (레이더 기하)** 에 적용된다.
- SNAP `Speckle-Filter` 연산자는 `filter`명만 지정하고 나머지는 기본값을 썼다
  (Lee/Frost는 기본 윈도우 **3×3**, Frost damping 2.0, Refined Lee는 고정 **7×7**).
- "multilook-only"라는 표현: GRDH 제품은 이미 멀티룩(공칭 ENL≈4.4)이 끝나 있어 SLC처럼
  별도 Multilook 연산이 없다. 따라서 여기서 "multilook-only"는 **추가 speckle 필터를
  적용하지 않은 RTC**를 뜻한다(비교의 기준선).

### 지표 (`qa.metrics` 사용)

동쪽 육지+수체 혼합부에서 **1000×1000 crop 2곳**(r0=6000/12000, c0=32000)을 잘라,
각 산출물을 dB→linear power로 변환한 뒤 네 축을 측정했다. 마스크(가는 선·강한 경계)는
**미필터 기준으로 한 번만** 만들어 전 필터에 공통 적용했다(공정 비교의 핵심).

| 지표 | 뜻 | 방향 |
| --- | --- | --- |
| **ENL** | Equivalent Number of Looks = 1/median(국소 CV)² — speckle 억제도 | ↑ 클수록 매끈 |
| **소하천 유지** | 필터 후 "어두운 가는 선"의 대비 / 미필터 대비 (%) | ↑ 클수록 선 보존 |
| **경계 보존** | 필터 후 계단형 경계 gradient / 미필터 대비 (%) | ↑ 클수록 경계 선명 |
| **수면 분리도** | Otsu 이분 후 Fisher 분리도 — 임계값 수체추출 난이도 | ↑ 클수록 분리 쉬움 |

> **수면 분리도 주의**: crop에 수체 대비가 충분해야 의미가 있다. crop2는 수체가 적어
> 분리도가 전반적으로 낮게(2.7~2.9) 눌렸다. 그래서 아래에서는 **crop별로 안정적인
> ENL·소하천·경계 3축을 위주로** 해석한다.

---

## 2. Part A — SNAP 필터 4종 비교 (요청 ①)

crop1 / crop2 값 (ENL·소하천·경계·분리도 모두 ↑ 좋음):

| 필터 | ENL | 소하천 유지 | 경계 보존 | 수면 분리도 |
| --- | --- | --- | --- | --- |
| **multilook-only (기준)** | 5.2 / 5.2 | 100% / 100% | 100% / 100% | 2.95 / 2.76 |
| **Refined Lee** (7×7 고정) | 10.8 / 11.1 | 48% / 42% | 62% / 67% | 4.89 / 2.86 |
| **Lee** (3×3) | 10.5 / 10.5 | 62% / 64% | 62% / 65% | 4.26 / 2.78 |
| **Frost** (3×3) | 10.1 / 10.2 | 66% / 67% | 68% / 71% | 4.31 / 2.81 |

**해석**

- **세 필터 모두 ENL을 5.2 → 10~11로 약 2배** 올린다. 즉 균질부 speckle을 뚜렷하게
  줄인다. 세 필터의 **speckle 억제 강도는 서로 비슷하다**(10.1~11.1).
- **가는 선(소하천·수로) 보존**은 Frost(66~67%) ≈ Lee(62~64%) > **Refined Lee(42~48%,
  가장 나쁨)**. Refined Lee가 유독 가는 선을 지우는 경향은 `qa` 모듈이 설계 근거로 든
  현상과 정확히 일치한다 — Refined Lee는 "가장 균질한 서브윈도우"를 고르는데, 가는
  하천 위 픽셀에서는 "하천을 배제한 주변부 서브윈도우"가 가장 균질하다고 판단해
  하천을 배경으로 덮어버린다.
- **경계 보존**은 Frost(68~71%)가 가장 선명, Refined Lee/Lee는 62~67%.
- **주의(공정성)**: SNAP **Refined Lee는 7×7 고정**인 반면 **Lee/Frost는 3×3 기본값**
  이라, 위 표의 Refined Lee 손해에는 "더 큰 윈도우" 효과가 섞여 있다. 윈도우를 맞춘
  순수 알고리즘 비교는 Part B의 폴더 실험에서 본다.

**결론(SNAP 4종)**: 수체(홍수) 매핑처럼 **경계·가는 수로를 살려야** 하는 용도에서는
**Frost가 speckle 억제와 경계·선 보존의 균형이 가장 좋다.** 현재 파이프라인 기본값인
Refined Lee는 speckle은 잘 잡지만 가는 수로를 지우는 부작용이 가장 크므로, 소하천이
중요한 AOI라면 Frost(또는 Lee) 전환을 검토할 만하다.

---

## 3. Part B — SNAP vs `filtering` 폴더 (요청 ②)

`filtering` 폴더의 순수 파이썬(numpy/rasterio) 구현을, **multilool-only 산출물을 linear로
변환한 것에 사후 적용**해 같은 지표로 쟀다.

### 3-A. 윈도우를 맞추면 SNAP과 거의 일치 — 폴더 구현이 검증됨

| 필터 (윈도우 매칭) | ENL | 소하천 유지 | 경계 보존 |
| --- | --- | --- | --- |
| SNAP Lee 3×3 | 10.5 / 10.5 | 62% / 64% | 62% / 65% |
| **filtering.lee 3×3** | 10.5 / 10.2 | 68% / 71% | 65% / 71% |
| SNAP Frost 3×3 | 10.1 / 10.2 | 66% / 67% | 68% / 71% |
| **filtering.frost 3×3 d=2** | 10.3 / 10.0 | 69% / 72% | 63% / 69% |

→ **ENL은 소수점 수준까지 일치**(10.5=10.5, 10.3≈10.1)하고, 소하천·경계 보존도 5~9%p
이내로 맞는다. 폴더의 자체 구현이 SNAP의 Lee/Frost를 **사실상 동등하게 재현**한다는
강한 증거다. 폴더 필터가 소하천·경계를 몇 %p 더 살리는 작은 계통차는, 폴더 필터가
**지형보정 후** 최종 격자에 적용된 반면 SNAP은 지형보정 전에 적용해 리샘플링을 한 번
더 거치기 때문으로 보이나, 크기가 작아 실용적 차이는 미미하다.

> 처음엔 SNAP(ENL~10)과 폴더 필터(ENL 19~37)의 큰 차이를 보고 "적용 단계 차이"를
> 원인으로 의심했으나, **윈도우를 3×3으로 맞추자 차이가 사라졌다.** 즉 초기 차이의
> 진짜 원인은 단계가 아니라 **내가 폴더 필터에 준 윈도우(7×7/5×5)가 SNAP 기본값(3×3)
> 보다 컸기** 때문이었다. (이 검증 과정을 기록으로 남긴다.)

### 3-B. 유일한 실질 차이 — Refined Lee (같은 7×7인데 폴더가 ~2배 더 평활화)

| 필터 (둘 다 7×7) | ENL | 소하천 유지 | 경계 보존 |
| --- | --- | --- | --- |
| SNAP Refined Lee | 10.8 / 11.1 | 48% / 42% | 62% / 67% |
| **filtering.refined_lee 7×7** | 22.7 / 21.5 | 73% / 76% | 51% / 61% |

→ 같은 7×7 Refined Lee인데 **폴더 구현이 speckle을 약 2배 더 억제**한다(ENL 22 vs 11).
이는 버그가 아니라 폴더가 **문서에 명시한 단순화** 때문이다 (`refined_lee.py` docstring):

- 폴더 구현은 후보 서브윈도우가 **5개**(전체 / 상·하·좌·좌우 절반)뿐이고, 그중 **전체
  윈도우**도 후보에 포함한다. 균질한 곳에서는 전체 7×7이 선택돼 49픽셀을 모두 평균 →
  강하게 평활화.
- SNAP Refined Lee는 **8방향 서브윈도우 + 점 표적(코너 리플렉터) 보존 분류**를 하고
  전체 윈도우를 후보로 두지 않아 더 보수적으로 평활화 → ENL이 낮음.
- 대각선 방향 경계와 점 표적 근처에서는 SNAP 쪽이 유리할 수 있다.

즉 **"Refined Lee"라는 같은 이름이지만 두 구현의 강도가 다르다.** 폴더의 refined_lee를
쓸 거라면 이 점(더 세게 평활화, 가는 선은 오히려 더 살림)을 알고 써야 한다.

### 3-C. 윈도우 크기가 필터 종류보다 지배적

| filtering.lee | ENL | 소하천 유지 | 경계 보존 |
| --- | --- | --- | --- |
| 3×3 | 10.5 / 10.2 | 68% / 71% | 65% / 71% |
| 7×7 | 36.8 / 35.0 | 73% / 76% | 45% / 51% |

→ 같은 Lee라도 윈도우를 3×3→7×7로 키우면 **speckle 억제가 3배 이상**(ENL 10→36)
강해지지만 **경계 보존은 65%→45%로 급락**한다. **필터 종류 선택보다 윈도우 크기 선택이
결과에 더 큰 영향**을 준다. SNAP 기본 3×3은 보수적(약한 평활화) 설정이다.

---

## 4. Part C — `qa` 폴더 리뷰 (요청 ③)

### 구성

| 파일 | 역할 |
| --- | --- |
| `metrics.py` | 4축 지표 계산 (ENL, 소하천 유지, 경계 보존, Otsu/Fisher 분리도) |
| `compare.py` | 통제 비교 실행기 (`compare_filters`) + 표/마크다운 출력 |
| `visualize.py` | 필터별 결과 비교 패널 PNG 생성 (Pillow, 선택) |
| `__main__.py` | `python -m qa <linear.tif> --enl ... --filters ...` CLI |

### 강점 (그대로 유지 권장)

- **"speckle 억제만 보면 안 된다"는 문제의식이 코드로 구현됨.** ENL 하나가 아니라
  **가는 선 보존을 독립 축으로** 잰다. 실제로 이번 데이터에서 SNAP Refined Lee의
  "speckle은 잘 잡지만 가는 선을 지운다"가 이 지표로 정확히 드러났다(ENL 10.8인데
  소하천 유지 48%). 이 모듈의 설계 근거가 실측으로 검증된 셈이다.
- **공정 비교 원칙이 코드에 강제됨**: 평가 마스크(가는 선·경계 후보)를 **미필터에서
  한 번만** 만들어 전 필터에 공통 적용한다(`compare_filters`). "필터마다 다른 마스크로
  재면 무의미하다"는 주석과 함께.
- **소하천 검출 전 presmooth(3×3)**: speckle이 심한 원본에서 곧바로 "가장 어두운 선"을
  고르면 실제 하천이 아니라 speckle로 우연히 어두워진 픽셀이 섞인다는 점을 인지하고
  약한 사전 평활화로 보정한다(검출 정확도 23%→안정, 주석에 근거 기록).
- **scipy 비의존**: Otsu·Fisher·감마분위수까지 numpy만으로 구현(이식성 좋음).

### 유의점

- **입력은 반드시 linear power**여야 한다(dB·DN 아님). speckle 통계 모델이 linear에서만
  성립하기 때문. 우리 파이프라인 산출물은 dB(`_rtc_db.tif`)라, QA에 쓰려면 이번처럼
  **dB→linear 변환**을 먼저 해야 한다(이 보고서 스크립트가 그 변환을 포함).
- **원본이 RCM/KOMPSAT-5 프로젝트에서 이식됨**: docstring·CLI 예시에 `05_KOMPSAT5`,
  `rcm_preprocess`, K-factor(`σ0=K·DN²`) 등 이 저장소에 없는 참조가 남아 있다. 동작에는
  문제없으나, S1 파이프라인 문서로는 예시 경로를 S1 기준으로 갱신하면 좋겠다.
- **수면 분리도는 crop 의존적**(수체 대비 필요). 자동 QA에서 이 축만 보고 필터를 고르면
  crop 선택에 휘둘릴 수 있다 — ENL·선·경계와 함께 봐야 한다(이번에도 crop2에서 확인).
- `metrics._windows`는 nodata를 edge 복제로 단순 패딩한다(정밀 nodata 처리 아님). QA
  요약용이라 문제는 없지만, nodata 경계가 crop에 많이 걸리면 지표가 약간 왜곡될 수 있어
  crop은 유효율 높은 내부로 잡는 게 좋다(이번엔 유효율 99.9~100%).

---

## 5. Part D — `filtering` 폴더 리뷰 (참고)

`qa`와 짝을 이루는 필터 구현 패키지. 6종 필터(lee/refined_lee/gamma_map/frost/lee_sigma/
median) + 공통 인프라 + SNAP 필터 참조문헌 카탈로그로 구성.

### 강점

- **공통 인프라 분리가 깔끔**: 적분영상 이동통계(`base.integral_image`), Lee MMSE 가중치
  (`apply_lee_weight`), 블록/halo GeoTIFF I/O(`run_speckle_filter`)를 공유하고, 각 필터는
  "지역 통계 계산법"만 다르게 구현. 새 필터 추가가 쉽다.
- **블록 처리 = 전체 로드 동등성**을 테스트로 보장(주석에 명시). 초대형 씬도 메모리
  안전하게 처리(STRIP_ROWS halo 모델).
- **참조문헌 카탈로그(`references.py`)**: SNAP의 모든 speckle 필터(Mean/Median/Frost/
  Gamma Map/Lee/Refined Lee/Lee Sigma/IDAN/MuLoG)를 원 논문과 함께 정리. 근거 추적이 됨.
- **과거 버그 수정 이력이 코드에 남음**: 예) `apply_lee_weight`의 2026-07-13 리뷰(R-01) —
  이전에 가중치 공식이 틀려 균질부에서 speckle 25%가 잔존하던 것을 Lee(1980) 원식으로
  수정. `gamma_map`의 R-2 — 점 표적 보존 분기 누락 수정. 검증 문화가 좋다.

### 유의점

- **linear power 입력 전제**(dB 적용 시 speckle 모델 붕괴 — docstring에 명시).
- **`refined_lee`는 단순화 구현**임을 반드시 인지(3-B): 5후보·전체윈도우 포함·대각선/점
  표적 분류 없음 → SNAP보다 강하게 평활화. "SNAP Refined Lee와 동일"하다고 오해 금물.
- **기본 ENL=4.0** 이지만 S1 GRDH 공칭은 **≈4.4**. 소소하지만 S1에 쓸 땐 4.4 권장
  (이번 비교는 4.4로 통일).
- `frost`/`lee_sigma`/`median`은 적분영상으로 안 되는 이동윈도우라 상대적으로 느림
  (열-블록 sliding window). 대형 씬 전면 적용 시 시간 고려.

---

## 6. 종합 권고

1. **SNAP 파이프라인 필터**: 홍수/수체 매핑에서 가는 수로 보존이 중요하면 현재 기본값
   **Refined Lee → Frost 전환 검토**(speckle 억제 동등, 가는 선·경계 보존 우수).
2. **필터 파라미터**: speckle을 더 세게 잡고 싶으면 필터 종류보다 **윈도우를 키우는 것
   (3×3→5×5→7×7)** 이 직접적이다. 단 경계·선 보존과 트레이드오프.
3. **`filtering` 폴더**는 SNAP을 잘 재현한 검증된 순수 파이썬 구현이라, SNAP 없이(예:
   다른 PC, 배치 후처리) 필터가 필요할 때 신뢰하고 쓸 수 있다. **단 refined_lee만은
   SNAP과 강도가 다름**을 유의.
4. **`qa` 폴더**는 필터 선택의 정량적 근거 도구로 완성도가 높다. 파이프라인에 정식
   편입해, 새 AOI·새 필터를 도입할 때 `python -m qa`로 근거를 남기는 워크플로를 권장.
   (입력을 linear로 변환하는 헬퍼만 S1 파이프라인에 추가하면 됨.)

---

## 7. SNAP 충실 재현 Refined Lee 추가 (`filtering/refined_lee_snap.py`, 2026-07-23)

3-B에서 확인된 "`filtering.refined_lee`(단순화판)가 SNAP Refined Lee와 강도가
다르다"는 문제 때문에, **SNAP `RefinedLee.java`를 그대로 numpy로 옮긴 충실
재현판**을 새 모듈로 추가했다. SNAP 없이(다른 PC·배치 후처리) SNAP과 (거의)
같은 Refined Lee 결과가 필요할 때 쓴다.

**단순화판과의 차이 (SNAP 원본 대조로 구현)**

| 항목 | refined_lee (단순화) | refined_lee_snap (SNAP 충실) |
| --- | --- | --- |
| 후보 방향 | 상·하·좌·우·전체 5개 | **8방향 edge-aligned**(대각선 포함), 전체윈도우 미포함 |
| 윈도우 | 임의 홀수(기본 7) | **7×7 고정**(SNAP 사양) |
| 잡음분산 sigmaV | 고정 `1/ENL` | **데이터에서 국소 추정**(9개 서브영역 정규화분산 중 최소 5개 평균), ENL 미사용 |
| 서브영역 판정 | 분산 최소 후보 선택 | 3×3 서브평균 gradient로 8방향 중 선택 (SNAP `getDirection`) |

**검증(합성 speckle, 단일룩 ENL≈1)**: 균질부 ENL 0.98→**9.28**(평활화 정상),
경계 계단 0.944→**0.924**(97.9% 보존), NaN 누수 0. 특히 **가는 선 대비가
0.998→0.36으로 크게 줄어**, 2절에서 관찰된 **"SNAP Refined Lee가 가는 선을
가장 많이 지운다"**는 특성을 재현한다(같은 입력에서 단순화판은 0.68로 선을
더 남김). 즉 단순화판보다 SNAP 거동에 부합한다.

**사용법**

```python
from filtering import refined_lee_snap_filter, apply_speckle_filter
refined_lee_snap_filter("scene_linear.tif", "scene_rl.tif")            # 직접 호출(7×7 고정)
apply_speckle_filter("scene_linear.tif", "scene_rl.tif",
                     method="refined_lee_snap")                        # 디스패처 경유
```

**주의**: 입력은 반드시 **linear power**(dB 아님). **ENL 인자를 받지 않는다**
(sigmaV를 국소 추정). SNAP과 미세하게 다를 수 있는 점(nodata 처리, 표본분산
분모 (k−1) 가정, sigmaV 정렬 off-by-one, varY==0 시 지역평균 반환)은
`refined_lee_snap.py` docstring에 명시했다.

---

### 부록 — 산출물 위치

- SNAP 필터별 RTC: `downloads/rtc_grd/S1C_..._1A5A_COG_rtc_db{,_lee,_frost,_nofilter}.tif`
- 비교 crop: 동쪽 육지+수체 혼합부 (col 32000, row 6000 / 12000, 1000×1000)
- 비교 스크립트: 세션 스크래치패드 `filter_qa_compare.py` (dB→linear 변환 + `qa.metrics`
  + `filtering.make_filter_fn` 호출). 정식 편입 시 저장소로 옮길 수 있음.
