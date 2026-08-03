# -*- coding: utf-8 -*-
"""external DEM 산출물을 얹어 날짜별 모자이크를 다시 만든다.

왜
--
`rtc_extdem/`의 산출물은 SNAP 자동 캐시 DEM이 하구 수역을 무효로 만든 문제를
피한 판이다(영산강 결측 20.2% → 0.0%). 기존 모자이크는 옛 산출물만 담고
있으므로 다시 만들어야 한다.

⚠ 세 가지
    · **나중에 오는 원본이 이긴다.** 그래서 `rtc_extdem`을 목록 끝에 둔다.
    · **`-srcnodata 0 -vrtnodata 0`** 이 없으면 SNAP이 남긴 0을 유효값으로
      취급해 **멀쩡한 이웃 화소를 덮어쓴다**. 섬진강·금강 결측이 두 날짜에서
      크게 어긋나던 원인이 이것이었다.
    · **`-b 1` 이 없으면 extdem 산출물이 통째로 빠진다.** `prepro_grd_gpt.py`에
      `saveLayoverShadowMask="true"`를 넣은 뒤로 산출이 **2밴드**(1 dB,
      2 레이오버/섀도)가 됐는데, 옛 산출은 1밴드다. `gdalbuildvrt`는 밴드 수가
      다르면 **경고만 내고 건너뛴다**.

          Warning 1: gdalbuildvrt does not support heterogeneous band
                     numbers: expected 1, got 2. Skipping ...

      2026-08-03에 이걸 `capture_output=True`로 삼켜서, VRT가 옛 파일만 담고도
      성공한 것처럼 보였다. 그래서 **경고를 반드시 찍는다**.

실행
----
    python rebuild_mosaic_extdem.py --date 20250718 --date 20260720
    python rebuild_mosaic_extdem.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import rasterio

RTC = Path(r"F:\06_SAR_system\S1\downloads\rtc_grd_frost_vh")
EXT = Path(r"F:\06_SAR_system\S1\downloads\rtc_extdem")
VRT = Path(r"F:\06_SAR_system\S1\downloads\water_otsu\vrt_vh")
GDAL = Path(r"F:\envs\sar-gee\Library\bin")
DATE_RE = re.compile(r"_(\d{8})T")


def sources_for(date: str) -> list[Path]:
    """옛 산출물 먼저, external DEM 판을 **뒤에** — 뒤가 이긴다."""
    def pick(d: Path):
        return sorted(p for p in d.glob("*.tif")
                      if (m := DATE_RE.search(p.name)) and m.group(1) == date)
    return pick(RTC) + pick(EXT)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", action="append", required=False,
                    help="YYYYMMDD. 없으면 rtc_extdem 에 있는 날짜 전부")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dates = args.date or sorted({m.group(1) for p in EXT.glob("*.tif")
                                 if (m := DATE_RE.search(p.name))})
    if not dates:
        raise SystemExit("대상 날짜 없음")

    for date in dates:
        srcs = sources_for(date)
        out = VRT / f"mosaic_{date}_vh.vrt"
        n_ext = sum(1 for p in srcs if p.parent == EXT)
        print(f"■ {date}   원본 {len(srcs)}장 (external DEM {n_ext}장)")
        for p in srcs:
            mark = "  ← extdem(우선)" if p.parent == EXT else ""
            print(f"    {p.name[-34:]}{mark}")
        if args.dry_run:
            print()
            continue

        before = None
        if out.exists():
            with rasterio.open(out) as s:
                before = (s.width, s.height, s.res)
            shutil.copy2(out, out.with_suffix(".vrt.bak"))

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="ascii") as f:
            f.write("\n".join(str(p) for p in srcs))
            lst = f.name
        r = subprocess.run(
            [str(GDAL / "gdalbuildvrt"), "-overwrite",
             "-b", "1",                              # extdem은 2밴드다 — dB만 쓴다
             "-srcnodata", "0", "-vrtnodata", "0",   # 0을 유효값으로 보지 않는다
             "-input_file_list", lst, str(out)],
            check=True, text=True, capture_output=True)
        Path(lst).unlink(missing_ok=True)
        for line in (r.stderr or "").splitlines():
            if "Skipping" in line or "heterogeneous" in line:
                print(f"    ⚠ {line.strip()}")

        with rasterio.open(out) as s:
            now = (s.width, s.height, s.res)
        # 실제로 몇 장이 들어갔는지 센다 — 건너뛴 게 있으면 여기서 드러난다
        got = out.read_text(encoding="utf-8", errors="replace").count(
            "<SourceFilename")
        print(f"    → {now[0]:,} x {now[1]:,}  해상도 {now[2][0]:.3g}"
              f"   원본 {got}/{len(srcs)}장 반영")
        if got != len(srcs):
            print(f"    ⚠ **{len(srcs)-got}장이 빠졌다** — 위 경고를 볼 것")
        if before and before[2] != now[2]:
            print(f"    ⚠ **해상도가 바뀌었다** {before[2]} → {now[2]} — 확인할 것")
        print()

    if args.dry_run:
        raise SystemExit("--dry-run: 만들지 않았습니다.")
    print(f"산출 → {VRT}   (옛 판은 *.vrt.bak 로 남겨 뒀다)")


if __name__ == "__main__":
    main()
