# -*- coding: utf-8 -*-
"""유역별 external DEM으로 RTC — **SAR을 DEM 창으로 잘라서** 처리한다.

왜
--
SNAP에 `demName="Copernicus 30m Global DEM"`(자동 캐시)을 주면 **하구 수역을
무효로 해석**해 결측을 만든다(영산강 제약의 20.2%). 같은 COP30 값이라도
`D:\\00_COP30\\COP30_hh`에서 구운 **GeoTIFF를 external로 물리면 결측이 0.00%**다
(2026-08-03 실측: 원본·0치환·NGII 세 판 모두 동일).

왜 SAR을 자르는가
-----------------
external DEM은 유역 범위만 덮는다. 전 granule을 처리하면 DEM 창 밖이 무효가
되고 시간만 든다. **`aoi_wkt`로 SAR을 Subset**하면 연산량이 준다.

⚠ 자를 창과 DEM 창은 **같으면 안 된다**
    `Subset`은 **레이더 기하**에서 자른다. 준 경위도 상자를 원본 격자(거리·방위)로
    옮겨 그 범위를 떼는데, **스와스가 기울어져 있어** 떼어 낸 조각의 지리적
    경계상자는 준 상자보다 **커진다**. 영산강 실측:

        준 창(=DEM 창)  125.83~127.70E  (1.87°)
        산출 경계상자    125.66~128.07E  (2.41°)  ← 0.54° 넘침

    DEM 창을 그대로 `aoi_wkt`에 주면 절감이 30%(944M→661M 화소)에 그친다.
    그래서 자를 창을 DEM 창과 갈라 좁게 준다(`--clip-margin` 0.15°).

    **넘침 영역은 DEM이 안 덮어도 된다.** 자를 창 밖이고 AOI 밖이라 분석에
    안 쓴다. 거기가 무효로 남는 건 정상이다 — DEM이 덮어야 하는 건 **자를 창**
    이지 산출 경계상자가 아니다. (2026-08-03에 이 검사를 산출 경계상자 기준으로
    잘못 걸어 두고 5대강 DEM을 0.85°로 다시 구웠다. 불필요한 작업이었다.)

    DEM 여유 0.6° − 자를 여유 0.15° = **사방 0.45°**. 영산강 기준 AOI 동쪽 끝
    에서 DEM 경계까지 55 km라 보간 가장자리 효과가 닿지 않는다.

⚠ 두 가지
    · **VRT는 external DEM으로 못 읽는다** — `cop30_korea.vrt`로 시도한 패치
      20건이 전부 `Graph execution failed`였다. GeoTIFF로 구울 것.
    · **`externalDEMApplyEGM=False`** — COP30은 타원체고다. `True`면 지오이드
      보정이 이중 적용돼 약 25 m 어긋난다.

실행
----
    conda run -n s1_snappy python rtc_basin_extdem.py --basin yeongsan
    conda run -n s1_snappy python rtc_basin_extdem.py --dry-run
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

import rasterio

from make_basin_dem import aoi_bounds
from prepro_grd_gpt import build_grd_rtc_graph

GRD = Path("downloads/sentinel1_grd")
DEM_DIR = Path("downloads/dem_basin")
OUT = Path("downloads/rtc_extdem")
DATE_RE = re.compile(r"_(\d{8})T")

# 유역별 1:1 관측일 쌍 — `Korea_WaterDetection_2025_2026/local_change.py`와 동일
PAIRS = {"yeongsan": ("20250718", "20260720"),
         "seomjin": ("20250718", "20260720"),
         "geum": ("20250718", "20260720"),
         "nakdong": ("20250725", "20260715"),
         "han": ("20250725", "20260715")}


# `Subset`이 레이더 기하에서 자르는 탓에 산출 경계상자가 준 창보다 커지는 양
# (**한쪽 변당**). 영산강 38C3 실측은 서 0.17° 동 0.37° 남 0.26° 북 0.00°였다.
# 넘침은 창 크기가 아니라 스와스 기울기에서 오므로 상수로 둔다.
# 보고용일 뿐이다 — 이 영역은 무효로 남아도 무해하다(모듈 주석 참고).
SPILL = (0.60, 0.35)                                        # (경도, 위도)

# DEM이 자를 창 밖으로 더 있어야 하는 최소량. DEM 보간이 가장자리에서 흔들리는
# 것만 피하면 되므로 크게 잡을 이유가 없다. 실제 여유는 0.45°다.
DEM_PAD = 0.10


def windows(basin: str, clip_margin: float):
    """(DEM 경로, DEM 창, SAR을 자를 창, 예상 산출 창).

    셋을 갈라 놓는 이유는 모듈 주석 참고 — `Subset`은 준 창보다 넓게 떼어 낸다.
    """
    p = DEM_DIR / f"{basin}_cop30.tif"
    if not p.exists():
        return None, None, None, None
    with rasterio.open(p) as s:
        dem = tuple(s.bounds)            # COP30은 EPSG:4326이라 그대로 쓴다

    a = aoi_bounds(basin)
    if a is None:
        return p, dem, dem, dem          # AOI를 못 읽으면 예전처럼 DEM 창으로
    m = clip_margin
    clip = (a[0] - m, a[1] - m, a[2] + m, a[3] + m)
    sx, sy = SPILL
    spill = (clip[0] - sx, clip[1] - sy, clip[2] + sx, clip[3] + sy)
    return p, dem, clip, spill


def wkt_of(b) -> str:
    return (f"POLYGON(({b[0]} {b[1]},{b[2]} {b[1]},"
            f"{b[2]} {b[3]},{b[0]} {b[3]},{b[0]} {b[1]}))")


def covers(outer, inner) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def footprint(zf: Path):
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


def overlap(a, b) -> float:
    """b 안에서 a와 겹치는 넓이 비율(%)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    ab = (b[2] - b[0]) * (b[3] - b[1])
    return ix * iy / ab * 100 if ab > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--basin", action="append", choices=list(PAIRS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gpt-c", default="6G")
    ap.add_argument("--min-overlap", type=float, default=3.0)
    ap.add_argument("--clip-margin", type=float, default=0.15,
                    help="SAR을 자를 창의 AOI 밖 여유(도). DEM 창과 다르다 — "
                         "모듈 주석의 '넘침' 설명 참고")
    ap.add_argument("--window", default="",
                    help="자를 창을 직접 준다 'w,s,e,n'(경위도). 결측이 유역 "
                         "AOI의 한 귀퉁이에만 있을 때 쓴다 — "
                         "`gee/Korea_WaterDetection_2025_2026/void_clip_windows.json` 참고")
    ap.add_argument("--only", default="",
                    help="쉼표로 구분한 씬 ID(4자리). 병렬 실행 시 작업을 나눈다")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    fps = {}
    for z in GRD.glob("*.zip"):
        m = DATE_RE.search(z.name)
        if m:
            fps[z] = (m.group(1), footprint(z))

    override = None
    if args.window:
        v = [float(x) for x in args.window.split(",")]
        if len(v) != 4:
            raise SystemExit("--window 는 'w,s,e,n' 네 값이어야 합니다")
        override = tuple(v)

    jobs = []
    for b in args.basin or list(PAIRS):
        dem, dw, clip, spill = windows(b, args.clip_margin)
        if dem is None:
            print(f"{b}: DEM 없음 — make_basin_dem.py 먼저 실행")
            continue
        if override is not None:
            clip = override
            sx, sy = SPILL
            spill = (clip[0] - sx, clip[1] - sy, clip[2] + sx, clip[3] + sy)
            print(f"   (자를 창을 --window 로 직접 지정했다)")

        def deg(x):
            return f"{x[0]:.2f}~{x[2]:.2f}E {x[1]:.2f}~{x[3]:.2f}N"

        print(f"■ {b}")
        print(f"   SAR 자를 창  {deg(clip)}   ({clip[2]-clip[0]:.2f}°"
              f" × {clip[3]-clip[1]:.2f}°)")
        print(f"   DEM 창       {deg(dw)}   ({dw[2]-dw[0]:.2f}°"
              f" × {dw[3]-dw[1]:.2f}°)")
        p = DEM_PAD
        need = (clip[0] - p, clip[1] - p, clip[2] + p, clip[3] + p)
        if covers(dw, need):
            pad = min(clip[0] - dw[0], dw[2] - clip[2],
                      clip[1] - dw[1], dw[3] - clip[3])
            print(f"   DEM이 자를 창을 사방 {pad:.2f}° 여유로 덮는다 ✔")
        else:
            short = max(need[0] - dw[0], dw[2] - need[2],
                        need[1] - dw[1], dw[3] - need[3], key=abs)
            print(f"   ⚠ **DEM이 자를 창을 못 덮는다**(부족 {abs(short):.2f}°)"
                  f" — make_basin_dem.py --basin {b} --margin "
                  f"{args.clip_margin + p + 0.2:.2f}")
        print(f"   (산출 경계상자는 {deg(spill)}까지 커진다. 넘침은 자를 창"
              f" 밖이라 무효로 남아도 무해하다)")
        print()

        for date in PAIRS[b]:
            for z, (d, fp) in fps.items():
                if d != date or fp is None:
                    continue
                ov = overlap(fp, clip)
                if ov < args.min_overlap:
                    continue
                jobs.append((b, date, ov, z, dem, wkt_of(clip)))

    if args.only:
        want = {s.strip().upper() for s in args.only.split(",") if s.strip()}
        jobs = [j for j in jobs
                if any(f"_{s}" in j[3].name.upper() for s in want)]
    jobs.sort(key=lambda j: (j[0], j[1], -j[2]))
    print(f"작업 **{len(jobs)}건**\n")
    print(f"{'유역':<10}{'날짜':<10}{'자를창 덮음':>11}   granule")
    print("-" * 58)
    for b, date, ov, z, dem, _ in jobs:
        print(f"{b:<10}{date:<10}{ov:>10.0f}%   ...{z.stem[-9:]}")
    if args.dry_run:
        raise SystemExit("\n--dry-run: 처리하지 않았습니다.")

    print()
    for i, (b, date, ov, z, dem, wkt) in enumerate(jobs, 1):
        # 창을 직접 준 산출은 유역 전체판과 파일명이 겹치면 안 된다
        tag = f"_ext_{b}" if override is None else \
            f"_ext_{b}_w{override[0]:.2f}_{override[1]:.2f}".replace(".", "p")
        out_tif = OUT / f"{z.stem}_rtc_db{tag}.tif"
        if out_tif.exists() and out_tif.stat().st_size > 1e6:
            print(f"[{i}/{len(jobs)}] 이미 있음 — {out_tif.name[-30:]}", flush=True)
            continue
        t0 = time.time()
        tmp = Path(tempfile.mkdtemp(prefix="ext_"))
        try:
            local = tmp / z.name
            shutil.copy2(z, local)
            g = build_grd_rtc_graph(
                local, OUT, polarization="VH",
                external_dem_file=dem.resolve(),
                external_dem_nodata=-32768.0,
                external_dem_apply_egm=False,   # COP30은 타원체고다
                aoi_wkt=wkt,                    # ← SAR을 DEM 창으로 자른다
                out_tag=tag)
            g.run(gpt_options=["-q", "8", "-c", args.gpt_c])
            print(f"[{i}/{len(jobs)}] {time.time()-t0:>5.0f}s  {b} {date}  "
                  f"{out_tif.name[-30:]}", flush=True)
        except Exception as e:                          # noqa: BLE001
            print(f"[{i}/{len(jobs)}] 실패 {b} {date}: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n산출 → {OUT}")


if __name__ == "__main__":
    main()
