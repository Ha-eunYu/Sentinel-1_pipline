# -*- coding: utf-8 -*-
"""RTC 산출 tif가 **끝까지 쓰였는지** 검사한다.

왜 필요한가
-----------
SNAP `gpt`가 메모리 부족으로 죽으면 산출 GeoTIFF가 중간에서 잘린다. 그런데
**파일 크기나 "열리는지"로는 못 가른다** — GDAL이 안 쓰인 타일을 nodata로
채워 돌려주므로 잘린 파일도 멀쩡히 열리고 통계도 나온다. 2026-08-03에 영산강
93DD가 이렇게 잘렸는데, 39 MB짜리 정상 산출물과 구별이 안 됐다.

어떻게 가르나
-------------
**행 방향 유효화소 분포**를 본다. 지형보정된 스와스는 기울어져 있어 위아래로
서서히 줄어든다. 잘린 파일은 어느 행에서 뚝 끊긴다.

    6D9F  위 |         ███▇▆▆▅▄▃▂▁| 아래   정상 — 마지막 행까지 닿는다
    93DD  위 |▁▁▂▃▄▄▅▆▇▇█         | 아래   절단 — 가장 짙은 데서 끊겼다

93DD는 아래로 갈수록 **늘다가** 최대치에서 멈췄다. 정상이라면 거기서부터
줄어들어야 한다.

⚠ 쓰는 중인 파일
    미완성 타일을 읽으면 `TIFFReadEncodedTile() failed`가 난다. 최근 수정된
    파일은 `--fresh-sec`(기본 120초)로 걸러 "처리중"으로만 표시한다.

실행
----
    python check_rtc_complete.py                          # 기본 폴더 전체
    python check_rtc_complete.py --dir downloads/rtc_extdem
    python check_rtc_complete.py 93DD 6D9F                # 씬 ID만

배경: `SNAP_MEMORY_KR.md`
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

DEFAULT_DIR = Path("downloads/rtc_extdem")
TAG_RE = re.compile(r"_([0-9A-F]{4})(?:_COG)?[._]")
BLOCKS = "█▇▆▅▄▃▂▁ "                       # 짙음 → 옅음 → 없음


def scene_tag(p: Path) -> str:
    """파일명에서 4자리 씬 ID. 앞쪽 날짜·궤도 숫자와 겹치지 않게 뒤에서 찾는다."""
    m = TAG_RE.search(p.name[40:])
    return m.group(1) if m else p.stem[-4:]


def profile(src, bands: int, rows: int) -> list[float]:
    """세로로 `bands`등분해 각 띠의 유효화소 비율(%)."""
    step = max(1, src.height // bands)
    out = []
    for i in range(bands):
        off = min(i * step, src.height - rows)
        try:
            a = src.read(1, window=Window(0, off, src.width, rows))
            out.append(float((np.isfinite(a) & (a != 0)).mean() * 100))
        except Exception:                                   # noqa: BLE001
            out.append(0.0)                                 # 안 쓰인 타일
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tags", nargs="*", help="검사할 씬 ID(4자리). 없으면 전체")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--bands", type=int, default=20, help="세로 분할 수")
    ap.add_argument("--rows", type=int, default=8, help="띠마다 읽을 행 수")
    ap.add_argument("--fresh-sec", type=float, default=120.0,
                    help="이 시간 안에 수정된 파일은 '처리중'으로 건너뛴다")
    args = ap.parse_args()

    tifs = sorted(args.dir.glob("*.tif"))
    if not tifs:
        raise SystemExit(f"tif 없음: {args.dir.resolve()}")
    want = {t.upper() for t in args.tags}

    print(f"{args.dir.resolve()}\n")
    bad = 0
    for p in tifs:
        tag = scene_tag(p)
        if want and tag not in want:
            continue
        mb = p.stat().st_size / 1e6
        age = time.time() - p.stat().st_mtime
        if age < args.fresh_sec:
            print(f"{tag:<6}{mb:>8.0f} MB   {age:>3.0f}초 전 기록 — **처리중**")
            continue

        with rasterio.open(p) as s:
            prof = profile(s, args.bands, args.rows)
            w, h = s.width, s.height

        bar = "".join(BLOCKS[min(8, int((100 - v) / 12.5))] for v in prof)
        # 유효가 있는 마지막 띠. 끝에서 두 띠 안이면 스와스가 자연스레 끝난 것.
        last = max((i for i, v in enumerate(prof) if v > 0.05), default=-1)
        ok = last >= args.bands - 2
        note = "완료" if ok else f"**{(last + 1) / args.bands * 100:.0f}% 에서 절단**"
        bad += 0 if ok else 1
        print(f"{tag:<6}{mb:>8.0f} MB  {w:>7,}x{h:<7,}  위|{bar}|아래  {note}")

    print(f"\n  {BLOCKS[0]} 유효 많음 … {BLOCKS[7]} 적음, 공백 = 0")
    if bad:
        print(f"  **절단 {bad}건** — 해당 granule을 다시 처리할 것 "
              f"(동시 실행 수는 SNAP_MEMORY_KR.md 6장 참고)")
    else:
        print("  전부 끝까지 쓰였다")


if __name__ == "__main__":
    main()
