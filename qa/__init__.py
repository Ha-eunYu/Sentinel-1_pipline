"""
rcm_preprocess.qa — speckle 필터 품질 평가(QA) 모듈.

전처리 결과에서 **어떤 필터·하이퍼파라미터를 쓸지**를 근거 있게 고르기 위한
측정 도구다. 육안 비교나 "speckle이 줄었나"만으로는 부족하다는 것이 실데이터
에서 드러났기 때문에 만들었다:

- `refined_lee`는 계단형 경계(step edge)에는 강하지만 **폭 1~3픽셀 소하천을
  오히려 지운다** (가장 균질한 서브윈도우를 고르는데, 하천 위 픽셀에서는
  "하천을 배제한 농지-only 서브윈도우"가 가장 균질하기 때문).
- `lee_sigma`는 밝은 점 표적은 보존하지만 **어두운 가는 선은 지운다**.
- 같은 speckle 억제 수준에서 `frost`가 소하천을 훨씬 잘 살린다.

이런 차이는 ENL(speckle 억제도) 하나만 봐서는 절대 안 보인다. 그래서 네 축으로
나눠 잰다 — speckle 억제 / **가는 선 보존** / 계단형 경계 보존 / 수면-육지 분리도.

구성
----
    metrics.py    지표 계산 (ENL, 소하천 유지율, 경계 보존율, Otsu/Fisher 분리도)
    compare.py    통제 비교 실행기 (동일 crop에 필터만 바꿔 측정) + 표 출력
    visualize.py  비교 패널 PNG 생성 (Pillow 필요, 선택)
    __main__.py   `python -m rcm_preprocess.qa` CLI

핵심 원칙: **같은 입력에 필터만 바꿔서 비교할 것.** 서로 다른 설정으로 만든
산출물끼리 비교하면 무엇 때문에 차이가 났는지 알 수 없다 (이 저장소도 그런
교란된 비교로 한 번 틀린 결론에 도달했었다 — README "필터 QA" 참고).

사용 예:

    python -m rcm_preprocess.qa \\
        data/processed/RCM1_.../01_sigma0_linear_unfiltered.tif \\
        --enl 1.0 --window 3000 4000 1200 1200 --png qa_panels.png
"""

from .compare import (
    DEFAULT_SPECS,
    FilterResult,
    FilterSpec,
    compare_filters,
    format_markdown,
    format_table,
    load_linear_crop,
)
from .metrics import (
    detect_strong_edges,
    detect_thin_dark_lines,
    equivalent_number_of_looks,
    fisher_separability,
    line_depth,
    local_cv,
    otsu_threshold,
    step_edge_retention,
    thin_line_retention,
    to_db,
)

__all__ = [
    # 비교 실행기
    "FilterSpec",
    "FilterResult",
    "compare_filters",
    "format_table",
    "format_markdown",
    "load_linear_crop",
    "DEFAULT_SPECS",
    # 지표
    "equivalent_number_of_looks",
    "thin_line_retention",
    "step_edge_retention",
    "fisher_separability",
    "detect_thin_dark_lines",
    "detect_strong_edges",
    "line_depth",
    "local_cv",
    "otsu_threshold",
    "to_db",
]
