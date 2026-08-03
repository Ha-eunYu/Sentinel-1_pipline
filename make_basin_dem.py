# -*- coding: utf-8 -*-
"""유역별 external DEM(GeoTIFF)을 `D:\\00_COP30\\COP30_hh`에서 구워 낸다.

왜 external DEM인가
-------------------
SNAP에 `demName="Copernicus 30m Global DEM"`을 주면 자동 다운로드 캐시를 쓰는데,
**하구 수역을 무효로 해석해 결측을 만든다**(영산강 제약의 20.2%). 같은 COP30
값이라도 **일반 GeoTIFF로 물리면 결측이 0.00%**가 된다(2026-08-03 실측).

왜 VRT가 아니라 GeoTIFF인가
---------------------------
**SNAP이 VRT를 external DEM으로 못 읽는다.** `cop30_korea.vrt`로 시도한 패치
20건이 전부 `Graph execution failed`로 죽었다. GeoTIFF로 구우면 된다.

⚠ 수직 기준
    COP30은 **타원체고**다. `externalDEMApplyEGM=False`로 줘야 한다.
    `True`(기본값)로 주면 지오이드 보정이 이중 적용돼 한국에서 약 25 m 어긋난다.

실행
----
    conda run -n sar-gee python make_basin_dem.py
    conda run -n sar-gee python make_basin_dem.py --basin yeongsan --margin 0.5
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path

COP = Path(r"D:\00_COP30\COP30_hh")
REF = Path(r"F:\06_SAR_system\gee\Korea_WaterDetection_2025_2026\reference")
OUT = Path(r"F:\06_SAR_system\S1\downloads\dem_basin")
GDAL = Path(r"F:\envs\sar-gee\Library\bin")
BASINS = ["han", "nakdong", "geum", "seomjin", "yeongsan"]


def aoi_bounds(basin: str):
    fp = REF / f"bbsn_{basin}.geojson"
    if not fp.exists():
        return None
    d = json.loads(fp.read_text(encoding="utf-8"))
    g = d["geometry"] if d.get("type") == "Feature" else d["features"][0]["geometry"]

    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)

    def geom(x):
        # `make_valid()` 뒤에 GeometryCollection이 섞일 수 있다 —
        # 그때는 `coordinates`가 없고 `geometries`가 있다.
        if "coordinates" in x:
            walk(x["coordinates"])
        elif "geometries" in x:
            for y in x["geometries"]:
                geom(y)

    geom(g)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def tiles_for(w, s, e, n):
    """1°×1° COP30 타일 파일 목록. 이름 규칙은 N{lat}_00_E{lon}_00 이다."""
    out = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            hits = list(COP.glob(
                f"Copernicus_DSM_*_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"))
            if hits:
                out.append(hits[0])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--basin", action="append", choices=BASINS)
    # DEM 창은 `rtc_basin_extdem.py`의 **자를 창**(AOI + 0.15°)을 덮으면 된다.
    # 0.6이면 사방 0.45° 여유라 충분하다 — 영산강 기준 AOI 동쪽 끝에서 DEM
    # 경계까지 55 km다.
    #
    # ⚠ `Subset` 산출 경계상자는 자를 창보다 커지지만(스와스 기울기), 그
    #   **넘침까지 DEM이 덮을 필요는 없다**. 자를 창 밖이고 AOI 밖이라 분석에
    #   안 쓴다. 2026-08-03에 이걸 착각해 0.85°로 다시 구웠다 — 헛일이었다.
    ap.add_argument("--margin", type=float, default=0.6,
                    help="AOI 밖 여유(도). SAR 자를 창을 덮으면 된다")
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    if not COP.exists():
        raise SystemExit(f"COP30 타일 폴더 없음: {COP}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"COP30 원본 {COP}\n")
    print(f"{'유역':<10}{'AOI 범위':<34}{'타일':>5}{'산출 MB':>9}")
    print("-" * 62)

    for b in args.basin or BASINS:
        bnd = aoi_bounds(b)
        if bnd is None:
            print(f"{b:<10}   AOI 없음")
            continue
        w, s, e, n = bnd
        w, s = w - args.margin, s - args.margin
        e, n = e + args.margin, n + args.margin
        ts = tiles_for(w, s, e, n)
        if not ts:
            print(f"{b:<10}   타일 없음")
            continue

        out = args.out_dir / f"{b}_cop30.tif"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="ascii") as f:
            f.write("\n".join(str(t) for t in ts))
            lst = f.name
        vrt = args.out_dir / f"_{b}.vrt"
        subprocess.run([str(GDAL / "gdalbuildvrt"), "-overwrite",
                        "-input_file_list", lst, str(vrt)],
                       check=True, capture_output=True)
        # **GeoTIFF로 굽는다** — SNAP이 VRT를 external DEM으로 못 읽는다
        subprocess.run([str(GDAL / "gdal_translate"), "-of", "GTiff",
                        "-projwin", str(w), str(n), str(e), str(s),
                        "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES",
                        "-a_nodata", "-32768",
                        str(vrt), str(out)],
                       check=True, capture_output=True)
        vrt.unlink(missing_ok=True)
        Path(lst).unlink(missing_ok=True)
        print(f"{b:<10}{f'{w:.2f}~{e:.2f}E {s:.2f}~{n:.2f}N':<34}"
              f"{len(ts):>5}{out.stat().st_size/1e6:>9.0f}")

    print(f"\n산출 → {args.out_dir}")
    print("사용: build_grd_rtc_graph(external_dem_file=..., "
          "external_dem_apply_egm=False)")


if __name__ == "__main__":
    main()
