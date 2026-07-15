"""
speckle 필터 통제 비교 실행기.

**같은 입력 crop에 필터만 바꿔** 지표를 재는 것이 핵심이다. 서로 다른 시점에
서로 다른 설정으로 만든 산출물끼리 비교하면 (필터 종류·윈도우·노이즈 제거·
공식 버전이 한꺼번에 달라져) 무엇 때문에 차이가 났는지 알 수 없다. 실제로
이 저장소에서도 그런 교란된 비교 때문에 한 번 잘못된 결론에 도달했었다
(README "필터 QA" 참고).

입력은 **linear power(σ0 linear)** GeoTIFF여야 한다. KOMPSAT-5 GTC_A 제품은
amplitude DN이므로 `σ0_linear = K × DN²` (K는 src/calibration.py의 K-factor)
로 변환해 넣을 것 (dB도 안 됨 — speckle 통계 모델이 linear에서만 성립).

사용 예 (05_KOMPSAT5 폴더에서):

    from qa import FilterSpec, compare_filters, format_table

    results = compare_filters(
        "path/to/k5_sigma0_linear.tif",
        specs=[
            FilterSpec("refined_lee 7x7", "refined_lee", window_size=7),
            FilterSpec("frost 7x7 d=1.0", "frost", window_size=7, damping=1.0),
        ],
        enl=1.0,
        window=(3000, 4000, 1200, 1200),   # col_off, row_off, width, height
    )
    print(format_table(results))

(이 패키지는 RCM 전처리 프로젝트에서 이식했다. "이 저장소에서 교란된 비교로
틀린 결론에 도달했었다"는 아래 언급은 원 프로젝트의 이력이다.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from filtering import FilterMethod, make_filter_fn

from . import metrics

logger = logging.getLogger(__name__)

NODATA = -9999.0


@dataclass(frozen=True)
class FilterSpec:
    """비교할 필터 하나의 설정. label은 표에 그대로 출력된다."""

    label: str
    method: FilterMethod | str
    window_size: int = 5
    damping: float = 2.0            # frost 전용
    sigma: float = 0.9              # lee_sigma 전용
    min_valid_fraction: float = 0.5  # refined_lee 전용


@dataclass
class FilterResult:
    """필터 하나에 대한 측정 결과."""

    label: str
    enl: float                  # speckle 억제도 (↑좋음)
    thin_line_retention: float  # 소하천 유지율 % (↑좋음)
    step_edge_retention: float  # 계단형 경계 보존율 % (↑좋음)
    separability: float         # 수면/육지 Fisher 분리도 (↑좋음)
    otsu_db: float              # Otsu 임계값 (dB)
    array: np.ndarray | None = field(default=None, repr=False)  # 시각화용(선택)


def load_linear_crop(
    linear_tif: str | Path,
    band: int = 1,
    window: tuple[int, int, int, int] | None = None,
    nodata: float = NODATA,
) -> tuple[np.ndarray, np.ndarray]:
    """
    01_*_linear_unfiltered.tif에서 crop을 읽어 (linear, valid_mask)를 돌려준다.

    무효 픽셀은 nan으로 채운다 (metrics 규약). window는 (col_off, row_off,
    width, height); None이면 전체.
    """
    with rasterio.open(linear_tif) as src:
        w = Window(*window) if window else None
        arr = src.read(band, window=w).astype(np.float64)
        nd = src.nodata if src.nodata is not None else nodata

    valid = np.isfinite(arr) & (arr != nd) & (arr > 0)
    arr = np.where(valid, arr, np.nan)
    return arr, valid


def compare_filters(
    linear_tif: str | Path,
    specs: list[FilterSpec],
    enl: float,
    band: int = 1,
    window: tuple[int, int, int, int] | None = None,
    keep_arrays: bool = False,
    line_window: int = 9,
    line_percentile: float = 99.0,
) -> list[FilterResult]:
    """
    동일 crop에 각 필터를 적용해 지표를 측정한다. 첫 결과는 항상 미필터 기준.

    Parameters
    ----------
    enl:
        Equivalent Number of Looks. 제품의 실제 룩 수를 줘야 한다
        (metadata.read_enl 참고). RCM 고해상도는 보통 1.0.
    keep_arrays:
        True면 각 결과에 필터링된 배열을 담아둔다 (visualize용). 메모리를
        쓰므로 필요할 때만.
    line_window / line_percentile:
        소하천 검출 파라미터 (metrics.detect_thin_dark_lines).

    Returns
    -------
    list[FilterResult] — [0]은 미필터 기준(label="미필터 (기준)"), 이후 specs 순서.
    """
    linear, valid = load_linear_crop(linear_tif, band=band, window=window)
    logger.info("QA crop: %s, 유효 픽셀 %.1f%%", linear.shape, valid.mean() * 100)

    # 평가 마스크는 **미필터 영상에서 한 번만** 만든다 (공정 비교의 핵심).
    line_mask = metrics.detect_thin_dark_lines(linear, valid, line_window, line_percentile)
    edge_mask = metrics.detect_strong_edges(linear, valid)
    logger.info(
        "소하천 후보 %d px / 강한 경계 %d px", int(line_mask.sum()), int(edge_mask.sum())
    )

    def measure(label: str, arr: np.ndarray) -> FilterResult:
        thr, sep = metrics.fisher_separability(arr)
        return FilterResult(
            label=label,
            enl=metrics.equivalent_number_of_looks(arr),
            thin_line_retention=metrics.thin_line_retention(arr, linear, line_mask, line_window),
            step_edge_retention=metrics.step_edge_retention(arr, linear, edge_mask),
            separability=sep,
            otsu_db=thr,
            array=arr if keep_arrays else None,
        )

    results = [measure("미필터 (기준)", linear)]

    for spec in specs:
        fn = make_filter_fn(
            spec.method,
            window_size=spec.window_size,
            enl=enl,
            min_valid_fraction=spec.min_valid_fraction,
            damping=spec.damping,
            sigma=spec.sigma,
        )
        out = fn(linear, valid, spec.window_size, NODATA)
        out = np.where(valid, out, np.nan)
        logger.info("측정 완료: %s", spec.label)
        results.append(measure(spec.label, out))

    return results


def format_table(results: list[FilterResult]) -> str:
    """결과를 사람이 읽는 표로. (↑ = 클수록 좋음)"""
    head = (
        f"{'필터':<28} {'ENL↑':>7} {'소하천유지↑':>11} {'경계보존↑':>10} "
        f"{'수면분리도↑':>11} {'Otsu(dB)':>9}"
    )
    lines = [head, "-" * len(head)]
    for r in results:
        lines.append(
            f"{r.label:<28} {r.enl:7.1f} {r.thin_line_retention:10.0f}% "
            f"{r.step_edge_retention:9.0f}% {r.separability:11.2f} {r.otsu_db:9.2f}"
        )
    return "\n".join(lines)


def format_markdown(results: list[FilterResult]) -> str:
    """README 등에 붙일 마크다운 표."""
    lines = [
        "| 필터 | ENL ↑ | 소하천 유지 ↑ | 경계 보존 ↑ | 수면 분리도 ↑ | Otsu (dB) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | {r.enl:.1f} | {r.thin_line_retention:.0f}% | "
            f"{r.step_edge_retention:.0f}% | {r.separability:.2f} | {r.otsu_db:.2f} |"
        )
    return "\n".join(lines)


# 홍수 매핑 QA에 자주 쓰는 기본 비교 세트 (README "필터 QA"의 근거)
DEFAULT_SPECS: list[FilterSpec] = [
    FilterSpec("lee 5x5", "lee", window_size=5),
    FilterSpec("refined_lee 5x5", "refined_lee", window_size=5),
    FilterSpec("refined_lee 7x7", "refined_lee", window_size=7),
    FilterSpec("gamma_map 5x5", "gamma_map", window_size=5),
    FilterSpec("lee_sigma 7x7", "lee_sigma", window_size=7),
    FilterSpec("median 5x5", "median", window_size=5),
    FilterSpec("frost 5x5 d=1.0", "frost", window_size=5, damping=1.0),
    FilterSpec("frost 5x5 d=2.0", "frost", window_size=5, damping=2.0),
    FilterSpec("frost 7x7 d=1.0", "frost", window_size=7, damping=1.0),
    FilterSpec("frost 7x7 d=2.0", "frost", window_size=7, damping=2.0),
]
