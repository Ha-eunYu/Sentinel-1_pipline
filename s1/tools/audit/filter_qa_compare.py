# -*- coding: utf-8 -*-
"""필터별 RTC 산출물을 4축으로 정량 비교한다 (VH 재검증용).

축 (qa.metrics)
---------------
1. **ENL** — speckle 억제도. 높을수록 잡음이 잘 눌렸다.
2. **가는 선 보존** — 소하천 같은 어두운 선이 얼마나 살아남았나(%).
3. **경계 보존** — 계단 경계의 대비가 얼마나 유지됐나(%).
4. **수면 분리도** — 물/육지 두 분포가 얼마나 잘 갈리나(Fisher).

**수체 판별에서 중요한 것은 ENL 하나가 아니다.** 가는 수로가 뭉개지면 면적이
줄고, 경계가 흐려지면 임계값이 흔들린다. 그래서 4축을 함께 본다.

비교는 **같은 crop** 에서 한다(전체 씬을 다 읽으면 메모리·시간이 과하다).
crop 은 유효화소가 많고 물/육지가 섞인 곳을 자동으로 고른다.

실행:
    conda run -n s1_snappy python -m s1.tools.audit.filter_qa_compare \
        --dir experiments/vh_filter
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from qa import metrics as M
from s1.core.paths import PROJECT_DIR, rel

TAG_RE = re.compile(r"_vh_([a-z]+)\.tif$|_vv_([a-z]+)\.tif$")


def db_to_linear(db: np.ndarray) -> np.ndarray:
    return np.power(10.0, db / 10.0)


def pick_crop(path: Path, size: int, tries: int = 40) -> tuple[int, int]:
    """물/육지가 섞이고 유효화소가 많은 crop 위치를 고른다.

    dB 분포의 표준편차가 큰 곳 = 물과 육지가 함께 있는 곳으로 본다.
    """
    best, best_score = (0, 0), -1.0
    with rasterio.open(path) as src:
        rng = np.random.default_rng(0)
        for _ in range(tries):
            col = int(rng.integers(0, max(1, src.width - size)))
            row = int(rng.integers(0, max(1, src.height - size)))
            a = src.read(1, window=Window(col, row, size, size))
            valid = np.isfinite(a) & (a != 0)
            if valid.mean() < 0.95:
                continue
            score = float(np.std(a[valid]))
            if score > best_score:
                best, best_score = (col, row), score
    return best


def read_crop(path: Path, col: int, row: int, size: int) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1, window=Window(col, row, size, size))


def main() -> None:
    ap = argparse.ArgumentParser(description="필터별 RTC 4축 정량 비교")
    ap.add_argument("--dir", type=Path, default=PROJECT_DIR / "experiments" / "vh_filter")
    ap.add_argument("--size", type=int, default=1024, help="crop 한 변(px)")
    ap.add_argument("--window", type=int, default=7, help="ENL 창 크기")
    args = ap.parse_args()

    tifs = sorted(args.dir.glob("*.tif"))
    if not tifs:
        raise SystemExit(f"{rel(args.dir)} 에 tif 가 없습니다.")

    # 기준(무필터)에서 crop 위치를 고르고, 모든 산출물에 같은 위치를 쓴다.
    base = next((t for t in tifs if "nofilter" in t.name), tifs[0])
    col, row = pick_crop(base, args.size)
    print(f"crop (col={col}, row={row}, {args.size}px) — 기준 {base.name[-28:]}\n")

    ref_db = read_crop(base, col, row, args.size)
    ref_lin = db_to_linear(ref_db)
    valid = np.isfinite(ref_db) & (ref_db != 0)
    # 선·경계 마스크는 **무필터 영상**에서 만든다. 필터가 지운 것을 재려면
    # 기준이 필터 이전이어야 하기 때문이다.
    ref_lines = M.detect_thin_dark_lines(ref_lin, valid)
    ref_edges = M.detect_strong_edges(ref_lin, valid)
    print(f"기준 마스크: 가는선 {int(ref_lines.sum()):,}px · "
          f"경계 {int(ref_edges.sum()):,}px\n")

    print(f"{'필터':>12} {'ENL':>7} {'가는선보존%':>11} {'경계보존%':>10} {'수면분리도':>10}")
    rows = []
    for t in tifs:
        m = TAG_RE.search(t.name)
        tag = (m.group(1) or m.group(2)) if m else t.stem[-10:]
        db = read_crop(t, col, row, args.size)
        lin = db_to_linear(db)
        enl = M.equivalent_number_of_looks(lin, args.window)
        thin = M.thin_line_retention(lin, ref_lin, ref_lines)
        edge = M.step_edge_retention(lin, ref_lin, ref_edges)
        sep, _ = M.fisher_separability(lin)
        rows.append((tag, enl, thin, edge, sep))
        print(f"{tag:>12} {enl:>7.2f} {thin:>11.1f} {edge:>10.1f} {sep:>10.3f}")

    print("\n해석")
    print("  ENL ↑ = speckle 억제 강함 / 가는선·경계 보존 ↑ = 세부 손실 적음")
    print("  수체 판별에는 '가는선 보존'과 '수면 분리도'가 특히 중요하다.")
    filt = [r for r in rows if r[0] != "nofilter"]
    if filt:
        best_thin = max(filt, key=lambda r: r[2])
        best_sep = max(filt, key=lambda r: r[4])
        best_enl = max(filt, key=lambda r: r[1])
        print(f"\n  ENL 최고: {best_enl[0]} ({best_enl[1]:.2f})")
        print(f"  가는선 보존 최고: {best_thin[0]} ({best_thin[2]:.1f}%)")
        print(f"  수면 분리도 최고: {best_sep[0]} ({best_sep[4]:.3f})")


if __name__ == "__main__":
    main()
