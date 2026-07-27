# -*- coding: utf-8 -*-
"""미처리 202607 GRD 씬의 footprint(zip manifest)를 읽어 북한(NK.geojson) 겹침%를
계산, NK 우선 처리 목록을 만든다. 추출 없이 zip에서 manifest.safe만 읽어 빠르다.
실행: conda run -n s1_pipeline python scratch_nk_scenes.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
import zipfile
from pathlib import Path

from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_geom(path: str):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    t = d.get("type")
    if t == "FeatureCollection":
        return unary_union([shape(f["geometry"]) for f in d["features"] if f.get("geometry")])
    if t == "Feature":
        return shape(d["geometry"])
    return shape(d)


nk = load_geom("geojson/NK.geojson")


def footprint(zippath: str):
    with zipfile.ZipFile(zippath) as zf:
        mns = [n for n in zf.namelist() if n.endswith("manifest.safe")]
        if not mns:
            return None
        txt = zf.read(mns[0]).decode("utf-8", "replace")
    m = re.search(r"<gml:coordinates>([^<]+)</gml:coordinates>", txt)
    if not m:
        return None
    pts = []
    for pair in m.group(1).split():
        a, b = pair.split(",")
        pts.append((float(b), float(a)))  # (lon, lat)
    return Polygon(pts)


rows = []
for z in sorted(glob.glob("downloads/sentinel1_grd/*_COG.zip")):
    base = Path(z).stem
    md = re.search(r"_(\d{8})T\d{6}_", base)
    dt = md.group(1) if md else ""
    if not dt.startswith("202607"):
        continue
    if Path(f"downloads/rtc_grd_frost/{base}_rtc_db.tif").exists():
        continue  # 이미 처리됨
    fp = footprint(z)
    if fp is None:
        print("no footprint:", base)
        continue
    inter = (fp.intersection(nk).area / fp.area * 100) if fp.area else 0.0
    rows.append((inter, dt, base, fp.bounds))

rows.sort(key=lambda r: (-r[0], r[1]))
print(f"\n미처리 202607 씬 {len(rows)}장 — NK 겹침% 내림차순:")
nk_list = []
for inter, dt, base, b in rows:
    tag = "★NK" if inter > 5 else "   "
    if inter > 5:
        nk_list.append(base)
    print(f"  {tag} NK{inter:5.1f}%  {dt}  lat{b[1]:5.1f}~{b[3]:5.1f}  {base[-28:]}")
print(f"\nNK(>5%) 씬 {len(nk_list)}장 (우선 처리 대상):")
for b in nk_list:
    print(" ", b)
Path("downloads/_nk_priority.txt").write_text("\n".join(nk_list), encoding="utf-8")
print("-> downloads/_nk_priority.txt 저장")
