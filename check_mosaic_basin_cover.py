# -*- coding: utf-8 -*-
"""모자이크가 대상 댐유역을 실제로 덮는지 — **유효화소 기준**으로 잰다.

왜
--
경계상자가 유역을 감싼다고 해서 관측된 것이 아니다. 스와스 가장자리·결측·
SNAP이 남긴 0이 유역 안에 들어와도 bbox는 그대로 100%로 보인다. 그래서
`watershed_pairs.cover()`와 **같은 규칙**으로 센다: 모자이크 1밴드를 유역
격자에 얹어 `isfinite(a) & (a != 0)`인 화소의 비율.

작은 유역(성덕 41.5 km², 밀양 94.1 km²)이 있어 200 m 대신 **50 m** 격자로
잰다(쌍 고르기용 200 m보다 촘촘하다). 유역 폴리곤·필드명·좌표계는 gee 쪽과
동일: `전댐유역.shp` / `damname` / EPSG:5179.

실행:
    conda run -n sar-gee python check_mosaic_basin_cover.py
    conda run -n sar-gee python check_mosaic_basin_cover.py --date 20250806 --date 20260802 \
        --dams 안동 임하 밀양 영천 성덕 운문 섬진강 평림
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyogrio
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

VRT_DIR = Path(r"F:\06_SAR_system\S1\downloads\water_otsu\vrt_vh")
DAMS_SHP = Path(r"F:\06_SAR_system\gee\전댐유역\전댐유역.shp")
NAME_FIELD = "damname"
TARGET_CRS = 5179
RES = 50.0

DEFAULT_DATES = ["20250806", "20260802"]
DEFAULT_DAMS = ["안동", "임하", "밀양", "영천", "성덕", "운문", "섬진강", "평림"]


def grid_of(geom, res: float = RES) -> dict:
    w, s, e, n = geom.bounds
    w, s = np.floor(w / res) * res, np.floor(s / res) * res
    e, n = np.ceil(e / res) * res, np.ceil(n / res) * res
    return {"crs": rasterio.crs.CRS.from_epsg(TARGET_CRS),
            "transform": from_origin(w, n, res, res),
            "width": int(round((e - w) / res)),
            "height": int(round((n - s) / res))}


def cover(vrt: Path, prof: dict, mask: np.ndarray) -> float:
    """유역 폴리곤 안 유효화소 비율. 모자이크가 없으면 0."""
    if not vrt.exists():
        return float("nan")
    with rasterio.open(vrt) as s0, \
            WarpedVRT(s0, crs=prof["crs"], transform=prof["transform"],
                      width=prof["width"], height=prof["height"],
                      resampling=Resampling.nearest) as v:
        a = v.read(1).astype("float32")
    ok = mask & np.isfinite(a) & (a != 0)
    return float(ok.sum() / max(1, mask.sum()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", action="append", help=f"YYYYMMDD (기본 {DEFAULT_DATES})")
    ap.add_argument("--dams", nargs="*", default=None, help=f"댐 이름 (기본 {DEFAULT_DAMS})")
    args = ap.parse_args()

    dates = args.date or DEFAULT_DATES
    dams = args.dams or DEFAULT_DAMS

    gdf = pyogrio.read_dataframe(DAMS_SHP).to_crs(TARGET_CRS)
    have = set(gdf[NAME_FIELD])
    unknown = [d for d in dams if d not in have]
    if unknown:
        raise SystemExit(f"shp에 없는 이름: {unknown}\n보유: {sorted(have)}")

    vrts = {d: VRT_DIR / f"mosaic_{d}_vh.vrt" for d in dates}
    for d, p in vrts.items():
        n = p.read_text(encoding="utf-8", errors="replace").count("<SourceFilename") \
            if p.exists() else 0
        print(f"■ mosaic_{d}_vh.vrt  {'있음' if p.exists() else '**없음**'}  원본 {n}장")
    print()

    head = "유역".ljust(8) + "km2".rjust(9) + "".join(f"{d:>12}" for d in dates)
    print(head)
    print("-" * len(head.encode("utf-8")) if False else "-" * (8 + 9 + 12 * len(dates)))

    rows = []
    for name in dams:
        geom = gdf.loc[gdf[NAME_FIELD] == name, "geometry"].union_all()
        prof = grid_of(geom)
        mask = rasterize([(geom, 1)], out_shape=(prof["height"], prof["width"]),
                         transform=prof["transform"], dtype="uint8").astype(bool)
        km2 = geom.area / 1e6
        cs = [cover(vrts[d], prof, mask) for d in dates]
        rows.append((name, km2, cs))
        cells = "".join(("       없음" if np.isnan(c) else f"{c * 100:11.1f}%") for c in cs)
        print(f"{name:<8}{km2:9.1f}{cells}")

    print()
    for i, d in enumerate(dates):
        got = [(n, c[i]) for n, _, c in rows if not np.isnan(c[i])]
        if not got:
            print(f"⚠ {d}: 모자이크가 없어 **측정 불가**")
            continue
        bad = [(n, c) for n, c in got if c < 0.999]
        if bad:
            print(f"⚠ {d}: 100% 미만 유역 {len(bad)}개 — "
                  + ", ".join(f"{n} {c * 100:.1f}%" for n, c in bad))
        else:
            print(f"✔ {d}: 대상 유역 전부 100%")


if __name__ == "__main__":
    main()
