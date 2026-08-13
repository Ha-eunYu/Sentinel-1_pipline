# -*- coding: utf-8 -*-
"""담수호 대표점을 JSON으로 뽑는다 — STAC 검색 쪽에서 쓰려고.

왜 나눴나
--------
STAC 검색은 `s1_pipeline` 환경에서 도는데 거기엔 `pyogrio`·`geopandas`가 없다.
좌표만 있으면 되는 일이라, 지오 의존이 있는 이쪽(`sar-gee`)에서 미리 뽑아
파일로 넘긴다.

⚠ 대표점은 반드시 `representative_point()`
    수지상 담수호는 **중심(centroid)이 물길 사이 육지에 떨어진다.** 옥정호를
    기억으로 찍었다가 324 m 벗어나 "제약에 없음"이 나온 적이 있다.

실행
----
    conda run -n sar-gee python export_reservoir_points.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyogrio

from s1.core.paths import PROJECT_DIR

# gee/ 는 저장소의 형제 폴더다. 드라이브 문자를 박지 않고 루트 기준으로 찾는다.
GEE = PROJECT_DIR.parent / "gee" / "Korea_WaterDetection_2025_2026"
LAKES = GEE.parent / "V-world_수자원" / "국가기본도_호소" / "TN_LKMH.shp"

# gee/ 는 별도 저장소라 패키지 import가 안 된다. 그 폴더만 경로에 추가한다.
sys.path.insert(0, str(GEE))
from reservoir_series import DEFAULT_LAKES, ORBIT        # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", nargs="+", default=DEFAULT_LAKES)
    ap.add_argument("--out", type=Path, default=Path("reservoir_points.json"))
    args = ap.parse_args()

    g = pyogrio.read_dataframe(LAKES)
    g["nm"] = g["LKMH_NM"].astype(str).str.strip()
    g["km2"] = g.to_crs(5179).area / 1e6
    g = g.to_crs(4326)

    lakes = {}
    for n in args.lake:
        sel = g[g["nm"] == n].sort_values("km2", ascending=False)
        if sel.empty:
            print(f"  ⚠ '{n}' 없음")
            continue
        r = sel.iloc[0]
        p = r.geometry.representative_point()
        lakes[n] = {"lon": round(p.x, 6), "lat": round(p.y, 6),
                    "km2": round(float(r["km2"]), 2)}

    # **관측일 목록도 같이 넘긴다.** 검색 쪽에서 `reservoir_series`를 import 하면
    # geopandas 때문에 죽는다(`s1_pipeline`에 없다). 환경 간 import 를 없앤다.
    out = {"lakes": lakes, "orbit": ORBIT}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"저수지 {len(lakes)}곳 · 관측일 {len(ORBIT)}개 → {args.out}\n")
    for n, v in lakes.items():
        print(f"  {n:<8}({v['lon']:.4f}, {v['lat']:.4f})  만수 {v['km2']:>6.2f} km²")


if __name__ == "__main__":
    main()
