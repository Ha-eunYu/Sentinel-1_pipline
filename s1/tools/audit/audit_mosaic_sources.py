# -*- coding: utf-8 -*-
"""모자이크 VRT가 **원본을 빠뜨리지 않았는지** 전수 점검한다.

왜
--
`gdalbuildvrt`는 밴드 수가 다른 원본을 **경고만 내고 조용히 건너뛴다**.

    Warning 1: gdalbuildvrt does not support heterogeneous band numbers:
               expected 1, got 2. Skipping ...

`prepro_grd_gpt.py`에 `saveLayoverShadowMask="true"`를 넣은 뒤로 RTC 산출이
2밴드(1 dB, 2 레이오버/섀도)가 됐다. 그 전 산출은 1밴드다. 그래서 한 폴더 안에
1밴드와 2밴드가 섞여 있고, 모자이크를 만들 때 **뒤에 만든 2밴드 산출이 통째로
빠질 수 있다**. 빠져도 VRT는 정상으로 보이고 오류도 안 난다.

무엇을 하나
-----------
날짜마다 디스크의 원본 수와 VRT에 실제로 들어간 수를 견주고, 빠진 파일의
밴드 수를 같이 보여 준다.

고치는 법
---------
`gdalbuildvrt`에 **`-b 1`**을 준다. 그러면 모든 원본에서 1번 밴드만 쓰므로
밴드 수가 달라도 섞인다. `rebuild_mosaic_extdem.py`가 그렇게 한다.

실행
----
    python audit_mosaic_sources.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from s1.core.paths import RTC_EXTDEM_DIR, RTC_FROST_VH_DIR, VRT_VH_DIR

import rasterio

VRT = VRT_VH_DIR
SRC_DIRS = [RTC_FROST_VH_DIR, RTC_EXTDEM_DIR]
DATE_RE = re.compile(r"_(\d{8})T")
SRC_RE = re.compile(r"<SourceFilename[^>]*>([^<]+)</SourceFilename>")


def bands_of(p: Path) -> int:
    try:
        with rasterio.open(p) as s:
            return s.count
    except Exception:                                       # noqa: BLE001
        return -1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vrt-dir", type=Path, default=VRT)
    args = ap.parse_args()

    on_disk: dict[str, list[Path]] = {}
    for d in SRC_DIRS:
        for p in d.glob("*.tif"):
            m = DATE_RE.search(p.name)
            if m:
                on_disk.setdefault(m.group(1), []).append(p)

    print(f"{'날짜':<10}{'디스크':>7}{'VRT':>6}{'빠짐':>6}   빠진 파일(밴드 수)")
    print("-" * 84)
    bad = 0
    for vp in sorted(args.vrt_dir.glob("mosaic_*_vh.vrt")):
        date = vp.stem.split("_")[1]
        want = on_disk.get(date, [])
        got = {Path(s).name for s in SRC_RE.findall(
            vp.read_text(encoding="utf-8", errors="replace"))}
        miss = [p for p in want if p.name not in got]
        flag = "" if not miss else "  ⚠"
        txt = ", ".join(f"{p.name[-26:]}({bands_of(p)}밴드)" for p in miss[:3])
        if len(miss) > 3:
            txt += f" 외 {len(miss)-3}개"
        bad += len(miss)
        print(f"{date:<10}{len(want):>7}{len(got):>6}{len(miss):>6}{flag}   {txt}")

    print("-" * 84)
    if bad:
        print(f"**{bad}장이 모자이크에서 빠졌다.** `gdalbuildvrt -b 1` 로 "
              f"다시 만들 것 — rebuild_mosaic_extdem.py 참고")
    else:
        print("빠진 원본 없음")


if __name__ == "__main__":
    main()
