# -*- coding: utf-8 -*-
"""제약 안 결측 영역만 잘라 **external DEM**으로 재처리한다.

배경
----
5대강 제약 안 dB에 결측이 있고, 원인은 COP30 값이 아니라 **DEM 지정 방식**이다.
같은 granule을 `demName="Copernicus 30m Global DEM"`(자동 캐시)으로 돌리면
영산강 제약의 20.23%가 비는데, **`externalDEMFile`로 돌리면 0.00%**가 된다
(2026-08-03 실측, 원본·0치환·NGII 세 판 모두 동일).

**결측이 두 날짜에서 비대칭이라 Δ%가 흔들린다.**

    영산강  2025 20.28% / 2026 20.29%   → 상쇄됨
    섬진강  2025  2.54% / 2026 19.09%   → 감소 **과대평가**
    금강    2025 14.20% / 2026  2.05%   → 감소 **과소평가**

granule 전체 재처리는 52분/장이다. 결측은 하구·인공호에 몰려 있으므로
**bbox만 Subset해서** 처리한다(`build_grd_rtc_graph(aoi_wkt=...)`).

실행
----
    conda run -n s1_snappy python patch_void_rtc.py
    conda run -n s1_snappy python patch_void_rtc.py --basin yeongsan --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from prepro_grd_gpt import build_grd_rtc_graph

# ⚠ `s1_snappy` 환경에는 shapely가 없다. 겹침 판정은 **경계상자 연산**으로
#   한다 — granule을 고르는 데는 충분하다(정확한 잘라내기는 SNAP Subset이
#   WKT로 한다). 다만 경계상자는 실제 스와스보다 넓으므로 **후보를 넉넉히
#   잡는 쪽**이라 안전하다.

GRD = Path("downloads/sentinel1_grd")
OUT = Path("downloads/rtc_void_patch")
BOXES = Path(r"F:\06_SAR_system\gee\Korea_WaterDetection_2025_2026\void_boxes.json")
# 전국을 덮는 COP30. **일반 GeoTIFF/VRT로 물리는 것이 요점**이다 —
# SNAP 자동 캐시 경로가 수역을 무효로 해석한다.
DEM = Path(r"F:\06_SAR_system\S1\downloads\dem\cop30_korea.vrt")
DATE_RE = re.compile(r"_(\d{8})T")


def footprint(zf: Path):
    """SAFE zip의 촬영 풋프린트 경계상자 (minx, miny, maxx, maxy)."""
    try:
        with zipfile.ZipFile(zf) as z:
            k = next((n for n in z.namelist()
                      if n.endswith("map-overlay.kml")), None)
            if not k:
                return None
            root = ET.fromstring(z.read(k))
            for el in root.iter():
                if el.tag.endswith("coordinates") and el.text:
                    pts = [tuple(map(float, c.split(",")[:2]))
                           for c in el.text.split()]
                    if len(pts) >= 3:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:                                   # noqa: BLE001
        return None
    return None


def overlap_pct(a, b) -> float:
    """b(결측 bbox) 중 a(granule)와 겹치는 넓이 비율(%)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return (ix * iy) / area_b * 100 if area_b > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--basin", action="append")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gpt-c", default="6G")
    ap.add_argument("--min-overlap", type=float, default=5.0,
                    help="granule이 결측 bbox의 이 %% 미만을 덮으면 건너뛴다")
    args = ap.parse_args()

    if not DEM.exists():
        raise SystemExit(f"DEM 없음: {DEM}")
    boxes = json.loads(BOXES.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    # granule 풋프린트를 한 번만 읽는다
    fps = {}
    for z in GRD.glob("*.zip"):
        m = DATE_RE.search(z.name)
        if m:
            fps[z] = (m.group(1), footprint(z))

    jobs = []
    for b, byd in boxes.items():
        if args.basin and b not in args.basin:
            continue
        for date, info in byd.items():
            vb = tuple(info["bounds_4326"])
            for z, (d, fp) in fps.items():
                if d != date or fp is None:
                    continue
                ov = overlap_pct(fp, vb)
                if ov < args.min_overlap:
                    continue
                jobs.append((b, date, ov, z, info))

    jobs.sort(key=lambda j: (j[0], j[1], -j[2]))
    print(f"결측 bbox {sum(len(v) for v in boxes.values())}건 → "
          f"재처리 작업 **{len(jobs)}건**\n")
    print(f"{'유역':<10}{'날짜':<10}{'덮음%':>7}{'결측km²':>9}"
          f"{'bbox km²':>10}   granule")
    print("-" * 72)
    for b, date, ov, z, info in jobs:
        print(f"{b:<10}{date:<10}{ov:>6.0f}%{info['void_km2']:>9.1f}"
              f"{info['bbox_km2']:>10.0f}   ...{z.stem[-9:]}")
    if args.dry_run:
        raise SystemExit("\n--dry-run: 처리하지 않았습니다.")

    print()
    for i, (b, date, ov, z, info) in enumerate(jobs, 1):
        tag = f"_void_{b}"
        out_tif = OUT / f"{z.stem}_rtc_db{tag}.tif"
        if out_tif.exists():
            print(f"[{i}/{len(jobs)}] 이미 있음 — {out_tif.name}", flush=True)
            continue
        t0 = time.time()
        tmp = Path(tempfile.mkdtemp(prefix="void_"))
        try:
            local = tmp / z.name
            shutil.copy2(z, local)
            g = build_grd_rtc_graph(
                local, OUT, polarization="VH",
                external_dem_file=DEM.resolve(),
                external_dem_nodata=-32768.0,
                # COP30은 이미 타원체고 — EGM 보정을 걸면 이중 적용된다
                external_dem_apply_egm=False,
                aoi_wkt=info["wkt_4326"],       # ← 결측 bbox만 자른다
                out_tag=tag)
            g.run(gpt_options=["-q", "8", "-c", args.gpt_c])
            print(f"[{i}/{len(jobs)}] {time.time()-t0:>5.0f}s  "
                  f"{b} {date}  {out_tif.name[-28:]}", flush=True)
        except Exception as e:                          # noqa: BLE001
            print(f"[{i}/{len(jobs)}] 실패 {b} {date}: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n산출 → {OUT}")
    print("다음: 모자이크를 **-srcnodata 0** 으로 다시 만들어 패치를 얹는다.")


if __name__ == "__main__":
    main()
