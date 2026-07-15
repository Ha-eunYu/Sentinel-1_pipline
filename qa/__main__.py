"""
speckle 필터 QA CLI.

linear power(σ0 linear) GeoTIFF의 한 영역(crop)에 여러 필터를 적용해 지표를
비교한다. **같은 입력에 필터만 바꿔** 재므로 결과를 필터 선택의 근거로 바로
쓸 수 있다. KOMPSAT-5 GTC_A 제품은 amplitude DN이므로 먼저
`σ0_linear = K × DN²` (src/calibration.py의 K-factor)로 변환해 넣을 것.

기본 비교 세트(compare.DEFAULT_SPECS)를 쓰거나, `--filters`로 직접 지정한다
(05_KOMPSAT5 폴더에서 실행):

    # 기본 세트 (lee/refined_lee/gamma_map/lee_sigma/median/frost 10종)
    python -m qa path/to/k5_sigma0_linear.tif \\
        --enl 1.0 --window 3000 4000 1200 1200

    # 특정 필터만 + 비교 패널 PNG 생성
    python -m qa <linear.tif> --enl 1.0 \\
        --filters refined_lee:7 frost:7:d=1.0 frost:5:d=2.0 \\
        --png qa_panels.png --markdown

ENL은 제품의 실제 룩 수를 줘야 한다 (K5는 Aux.xml의 azimuth/range 룩 수 곱;
싱글룩 제품은 1.0).
"""

from __future__ import annotations

import argparse
import logging
import sys

from .compare import DEFAULT_SPECS, FilterSpec, compare_filters, format_markdown, format_table

logger = logging.getLogger("qa")


def _parse_filter_spec(text: str) -> FilterSpec:
    """
    "method[:window][:d=DAMPING][:s=SIGMA]" 형식을 FilterSpec으로 파싱한다.

    예) "frost:7:d=1.0", "refined_lee:5", "lee_sigma:7:s=0.9", "median:5"
    """
    parts = text.split(":")
    method = parts[0]
    window = 5
    damping = 2.0
    sigma = 0.9

    for p in parts[1:]:
        if p.startswith("d="):
            damping = float(p[2:])
        elif p.startswith("s="):
            sigma = float(p[2:])
        else:
            window = int(p)

    label = f"{method} {window}x{window}"
    if method == "frost":
        label += f" d={damping}"
    elif method == "lee_sigma":
        label += f" s={sigma}"

    return FilterSpec(label, method, window_size=window, damping=damping, sigma=sigma)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m qa",
        description=(
            "speckle 필터 통제 비교 — 같은 입력에 필터만 바꿔 "
            "ENL(speckle 억제)·소하천 유지율·경계 보존율·수면 분리도를 측정"
        ),
    )
    p.add_argument("linear_tif", help="linear power(σ0 linear) GeoTIFF — dB/DN 아님")
    p.add_argument(
        "--enl",
        type=float,
        required=True,
        help="제품의 실제 ENL (K5는 Aux.xml의 룩 수 곱; 싱글룩이면 1.0)",
    )
    p.add_argument(
        "--window",
        type=int,
        nargs=4,
        metavar=("COL", "ROW", "W", "H"),
        default=None,
        help="분석할 crop (col_off row_off width height). 생략 시 전체 (느림)",
    )
    p.add_argument("--band", type=int, default=1, help="분석할 밴드 (기본 1=HH)")
    p.add_argument(
        "--filters",
        nargs="+",
        default=None,
        help=(
            "비교할 필터들. 형식: method[:window][:d=X][:s=Y] "
            "(예: frost:7:d=1.0 refined_lee:7). 생략 시 기본 세트 10종"
        ),
    )
    p.add_argument("--png", default=None, help="비교 패널 PNG 저장 경로 (Pillow 필요)")
    p.add_argument(
        "--hv-band",
        type=int,
        default=None,
        help="PNG를 R=HH/G=HV 의사컬러로 그릴 때의 HV 밴드 (예: 2)",
    )
    p.add_argument("--markdown", action="store_true", help="마크다운 표로 출력 (README 붙여넣기용)")
    p.add_argument("-v", "--verbose", action="store_true", help="상세 로그")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    specs = [_parse_filter_spec(f) for f in args.filters] if args.filters else DEFAULT_SPECS
    window = tuple(args.window) if args.window else None
    need_arrays = args.png is not None

    try:
        results = compare_filters(
            args.linear_tif,
            specs=specs,
            enl=args.enl,
            band=args.band,
            window=window,
            keep_arrays=need_arrays,
        )
    except Exception as exc:
        logger.error("QA 실패: %s", exc)
        if args.verbose:
            raise
        return 1

    print()
    print(format_markdown(results) if args.markdown else format_table(results))
    print()

    if args.png:
        from .visualize import save_comparison_panels

        hv_results = None
        if args.hv_band:
            hv_results = compare_filters(
                args.linear_tif,
                specs=specs,
                enl=args.enl,
                band=args.hv_band,
                window=window,
                keep_arrays=True,
            )
        save_comparison_panels(results, args.png, hv_results=hv_results)
        print(f"비교 패널 저장: {args.png}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
