# -*- coding: utf-8 -*-
"""
특정 씬들만 **격리**해 수체 지도를 만들고, 그 수체 픽셀이 경계 폴리곤
(기본 Korea_Peninsula) 내부에 실제로 얼마나 들어가는지 point-in-polygon으로
검증한다. SCENE_FOOTPRINT_REAUDIT_KR.md 5절이 권고한 "소형/특정 궤도 단독
결과를 문서화하기 전 사전 검증" 단계를 표준화한 도구.

배경: 저장된 flood_water_*.tif가 여러 궤도가 섞인 합성본이면, 특정 소형 궤도
3씬(예: 7/16 저녁 003704의 D298·3191·4C7C)만의 기여를 그 파일로는 분리할 수
없다. 이 스크립트는 지정한 씬의 RTC dB(Refined Lee)만 모자이크해 격리 수체
지도를 만들고, 물 픽셀의 위경도를 경계 폴리곤과 대조한다.

의존성: rasterio + numpy 만 사용(shapely 불필요, point-in-polygon 자체 구현).

산출물:
  downloads/water_otsu/verify/flood_water_isolated_<tag>.tif   (0/1/255)

실행:
  conda run -n s1_snappy python verify_scene_footprint.py --tag 20260716_o003704_3scene \\
      --scenes downloads/etc/S1D_..._D298_COG_rtc_db.tif \\
               downloads/rtc_grd/S1D_..._3191_COG_rtc_db.tif \\
               downloads/rtc_grd/S1D_..._4C7C_COG_rtc_db.tif
  (--scenes 생략 시 7/16 저녁 3씬 D298·3191·4C7C 기본값)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

PROJECT_DIR = Path(__file__).resolve().parent
GEOJSON_DIR = PROJECT_DIR / "geojson"
OUT_DIR = PROJECT_DIR / "downloads" / "water_otsu" / "verify"

DB_THRESHOLD_DEFAULT = -16.0
NODATA_U8 = 255
CHUNK_ROWS = 512
M_PER_DEG = 111_320.0

# 기본 검증 대상: 7/16 21:16 UTC S1D 하강 궤도 003704의 3프레임
DEFAULT_SCENES = [
    PROJECT_DIR / "downloads" / "etc" /
    "S1D_IW_GRDH_1SDV_20260716T211600_20260716T211629_003704_006A0F_D298_COG_rtc_db.tif",
    PROJECT_DIR / "downloads" / "rtc_grd" /
    "S1D_IW_GRDH_1SDV_20260716T211629_20260716T211654_003704_006A0F_3191_COG_rtc_db.tif",
    PROJECT_DIR / "downloads" / "rtc_grd" /
    "S1D_IW_GRDH_1SDV_20260716T211654_20260716T211719_003704_006A0F_4C7C_COG_rtc_db.tif",
]


def load_exterior_rings(geojson_path: Path) -> list[np.ndarray]:
    """FeatureCollection/Feature/Geometry에서 모든 (Multi)Polygon 외곽 링을
    Nx2(lon,lat) 배열 목록으로 추출(구멍은 무시 — 해안선 검증엔 충분)."""
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in data["features"] if f.get("geometry")]
    elif data.get("type") == "Feature":
        geoms = [data["geometry"]]
    else:
        geoms = [data]
    rings: list[np.ndarray] = []
    for g in geoms:
        if g["type"] == "Polygon":
            rings.append(np.asarray(g["coordinates"][0], dtype="float64"))
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                rings.append(np.asarray(poly[0], dtype="float64"))
    return rings


def points_in_rings(lons: np.ndarray, lats: np.ndarray, rings: list[np.ndarray]) -> np.ndarray:
    """벡터화 ray-casting. 점이 어느 링에든 들어가면 True (even-odd, 링별 OR)."""
    inside = np.zeros(lons.shape, dtype=bool)
    for ring in rings:
        rx, ry = ring[:, 0], ring[:, 1]
        n = len(ring)
        j = n - 1
        acc = np.zeros(lons.shape, dtype=bool)
        for i in range(n):
            xi, yi, xj, yj = rx[i], ry[i], rx[j], ry[j]
            cond = ((yi > lats) != (yj > lats))
            # 교차하는 세로 위치에서의 x
            denom = (yj - yi)
            denom = np.where(denom == 0, 1e-12, denom)
            xints = (xj - xi) * (lats - yi) / denom + xi
            acc ^= cond & (lons < xints)
            j = i
        inside |= acc
    return inside


def build_vrt(scenes: list[Path], tag: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    vrt = OUT_DIR / f"mosaic_{tag}.vrt"
    missing = [s for s in scenes if not s.exists()]
    if missing:
        raise FileNotFoundError("다음 씬 RTC가 없습니다:\n  " +
                                "\n  ".join(str(m) for m in missing))
    cmd = ["gdalbuildvrt", "-srcnodata", "0", "-vrtnodata", "0", "-overwrite",
           str(vrt), *[str(s.resolve()) for s in scenes]]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return vrt


def main() -> None:
    ap = argparse.ArgumentParser(description="특정 씬 격리 수체 지도 + 경계 내부 비율 검증")
    ap.add_argument("--scenes", nargs="+", type=Path, default=DEFAULT_SCENES)
    ap.add_argument("--tag", default="20260716_o003704_3scene")
    ap.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    ap.add_argument("--boundary", type=Path, default=GEOJSON_DIR / "Korea_Peninsula.geojson")
    ap.add_argument("--extra-boundaries", nargs="*", type=Path,
                    default=[GEOJSON_DIR / "South_Korea.geojson", GEOJSON_DIR / "NK.geojson"])
    ap.add_argument("--sample", type=int, default=20000, help="point-in-polygon 표본 픽셀 수")
    args = ap.parse_args()

    vrt = build_vrt(args.scenes, args.tag)
    out_tif = OUT_DIR / f"flood_water_isolated_{args.tag}.tif"

    # 경계 로드
    boundaries = {args.boundary.stem: load_exterior_rings(args.boundary)}
    for b in args.extra_boundaries:
        if b.exists():
            boundaries[b.stem] = load_exterior_rings(b)

    with rasterio.open(vrt) as src:
        res_x, res_y = abs(src.transform.a), abs(src.transform.e)
        top, left = src.bounds.top, src.bounds.left
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width, "count": 1,
            "dtype": "uint8", "crs": src.crs, "transform": src.transform,
            "nodata": NODATA_U8, "compress": "DEFLATE", "tiled": True, "bigtiff": "IF_SAFER",
        }
        base_area = (res_y * M_PER_DEG) * (res_x * M_PER_DEG)

        n_valid = n_water = 0
        water_area_km2 = 0.0
        w_lon_min = w_lat_min = 1e9
        w_lon_max = w_lat_max = -1e9
        sample_lons: list[np.ndarray] = []
        sample_lats: list[np.ndarray] = []

        with rasterio.open(out_tif, "w", **profile) as dst:
            for row0 in range(0, src.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, src.height - row0)
                win = Window(0, row0, src.width, nrows)
                db = src.read(1, window=win).astype("float32")
                valid = np.isfinite(db) & (db != 0)
                water = valid & (db < args.db)
                dst.write(np.where(valid, water.astype("uint8"), NODATA_U8), 1, window=win)

                n_valid += int(valid.sum())
                nw = int(water.sum())
                n_water += nw
                if nw:
                    rr, cc = np.nonzero(water)
                    lons = left + (cc + 0.5) * res_x
                    lats = top - (row0 + rr + 0.5) * res_y
                    water_area_km2 += float((base_area * np.cos(np.radians(lats))).sum() / 1e6)
                    w_lon_min, w_lon_max = min(w_lon_min, lons.min()), max(w_lon_max, lons.max())
                    w_lat_min, w_lat_max = min(w_lat_min, lats.min()), max(w_lat_max, lats.max())
                    sample_lons.append(lons)
                    sample_lats.append(lats)

    total_px = profile["height"] * profile["width"]
    print(f"격리 대상 {len(args.scenes)}씬 -> {out_tif.name}")
    print(f"격자 {profile['width']}x{profile['height']}px, 커버리지 {100*n_valid/total_px:.1f}%")
    print(f"수체(dB<{args.db}) {n_water:,}px = {water_area_km2:,.2f} km^2")
    if n_water == 0:
        print("수체 픽셀 없음.")
        return
    print(f"수체 픽셀 경위도 범위: lon {w_lon_min:.3f}~{w_lon_max:.3f}E, "
          f"lat {w_lat_min:.3f}~{w_lat_max:.3f}N")

    lons = np.concatenate(sample_lons)
    lats = np.concatenate(sample_lats)
    if lons.size > args.sample:
        idx = np.random.default_rng(0).choice(lons.size, args.sample, replace=False)
        lons, lats = lons[idx], lats[idx]
    print(f"\npoint-in-polygon (표본 {lons.size:,}개):")
    for name, rings in boundaries.items():
        frac = 100.0 * points_in_rings(lons, lats, rings).mean()
        print(f"  {name:20s} 내부 {frac:5.1f}%  (추정 육지내 수체 ≈ {water_area_km2*frac/100:,.1f} km^2)")


if __name__ == "__main__":
    main()
