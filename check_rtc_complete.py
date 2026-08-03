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

⚠ 가로선으로 끊긴다고 다 절단은 아니다
    `aoi_wkt`로 clip한 산출물은 **창의 남/북 경계가 위경도 가로선**이라 거기서
    뚝 끊긴다. 정상이다. 창을 알아야 정상인지 절단인지 갈린다.

        38C3  자료 끝 34.08N,  clip 창 남쪽 34.07N  →  정상

    창은 `rtc_basin_extdem.py`가 산출 폴더의 **`_clip_windows.json`** 에
    파일별로 남긴다. 그 기록을 먼저 쓰고, 없는 파일만 `--clip-south` 값을
    쓴다. **창이 다른 산출물이 한 폴더에 섞이면 `--clip-south` 하나로는
    감당이 안 되므로** 기록 쪽이 정답이다.

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
import json
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


def last_data_lat(src, rows: int, steps: int = 200):
    """자료가 있는 가장 남쪽·북쪽 위도. 아래에서 위로 훑어 첫 값을 찾는다."""
    from rasterio.warp import transform_bounds

    step = max(1, src.height // steps)

    def scan(order):
        for i in order:
            off = min(i * step, src.height - rows)
            try:
                a = src.read(1, window=Window(0, off, src.width, rows))
            except Exception:                               # noqa: BLE001
                continue
            if (np.isfinite(a) & (a != 0)).any():
                return off
        return None

    lo = scan(range(steps - 1, -1, -1))       # 아래에서 위로 → 남쪽 끝
    hi = scan(range(steps))                   # 위에서 아래로 → 북쪽 끝
    if lo is None:
        return None, None

    def lat(row):
        b = src.window_bounds(Window(0, row, src.width, rows))
        return transform_bounds(src.crs, "EPSG:4326", *b)[1]

    return lat(lo), lat(hi)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tags", nargs="*", help="검사할 씬 ID(4자리). 없으면 전체")
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--bands", type=int, default=20, help="세로 분할 수")
    ap.add_argument("--rows", type=int, default=8, help="띠마다 읽을 행 수")
    ap.add_argument("--fresh-sec", type=float, default=120.0,
                    help="이 시간 안에 수정된 파일은 '처리중'으로 건너뛴다")
    ap.add_argument("--clip-south", type=float, default=None,
                    help="clip 창의 남쪽 위도. 주면 거기서 끝난 것을 정상으로 본다")
    ap.add_argument("--lat-tol", type=float, default=0.15,
                    help="--clip-south 와의 허용 오차(도)")
    args = ap.parse_args()

    tifs = sorted(args.dir.glob("*.tif"))
    if not tifs:
        raise SystemExit(f"tif 없음: {args.dir.resolve()}")
    want = {t.upper() for t in args.tags}

    # 파일별 clip 창 기록 — rtc_basin_extdem.py 가 남긴다
    rec_p = args.dir / "_clip_windows.json"
    rec = {}
    if rec_p.exists():
        try:
            rec = json.loads(rec_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠ {rec_p.name} 를 읽을 수 없다 — --clip-south 로만 판정한다")

    print(f"{args.dir.resolve()}")
    print(f"창 기록 {len(rec)}건" + ("" if rec else " — 없음") + "\n")
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
            south, north = last_data_lat(s, args.rows)

        bar = "".join(BLOCKS[min(8, int((100 - v) / 12.5))] for v in prof)
        last = max((i for i, v in enumerate(prof) if v > 0.05), default=-1)
        frac = (last + 1) / args.bands

        # 끝난 이유는 둘 중 하나면 된다.
        #   ① 래스터 자체의 마지막 행까지 자료가 닿았다 (스와스가 자연히 끝남)
        #   ② clip 창의 남쪽 경계에서 끝났다 — 창 경계는 위경도 가로선이라
        #      스와스를 뚝 자른다. 이 경우 래스터 아래쪽은 비어 있는 게 정상이다.
        # 둘 다 아니면서 중간에서 끊겼으면 절단이다.
        # 이 파일의 창 남쪽 위도 — 기록이 있으면 그걸, 없으면 --clip-south
        r = rec.get(p.name)
        c_south = r["bounds_4326"][1] if r else args.clip_south
        src = "기록" if r else "--clip-south"

        at_bottom = frac >= 1 - 1 / args.bands
        at_window = (c_south is not None and south is not None
                     and abs(south - c_south) < args.lat_tol)

        if south is None:
            ok, note = False, "**자료 없음**"
        elif at_bottom:
            ok, note = True, f"완료 — 래스터 끝까지 ({south:.2f}N)"
        elif at_window:
            ok, note = True, (f"완료 — 창 남쪽에서 끝 "
                              f"({south:.2f}N ≈ {c_south:.2f}N, {src})")
        else:
            ok = False
            w_txt = (f", 창은 {c_south:.2f}N({src})" if c_south is not None else
                     " — 창 기록이 없다. rtc_basin_extdem.py 를 다시 돌리거나 "
                     "--clip-south 로 줄 것")
            note = f"**{frac*100:.0f}% 에서 끊김 — 자료 끝 {south:.2f}N{w_txt}**"
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
