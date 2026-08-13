# -*- coding: utf-8 -*-
"""저수지 시계열용 VH RTC — **granule마다 덮는 댐만 잘라서** 처리한다.

왜 전 granule 이 아닌가
-----------------------
2026-07 로컬 GRD 15장이 VH RTC 미처리다(`rtc_grd_frost`는 **VV**라 못 쓴다).
이 날짜들은 **5대강 유역 분석에 안 쓰인다** — 유역은 4개 고정 날짜만 쓴다.
저수지 시계열이 필요로 하는 것은 **담수호 폴리곤 + 800 m 버퍼** 안의 dB뿐이다.

전 granule 은 장당 30~60분이지만, 댐 창으로 자르면 장당 2~5분이다(섬진강·낙동강
결측 창 실측). 같은 결과를 10~20배 빨리 얻는다.

어떻게 창을 잡나
----------------
granule 풋프린트(KML) 안에 든 댐만 추려 **한 상자로 감싼다**. 댐이 스와스를 따라
길게 늘어서면 상자가 커지므로, `--max-deg`보다 넓어지면 **경도 기준으로 쪼갠다**.

⚠ 창은 댐 + 버퍼를 반드시 덮어야 한다
    `reservoir_series.BUFFER_M`(800 m)까지 임계 산정에 쓰인다. 그래서 여유를
    0.05°(약 5.5 km) 준다. 이보다 줄이면 임계가 흔들린다.

⚠ 부분 겹침 granule 은 넣지 않는다
    `Subset`의 geoRegion 이 원본 밖으로 크게 벗어나면 죽는다. 풋프린트 안에 든
    댐만 대상으로 삼으므로 이 문제는 구조적으로 안 생긴다.

실행
----
    conda run -n s1_snappy python rtc_reservoir_windows.py --dry-run
    conda run -n s1_snappy python rtc_reservoir_windows.py --date 20260713
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
from rtc_basin_extdem import record_window

GRD = Path("downloads/sentinel1_grd")
OUT = Path("downloads/rtc_reservoir")
DEM = Path("downloads/dem_basin/korea_cop30.tif")
POINTS = Path("reservoir_points.json")
DATE_RE = re.compile(r"_(\d{8})T")
PAD = 0.05                      # 댐 둘레 여유(도) — 800 m 버퍼를 덮고도 남는다


def footprint(zf: Path):
    """granule 풋프린트 꼭짓점 목록. `s1_snappy`에 shapely가 없어 좌표로 다룬다."""
    try:
        with zipfile.ZipFile(zf) as z:
            k = next((n for n in z.namelist()
                      if n.endswith("map-overlay.kml")), None)
            if not k:
                return None
            for el in ET.fromstring(z.read(k)).iter():
                if el.tag.endswith("coordinates") and el.text:
                    pts = [tuple(map(float, c.split(",")[:2]))
                           for c in el.text.split()]
                    if len(pts) >= 3:
                        return pts
    except Exception:                                       # noqa: BLE001
        return None
    return None


def inside(pts, x: float, y: float) -> bool:
    """점이 다각형 안인가 — 광선 교차법.

    풋프린트는 볼록한 사각형에 가깝지만 스와스가 기울어져 있어 **경계상자로
    판정하면 과다 선별**된다(실측상 bbox 8장 vs footprint 2장). 그래서 실제
    다각형으로 본다.
    """
    n, ok = len(pts), False
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                ok = not ok
    return ok


def windows_for(hits, max_deg: float):
    """댐 목록을 상자로 감싼다. 너무 넓으면 경도로 쪼갠다."""
    xs = sorted(hits, key=lambda h: h[1])
    groups, cur = [], [xs[0]]
    for h in xs[1:]:
        if h[1] - cur[0][1] > max_deg:
            groups.append(cur)
            cur = [h]
        else:
            cur.append(h)
    groups.append(cur)

    out = []
    for g in groups:
        b = (min(h[1] for h in g) - PAD, min(h[2] for h in g) - PAD,
             max(h[1] for h in g) + PAD, max(h[2] for h in g) + PAD)
        out.append((b, [h[0] for h in g]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", action="append",
                    help="YYYYMMDD. 생략하면 VH 미처리 날짜 전부")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gpt-c", default="6G")
    ap.add_argument("--max-deg", type=float, default=1.2,
                    help="창의 경도 폭 상한(도). 넘으면 쪼갠다")
    args = ap.parse_args()

    if not DEM.exists():
        raise SystemExit(f"DEM 없음: {DEM}\n"
                         f"    python make_basin_dem.py "
                         f"--bounds 125.4,33.8,129.9,38.7 --name korea")
    raw = json.loads(POINTS.read_text(encoding="utf-8"))
    lakes = raw["lakes"]

    vh = Path("downloads/rtc_grd_frost_vh")
    done = {p.name.split("_rtc")[0] for p in vh.glob("*.tif")}

    jobs = []
    for z in sorted(GRD.glob("*.zip")):
        m = DATE_RE.search(z.name)
        if not m:
            continue
        d = m.group(1)
        if args.date and d not in args.date:
            continue
        if z.stem in done:                       # 이미 VH RTC 가 있다
            continue
        fp = footprint(z)
        if fp is None:
            continue
        hits = [(n, v["lon"], v["lat"]) for n, v in lakes.items()
                if inside(fp, v["lon"], v["lat"])]
        if not hits:
            continue
        for bnd, names in windows_for(hits, args.max_deg):
            jobs.append((d, z, bnd, names))

    print(f"VH 미처리 중 **댐을 덮는 작업 {len(jobs)}건**\n")
    print(f"{'날짜':<10}{'창(경위도)':<38}{'댐':<30}granule")
    print("-" * 100)
    for d, z, b, names in jobs:
        print(f"{d:<10}{f'{b[0]:.2f}~{b[2]:.2f}E {b[1]:.2f}~{b[3]:.2f}N':<38}"
              f"{','.join(names)[:28]:<30}...{z.stem[-9:]}")
    if args.dry_run:
        raise SystemExit("\n--dry-run: 처리하지 않았습니다.")

    OUT.mkdir(parents=True, exist_ok=True)
    for i, (d, z, b, names) in enumerate(jobs, 1):
        tag = f"_res_w{b[0]:.2f}_{b[1]:.2f}".replace(".", "p")
        out_tif = OUT / f"{z.stem}_rtc_db{tag}.tif"
        if out_tif.exists() and out_tif.stat().st_size > 1e6:
            print(f"[{i}/{len(jobs)}] 이미 있음", flush=True)
            record_window(OUT, out_tif.name, "reservoir", d, b)
            continue
        t0 = time.time()
        tmp = Path(tempfile.mkdtemp(prefix="res_"))
        try:
            local = tmp / z.name
            shutil.copy2(z, local)
            wkt = (f"POLYGON(({b[0]} {b[1]},{b[2]} {b[1]},{b[2]} {b[3]},"
                   f"{b[0]} {b[3]},{b[0]} {b[1]}))")
            g = build_grd_rtc_graph(
                local, OUT, polarization="VH",
                external_dem_file=DEM.resolve(),
                external_dem_nodata=-32768.0,
                external_dem_apply_egm=False,    # COP30은 타원체고다
                aoi_wkt=wkt, out_tag=tag)
            g.run(gpt_options=["-q", "8", "-c", args.gpt_c])
            record_window(OUT, out_tif.name, "reservoir", d, b)
            print(f"[{i}/{len(jobs)}] {time.time()-t0:>5.0f}s  {d}  "
                  f"{','.join(names)[:30]}", flush=True)
        except Exception as e:                              # noqa: BLE001
            print(f"[{i}/{len(jobs)}] 실패 {d}: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n산출 → {OUT}")
    print("다음: rebuild_mosaic_extdem.py 로 그 날짜 모자이크를 만들고, "
          "reservoir_series.ORBIT 에 날짜를 더할 것")


if __name__ == "__main__":
    main()
