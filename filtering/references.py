"""
SNAP(ESA)의 speckle 필터 목록과 각 필터의 참조문헌 카탈로그.

목적
----
1. SNAP이 제공하는 모든 speckle 필터가 무엇인지, 어떤 논문에 근거하는지를
   한곳에 정리한다 (이 저장소는 아직 lee/refined_lee만 구현했지만, 나머지
   필터를 추가할 때 근거 논문을 여기서 바로 참고할 수 있도록).
2. 인용을 코드와 함께 버전 관리해, "무엇을 어디서 확인했는지"를 남긴다.

출처 (2026-07-13 확인)
--------------------
아래 인용의 상당수는 이 저장소에 포함된 SNAP 소스/도움말에서 그대로 옮겼다:
- 단일편파 필터 목록:
  ESA_SNAP_Microwave_toolbox/.../filtering/SpeckleFilterOp.java 의 valueSet
- 단일편파 참조문헌:
  .../sar/docs/operators/SpeckleFilterOp.html 의 Reference 절
- 편파(polarimetric) 필터 참조문헌:
  .../polarimetric/docs/operators/PolarimetricSpeckleFilterOp.html 의 Reference 절
SNAP 도움말이 명시하지 않은 원 논문(Lee 1980, Kuan 1985/1987, Gamma MAP의
Lopes 1990 IGARSS 등)은 웹 검색으로 보완했다.

주의
----
`implemented` 필드는 "이 rcm_preprocess 패키지에 구현되어 있는가"를 뜻한다
(SNAP 구현 여부가 아니다). 현재 lee/refined_lee만 True다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilterReference:
    """speckle 필터 하나에 대한 메타데이터 + 참조문헌."""

    key: str                    # 이 패키지에서 쓰는 식별자(있으면), 없으면 SNAP 이름 소문자
    snap_name: str              # SNAP UI에 표시되는 이름
    implemented: bool           # rcm_preprocess에 구현되어 있는지
    summary: str                # 한 줄 설명
    references: list[str] = field(default_factory=list)


# SNAP "Speckle-Filter" (단일편파) 연산자가 제공하는 필터들 + 대표적인 편파 전용 필터.
SNAP_SPECKLE_FILTERS: tuple[FilterReference, ...] = (
    FilterReference(
        key="mean",
        snap_name="Mean / Boxcar",
        implemented=False,
        summary="윈도우 내 단순 평균. 적응형 아님 — 경계까지 균일하게 흐린다.",
        references=[
            "표준 이동평균(비적응형)으로 특정 원 논문 없음. "
            "SNAP은 성능 비교 근거로 Mansourpour M., Rajabi M.A., Blais J.A.R., "
            "\"Effects and Performance of Speckle Noise Reduction Filters on Active "
            "Radar and SAR Images,\" (2006)을 든다.",
        ],
    ),
    FilterReference(
        key="median",
        snap_name="Median",
        implemented=True,
        summary="윈도우 내 중앙값. outlier(강한 점 표적)에 강건하지만 비적응형.",
        references=[
            "순서통계(order-statistic) 표준 필터로 특정 원 논문 없음. "
            "SNAP 평가 근거는 Mansourpour et al. (2006)."
        ],
    ),
    FilterReference(
        key="frost",
        snap_name="Frost",
        implemented=True,
        summary="지역 변동계수로 폭이 조절되는 지수 가중 커널(convolution) 필터.",
        references=[
            "V. S. Frost, J. A. Stiles, K. S. Shanmugan, J. C. Holtzman, "
            "\"A Model for Radar Images and Its Application to Adaptive Digital "
            "Filtering of Multiplicative Noise,\" IEEE Transactions on Pattern "
            "Analysis and Machine Intelligence, PAMI-4(2):157-166, 1982.",
        ],
    ),
    FilterReference(
        key="gamma_map",
        snap_name="Gamma Map",
        implemented=True,
        summary="장면 반사도가 Gamma 분포라고 가정한 MAP(최대사후확률) 필터.",
        references=[
            "A. Lopes, E. Nezry, R. Touzi, H. Laur, \"Maximum a posteriori speckle "
            "filtering and first order texture models in SAR images,\" IGARSS 1990, "
            "pp. 2409-2412.",
            "기반이 된 MAP 필터: D. T. Kuan, A. A. Sawchuk, T. C. Strand, P. Chavel, "
            "\"Adaptive restoration of images with speckle,\" IEEE Transactions on "
            "Acoustics, Speech, and Signal Processing, ASSP-35(3):373-383, 1987 "
            "(및 Kuan et al., IEEE TPAMI PAMI-7(2):165-177, 1985).",
        ],
    ),
    FilterReference(
        key="lee",
        snap_name="Lee",
        implemented=True,
        summary="지역 평균/분산 기반 MMSE 적응형 필터(정사각형 단일 윈도우).",
        references=[
            "J. S. Lee, \"Digital image enhancement and noise filtering by use of "
            "local statistics,\" IEEE Transactions on Pattern Analysis and Machine "
            "Intelligence, PAMI-2(2):165-168, 1980.",
            "J. S. Lee, \"Speckle analysis and smoothing of synthetic aperture radar "
            "images,\" Computer Graphics and Image Processing, 17(1):24-32, 1981.",
        ],
    ),
    FilterReference(
        key="refined_lee",
        snap_name="Refined Lee",
        implemented=True,
        summary="방향성 edge-aligned 서브윈도우를 골라 경계를 보존하는 Lee 변형.",
        references=[
            "J. S. Lee, \"Refined filtering of image noise using local statistics,\" "
            "Computer Graphics and Image Processing, 15(4):380-389, 1981.",
            "J. S. Lee, E. Pottier, \"Polarimetric Radar Imaging: From Basics to "
            "Applications,\" CRC Press, 2009. (SNAP이 참조로 명시)",
            "방향 판정용 compass gradient 마스크: G. S. Robinson, \"Edge detection by "
            "compass gradient masks,\" Computer Graphics and Image Processing, "
            "6(5):492-502, 1977.",
            "균질/이질/점 표적 임계값 분류(별개 논문): A. Lopes, R. Touzi, E. Nezry, "
            "\"Adaptive speckle filters and scene heterogeneity,\" IEEE TGRS, "
            "28(6):992-1000, 1990; A. Lopes, E. Nezry, R. Touzi, H. Laur, "
            "\"Structure detection and statistical adaptive speckle filtering in SAR "
            "images,\" Int. J. Remote Sensing, 14(9):1735-1758, 1993.",
        ],
    ),
    FilterReference(
        key="lee_sigma",
        snap_name="Lee Sigma (Improved)",
        implemented=True,
        summary="화소값이 평균의 ±sigma 구간에 드는 이웃만 평균내는 sigma 필터의 개선판.",
        references=[
            "J. S. Lee, J. H. Wen, T. L. Ainsworth, K. S. Chen, A. J. Chen, "
            "\"Improved Sigma Filter for Speckle Filtering of SAR Imagery,\" IEEE "
            "Transactions on Geoscience and Remote Sensing, 47(1):202-213, 2009.",
            "원 sigma 필터: J. S. Lee, \"Digital image smoothing and the sigma "
            "filter,\" Computer Vision, Graphics, and Image Processing, "
            "24(2):255-269, 1983.",
        ],
    ),
    FilterReference(
        key="idan",
        snap_name="IDAN",
        implemented=False,
        summary="region-growing으로 적응형 이웃을 만든 뒤 sigma 기준으로 필터링.",
        references=[
            "G. Vasile, E. Trouve, J. S. Lee, V. Buzuloiu, \"Intensity-Driven "
            "Adaptive-Neighborhood Technique for Polarimetric and Interferometric "
            "SAR Parameters Estimation,\" IEEE Transactions on Geoscience and Remote "
            "Sensing, 44(6):1609-1621, 2006.",
        ],
    ),
    FilterReference(
        key="mulog",
        snap_name="MuLoG",
        implemented=False,
        summary="로그 변환 후 임의의 가우시안 denoiser(NLM 등)를 붙이는 다채널 프레임워크.",
        references=[
            "C. A. Deledalle, L. Denis, S. Tabti, F. Tupin, \"MuLoG, or How to apply "
            "Gaussian denoisers to multi-channel SAR speckle reduction?,\" IEEE "
            "Transactions on Image Processing, 26(9):4389-4403, 2017.",
        ],
    ),
)


def format_references() -> str:
    """SNAP_SPECKLE_FILTERS를 사람이 읽기 좋은 여러 줄 문자열로 만든다."""
    lines: list[str] = []
    for f in SNAP_SPECKLE_FILTERS:
        status = "구현됨" if f.implemented else "미구현"
        lines.append(f"[{status}] {f.snap_name}  (key={f.key})")
        lines.append(f"    {f.summary}")
        for ref in f.references:
            lines.append(f"    - {ref}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_references())
