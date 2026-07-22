# 타일 기반(split-based) Otsu 자동 임계값: 방법론과 레퍼런스

`build_water_per_date_otsu.py`가 쓰는 임계값 결정 방식(궤도별·날짜별 수체
지도)의 이론적 근거를 정리한다. SAR 홍수 탐지에서 널리 쓰이는 **split-based
automatic thresholding** 계열(Martinis 2009, Chini 2017)을 참고했다.

> **출처 접근에 관한 주의**: 아래 정리는 (a) 두 논문의 **초록·서지정보를
> 직접 확인**하고, (b) Chini 그룹의 공개 구현(SBATool) 문서, (c) Otsu(1979)
> 원논문의 공식을 근거로 한다. 다만 논문 **본문 PDF의 세부 수식·파라미터까지
> 원문 그대로 인용하지는 못했다**(오픈액세스 PDF의 텍스트 추출 실패). 따라서
> "Martinis 2009가 정확히 어떤 통계량으로 타일을 선택했는가" 같은 세부는
> 개념 수준으로만 기술하고, 정확한 값은 원논문(4·5절)을 확인할 것을 권한다.
> 우리 구현이 원 논문과 **다른 점**은 4절에 명시한다.

## 1. 배경: 전역(global) Otsu와 그 한계

### 1-1. Otsu(1979) 임계값

Otsu 방법은 회색조 히스토그램을 임계값 `t`로 두 클래스(어두움/밝음)로 나눌 때
**클래스 간 분산(between-class variance)** 을 최대화하는 `t`를 고른다. 이는
클래스 내 분산 최소화와 동치다.

- 각 클래스 확률: `ω₀(t) = Σ_{i≤t} p_i`, `ω₁(t) = 1 − ω₀(t)`
- 각 클래스 평균: `μ₀(t)`, `μ₁(t)`, 전체 평균 `μ_T`
- 클래스 간 분산: `σ_B²(t) = ω₀(t)·ω₁(t)·[μ₀(t) − μ₁(t)]²`
- 최적 임계값: `t* = argmax_t σ_B²(t)`

Otsu는 같은 논문에서 임계값의 "좋음(분리도)"을 재는 정규화 척도도 제안했다:

```text
η(t) = σ_B²(t) / σ_T²        (0 ≤ η ≤ 1, σ_T² = 전체 분산)
```

`η`가 1에 가까울수록 두 봉우리가 뚜렷이 갈린다(이봉성이 강함). 우리는 이
`η`를 **타일이 물+육지 이봉인지 판정하는 척도**로 재활용한다(3절).

### 1-2. 왜 넓은 SAR 장면에서 전역 Otsu가 실패하는가

Otsu는 히스토그램이 이봉(bimodal)이고 두 클래스의 화소 수가 크게 차이 나지
않을 때 잘 동작한다. 그런데 홍수/수체 탐지에서는 **관심 클래스(물)가 장면
전체에서 극소수**다.

이 프로젝트 7/3 GRD 장면의 실측 VV dB 히스토그램:

- **물 봉우리 ≈ −22 dB** (약 4.6×10⁵ 화소/구간)
- **육지 봉우리 ≈ −8 dB** (약 7.6×10⁷ 화소/구간) — 물의 약 150배
- 두 봉우리 사이 **골짜기 ≈ −18 dB**

물:육지 ≈ 1:150이라, `σ_B²`를 최대로 만드는 지점은 물/육지 골짜기가 아니라
**다수인 육지 분포 자체를 반으로 가르는 곳(≈ −8 dB)** 이 된다. 실제로 전역
Otsu를 적용하자 임계값 **−8.3 dB**, 수체 면적 **약 26,000 km²**(장면의 절반)
라는 명백한 오탐이 나왔다. 이것이 split-based 기법이 등장한 이유다.

## 2. Martinis, Twele & Voigt (2009) — Split-Based Approach (SBA)

**Martinis, S., Twele, A., & Voigt, S. (2009).** *Towards operational near
real-time flood detection using a split-based automatic thresholding procedure
on high resolution TerraSAR-X data.* Natural Hazards and Earth System Sciences
(NHESS), 9(2), 303–314. DOI: 10.5194/nhess-9-303-2009 (오픈액세스).

핵심 아이디어

- 완전 **비지도(unsupervised)** — 학습자료·사전 클래스 통계 없이 동작.
- 대형 고해상도 SAR 장면을 **여러 부분(splits/sub-tiles)으로 분할**한다.
- 물이 소수인 전역 히스토그램이 아니라, **부분(타일)들에 내재된 정보를
  분석·결합해 전역 임계값(global threshold)을 유도**한다(초록 원문:
  "derivation of a global threshold by the analysis and combination of the
  split inherent information"). 즉 물/육지가 함께 잡히는 부분에서 임계값을
  뽑아 장면 전체에 쓴다.
- 그 임계값을 **다중 스케일 분할(multi-scale segmentation, 소·중·대 규모
  per-parcel)** 과 결합해 최종 수체를 분류하며, **DEM은 선택적으로 통합**한다.

> 원논문은 부분(타일) 선택에 쓰는 구체적 통계 기준과 사용한 "단순 임계값
> 알고리즘(a simple thresholding algorithm)"의 종류를 본문에서 기술한다.
> 본 문서 작성 시 PDF 본문의 정확한 수식을 추출하지 못했으므로, **세부
> 기준은 원논문 확인을 권장**한다. (이 알고리즘은 이후 Twele et al. 2016에서
> Sentinel-1용으로 이식되었다.)

## 3. Chini, Hostache, Giustarini & Matgen (2017) — Hierarchical SBA (HSBA)

**Chini, M., Hostache, R., Giustarini, L., & Matgen, P. (2017).** *A
Hierarchical Split-Based Approach for Parametric Thresholding of SAR Images:
Flood Inundation as a Test Case.* IEEE Transactions on Geoscience and Remote
Sensing (TGRS), 55(12), 6975–6988. DOI: 10.1109/TGRS.2017.2737664.

SBA를 발전시킨 점

- **계층적(hierarchical) 탐색**: 고정 타일 크기가 아니라 **가변 크기 타일**을
  계층적으로(사실상 쿼드트리처럼 큰 타일 → 하위 분할) 탐색해, **이봉성이
  드러나는 적절한 스케일의 타일을 자동으로 찾는다.** 물의 규모/위치를 모를 때
  타일 크기를 미리 못 정하는 문제를 해결한다.
- **모수적(parametric) 임계값**: 선택된 타일의 히스토그램에 **두 클래스의
  분포함수(두 개의 확률밀도, 실무적으로 가우시안)를 적합**하고, 그 적합된
  분포로부터 임계값을 유도한다("parametric thresholding … requires the
  estimation of two distribution functions"). Chini 그룹의 공개 구현
  **SBATool**은 입력으로 **Z-score 맵**을 받아 **가우시안 초기값
  (setGaussianInitials)** 으로 히스토그램을 적합하며, **GSBA(Growing SBA)**
  와 **HSBA** 두 알고리즘을 제공한다.
- 이후 임계값을 장면 전체에 적용하고 후처리(예: region growing)로 확장한다.

## 4. 우리 구현(`build_water_per_date_otsu.py`)이 채택·단순화한 것

우리는 위 계열의 **핵심 통찰**(= "물이 소수라 전역 임계값이 왜곡되니, 물+육지가
함께 있는 이봉 타일에서만 임계값을 뽑는다")을 따르되, 이 프로젝트 규모/의존성에
맞춰 **가볍게 구현**했다. 원 논문과의 차이를 명시한다.

| 항목 | Martinis 2009 / Chini 2017 | 본 구현 |
| --- | --- | --- |
| 타일 분할 | 고정 분할(SBA) / 가변·계층적(HSBA) | **고정 크기 타일**(기본 1024px ≈ 10km) |
| 타일 선택 | 부분 내재정보 기반 통계 기준 | **Otsu 분리도 η 상위 (100−pctl)%** + 어두운클래스 비율 2~98% |
| 임계값 방식 | 단순 임계값(SBA) / 모수적 2분포 적합(HSBA) | 선택된 타일 히스토그램을 **합산(pool) 후 비모수 Otsu** |
| 후처리 | 다중스케일 분할 / region growing / DEM | 없음(순수 dB 임계값 마스크) |
| 궤도 처리 | — | **절대궤도번호별로 분리**해 패스마다 별도 임계값 |

구현 절차 (요약)

1. `(날짜, 절대궤도)` 그룹마다 프레임을 모자이크한다.
2. 장면을 1024px 타일로 나눈다. 유효화소 25% 미만 타일은 후보에서 제외.
3. 타일마다 Otsu 분리도 `η`와 어두운클래스 비율을 계산한다.
4. `η` **상위 5%(--pctl 95)** 이면서 어두운클래스 비율이 **2~98%**(한쪽으로
   쏠리지 않아 실제 이봉)인 타일만 채택한다.
5. 채택 타일들의 히스토그램을 **합산**해 한 번의 Otsu로 전역 임계값을 낸다.
   이봉 타일 안에선 물:육지 비율이 비슷해 Otsu가 **진짜 물/육지 골짜기**를 찾는다.
6. 이봉 타일이 8개 미만이면(장면이 대부분 육지/물) `--fallback-db`(−16)로
   물러난다.

검증(초기 3그룹): 7/3 o008384 **−14.55 dB**(738 km²), 7/14 o003668 **−12.05 dB**,
7/14 o003675 **−12.15 dB**. 전역 Otsu의 −8 dB 대비 물/육지 골짜기(−12~−15 dB)로
정상 수렴했다.

**한계**: HSBA의 계층적 가변 타일이나 모수적 2분포 적합을 쓰지 않으므로, 물이
매우 국소적이거나 타일 크기(10km)와 물 규모가 안 맞으면 이봉 타일을 못 찾을 수
있다. 그럴 때는 `--tile`을 줄이거나 fallback으로 물러난다. 더 엄밀히 하려면
Chini 2017식 계층 탐색 + 가우시안 적합으로 확장할 수 있다.

## 5. 참고문헌

1. **Otsu, N. (1979).** A Threshold Selection Method from Gray-Level
   Histograms. *IEEE Transactions on Systems, Man, and Cybernetics*, 9(1),
   62–66. DOI: 10.1109/TSMC.1979.4310076.
2. **Martinis, S., Twele, A., & Voigt, S. (2009).** Towards operational near
   real-time flood detection using a split-based automatic thresholding
   procedure on high resolution TerraSAR-X data. *Natural Hazards and Earth
   System Sciences*, 9(2), 303–314. DOI: 10.5194/nhess-9-303-2009.
   <https://nhess.copernicus.org/articles/9/303/2009/>
3. **Chini, M., Hostache, R., Giustarini, L., & Matgen, P. (2017).** A
   Hierarchical Split-Based Approach for Parametric Thresholding of SAR Images:
   Flood Inundation as a Test Case. *IEEE Transactions on Geoscience and Remote
   Sensing*, 55(12), 6975–6988. DOI: 10.1109/TGRS.2017.2737664.
4. **Twele, A., Cao, W., Plank, S., & Martinis, S. (2016).** Sentinel-1-based
   flood mapping: a fully automated processing chain. *International Journal of
   Remote Sensing*, 37(13), 2990–3004. DOI: 10.1080/01431161.2016.1192304.
   (Martinis 2009 SBA의 Sentinel-1 이식 — 서지정보는 재확인 권장.)
5. 구현 참고: Chini 그룹 공개 코드 **SBATool** (GSBA/HSBA),
   <https://github.com/IES-SARLab/SBATool>.

---

관련 문서: [FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md) 8절(적용 결과),
스크립트: `build_water_per_date_otsu.py`.
