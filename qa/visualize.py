"""
필터 비교 결과를 눈으로 볼 수 있는 패널 PNG로 만든다.

수치 지표(qa.metrics)만으로는 "소하천이 실제로 어떻게 보이는지" 감이 안 오므로,
동일 영역·동일 스트레치로 필터별 결과를 나란히 붙여준다. QGIS에서 하나씩
열어 비교하는 수고를 덜고, 발표자료(QA.pptx)에 바로 쓸 수 있다.

의존성: Pillow (환경에 없으면 `pip install pillow`). 이 모듈만 Pillow를
요구하며, 전처리 파이프라인 본체는 Pillow 없이 동작한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .compare import FilterResult
from .metrics import to_db

logger = logging.getLogger(__name__)


def _stretch_db(linear: np.ndarray, lo_db: float, hi_db: float) -> np.ndarray:
    """linear power → dB → [0,1] 선형 스트레치. nan은 0으로."""
    db = to_db(linear)
    out = (db - lo_db) / (hi_db - lo_db)
    return np.clip(np.nan_to_num(out, nan=0.0), 0.0, 1.0)


def to_rgb(
    hh: np.ndarray,
    hv: np.ndarray | None = None,
    hh_range: tuple[float, float] = (-18.0, -2.0),
    hv_range: tuple[float, float] = (-26.0, -10.0),
) -> np.ndarray:
    """
    QGIS에서 흔히 쓰는 의사컬러(R=HH, G=HV)로 변환한다 (uint8 RGB).

    hv가 없으면 회색조(HH만)로 만든다. 스트레치 범위는 두 필터 결과를 비교할
    때 **반드시 동일하게** 유지해야 한다 (다르면 밝기 차이가 필터 차이처럼
    보인다).
    """
    r = _stretch_db(hh, *hh_range)
    if hv is None:
        rgb = np.dstack([r, r, r])
    else:
        g = _stretch_db(hv, *hv_range)
        rgb = np.dstack([r, g, np.zeros_like(r)])
    return (rgb * 255).astype(np.uint8)


def save_comparison_panels(
    results: list[FilterResult],
    output_png: str | Path,
    hv_results: list[FilterResult] | None = None,
    columns: int = 2,
    panel_size: tuple[int, int] = (900, 520),
    hh_range: tuple[float, float] = (-18.0, -2.0),
    hv_range: tuple[float, float] = (-26.0, -10.0),
) -> Path:
    """
    FilterResult들의 배열을 격자 패널 PNG로 저장한다.

    results는 `compare_filters(..., keep_arrays=True)`로 얻어야 한다 (배열이
    없으면 그릴 수 없음). hv_results를 함께 주면 R=HH, G=HV 의사컬러가 되고,
    없으면 회색조가 된다. 각 패널에는 label과 핵심 지표를 캡션으로 넣는다.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "시각화에는 Pillow가 필요합니다: pip install pillow"
        ) from exc

    usable = [r for r in results if r.array is not None]
    if not usable:
        raise ValueError(
            "그릴 배열이 없습니다. compare_filters(..., keep_arrays=True)로 호출하세요."
        )

    hv_map = {}
    if hv_results:
        hv_map = {r.label: r.array for r in hv_results if r.array is not None}

    pw, ph = panel_size
    caption_h = 22
    rows = (len(usable) + columns - 1) // columns
    gap = 8

    sheet = Image.new(
        "RGB",
        (columns * pw + (columns + 1) * gap, rows * (ph + caption_h) + (rows + 1) * gap),
        (18, 18, 18),
    )
    draw = ImageDraw.Draw(sheet)

    for i, r in enumerate(usable):
        rgb = to_rgb(r.array, hv_map.get(r.label), hh_range, hv_range)
        im = Image.fromarray(rgb).resize((pw, ph), Image.NEAREST)

        cx = gap + (i % columns) * (pw + gap)
        cy = gap + (i // columns) * (ph + caption_h + gap)
        sheet.paste(im, (cx, cy + caption_h))

        # 캡션은 ASCII로 쓴다: PIL 기본 비트맵 폰트에는 한글 글리프가 없어
        # 한글을 넣으면 네모(tofu)로 깨진다. 한글 폰트를 별도로 싣는 대신
        # 지표명을 영문 약어로 표기한다 (stream=소하천 유지율, edge=경계
        # 보존율, sep=수면/육지 Fisher 분리도).
        caption = (
            f"{r.label}   ENL {r.enl:.1f} | stream {r.thin_line_retention:.0f}% | "
            f"edge {r.step_edge_retention:.0f}% | sep {r.separability:.2f}"
        )
        draw.text((cx + 4, cy + 4), caption, fill=(240, 240, 240))

    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_png)
    logger.info("비교 패널 저장: %s (%d개 패널)", output_png, len(usable))
    return output_png
