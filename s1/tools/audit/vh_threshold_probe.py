# -*- coding: utf-8 -*-
"""VH RTC 의 물/육지 골짜기 위치를 실측해 **fallback 임계값**을 정한다.

왜 필요한가
-----------
궤도별 타일기반 Otsu 가 이봉 타일을 충분히 못 모으면 고정값으로 물러난다
(fallback). 그 값이 지금 **−16 dB**인데, 이건 **VV 기준**으로 잡은 값이다.
VH 는 물/육지 대비도 다르고 절대값도 낮아 그대로 쓰면 물을 놓친다.

판정 원칙 (2026-08-17 지시)
---------------------------
**물이 아닌 것을 물이라 해도 되지만, 물인 것을 물이 아니라고 하면 안 된다.**
즉 **과탐(false positive) 허용, 미탐(false negative) 회피**. 그래서 임계값을
골짜기 그대로가 아니라 **골짜기보다 높은 쪽(=물 쪽을 넓게 잡는 쪽)** 으로 민다.

dB 축에서 물은 어두운 쪽(작은 값)이다. 임계값 t 는 `dB < t` 를 물로 본다.
t 를 키우면 물 판정이 넓어진다 → 미탐이 줄고 과탐이 는다.

무엇을 재나
-----------
씬마다 히스토그램을 만들어
  1. 물 봉우리(어두운 쪽 국소 최대)
  2. 육지 봉우리(밝은 쪽 최대)
  3. 두 봉우리 사이 **골짜기**(최소)
를 찾고, 골짜기에 여유(margin)를 더한 값을 후보로 제시한다.

실행:
    conda run -n s1_snappy python -m s1.tools.audit.vh_threshold_probe
    conda run -n s1_snappy python -m s1.tools.audit.vh_threshold_probe --margin 1.5 --max-scenes 12
"""

from __future__ import annotations

import argparse
import numpy as np
import rasterio
from rasterio.windows import Window

from s1.core.paths import RTC_FROST_VH_DIR, rel
from s1.core.scene import parse_scene

HIST_MIN, HIST_MAX, BINS = -40.0, 5.0, 450   # 0.1 dB 폭
SEARCH_GAP_DB = 6.0   # 물 봉우리는 육지 봉우리보다 최소 이만큼 어두운 쪽에서 찾는다
CHUNK_ROWS = 2048


def scene_hist(path, step: int = 4) -> np.ndarray:
    """씬 하나의 dB 히스토그램(청크로 읽어 메모리 안전). step 으로 솎아 읽는다."""
    counts = np.zeros(BINS, dtype="int64")
    with rasterio.open(path) as src:
        for row in range(0, src.height, CHUNK_ROWS):
            h = min(CHUNK_ROWS, src.height - row)
            a = src.read(1, window=Window(0, row, src.width, h))[::step, ::step]
            a = a[np.isfinite(a)]
            a = a[a != 0]                      # 0 = 미관측
            if a.size:
                counts += np.histogram(a, bins=BINS, range=(HIST_MIN, HIST_MAX))[0]
    return counts


def peaks_and_valley(counts: np.ndarray):
    """(물 봉우리, 골짜기, 육지 봉우리) dB. 찾지 못하면 None 을 섞어 반환."""
    centers = np.linspace(HIST_MIN, HIST_MAX, BINS, endpoint=False) + \
        (HIST_MAX - HIST_MIN) / BINS / 2
    if counts.sum() == 0:
        return None, None, None
    # 완만하게 다듬어 잡음 봉우리를 제거
    k = np.ones(9) / 9
    sm = np.convolve(counts.astype("float64"), k, mode="same")

    land_i = int(np.argmax(sm))                      # 육지 = 최대 봉우리
    # 물 봉우리는 육지 봉우리 바로 옆 어깨가 아니라 **충분히 어두운 쪽**에 있다.
    # 그냥 왼쪽 최대를 잡으면 육지 봉우리의 어깨를 물로 착각한다(실측 확인).
    # VH 육지가 −13 dB대이므로 최소 6 dB 아래에서만 찾는다.
    gap_bins = int(SEARCH_GAP_DB / ((HIST_MAX - HIST_MIN) / BINS))
    hi = land_i - gap_bins
    if hi < 20:
        return None, None, float(centers[land_i])
    water_i = int(np.argmax(sm[:hi]))
    if sm[water_i] <= 0:
        return None, None, float(centers[land_i])
    valley_i = water_i + int(np.argmin(sm[water_i:land_i]))
    return float(centers[water_i]), float(centers[valley_i]), float(centers[land_i])


def main() -> None:
    ap = argparse.ArgumentParser(description="VH fallback 임계값 실측")
    ap.add_argument("--max-scenes", type=int, default=10, help="표본 씬 수")
    ap.add_argument("--margin", type=float, default=1.0,
                    help="골짜기에 더할 여유 dB (미탐 회피용, 기본 1.0)")
    ap.add_argument("--step", type=int, default=4, help="픽셀 솎기 간격")
    args = ap.parse_args()

    tifs = sorted(RTC_FROST_VH_DIR.glob("*_vh.tif"))
    if not tifs:
        raise SystemExit(f"{rel(RTC_FROST_VH_DIR)} 에 VH 산출물이 없습니다.")
    # 남한 커버가 큰 씬을 고르기 어렵다면 용량 큰 순으로 — 넓게 찍은 씬이 이봉이 뚜렷
    tifs = sorted(tifs, key=lambda p: -p.stat().st_size)[:args.max_scenes]

    print(f"표본 {len(tifs)}씬 (용량 상위), 픽셀 1/{args.step} 솎기\n")
    print(f"{'날짜':>9} {'궤도':>7} {'물봉우리':>8} {'골짜기':>7} {'육지봉우리':>10}")
    valleys = []
    for t in tifs:
        k = parse_scene(t)
        w, v, land = peaks_and_valley(scene_hist(t, args.step))
        tag = f"{k.date:>9} {k.orbit:>7}" if k else f"{t.name[:17]:>17}"
        if v is None:
            print(f"{tag} {'-':>8} {'-':>7} {land if land else 0:>10.2f}  (이봉 아님)")
            continue
        valleys.append(v)
        print(f"{tag} {w:>8.2f} {v:>7.2f} {land:>10.2f}")

    if not valleys:
        raise SystemExit("\n이봉 구조를 찾은 씬이 없습니다. 표본을 늘리세요.")

    arr = np.array(valleys)
    print(f"\n골짜기 {len(arr)}개: 중앙값 {np.median(arr):.2f} dB, "
          f"범위 {arr.min():.2f} ~ {arr.max():.2f}")
    print(f"권장 fallback = 중앙값 + 여유({args.margin}) = "
          f"**{np.median(arr) + args.margin:.1f} dB**")
    print("\n판정 원칙: 물을 놓치지 않도록 골짜기보다 **높은 쪽**으로 민다.")
    print("           (dB < 임계값 을 물로 보므로 임계값이 클수록 물 판정이 넓다)")


if __name__ == "__main__":
    main()
