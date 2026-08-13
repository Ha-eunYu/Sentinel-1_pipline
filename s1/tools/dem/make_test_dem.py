# -*- coding: utf-8 -*-
"""영산강 하구 시험용 DEM 두 판을 만든다 — COP30 0값이 TF를 죽이는지 가른다.

배경
----
영산강 **제약 안 dB의 20.3%가 결측**이다. 그 자리의 COP30을 보면 75.2%가
정확히 0.0 m이고, 정상 자리는 0값이 하나도 없다. COP30이 수역을 0으로
채우고 SNAP Terrain-Flattening이 그 자리를 무효 처리한 것으로 보인다.

그런데 **원인이 둘 중 무엇인지 아직 모른다.**

    ① SNAP이 0을 nodata로 취급        → 0.1로만 바꿔도 해결
    ② 수역 평탄면에서 조사면적이 퇴화   → 값을 바꿔도 재발

①이면 NGII가 아예 필요 없다. 작은 구역으로 시험해 가른다.

산출
----
    dem_test/yeongsan_cop30.tif        원본 그대로(대조군)
    dem_test/yeongsan_cop30_fix.tif    0 → 0.1 m 치환
    dem_test/yeongsan_ngii_hybrid.tif  NGII 우선, 없으면 0.1 m

⚠ 수직 기준은 이미 맞아 있다 — 실측 COP30−NGII 중앙 −0.64 m다(지오이드고
   +24~26 m가 아니다). `5m_DEM.tif`도 타원체고이므로 EGM 보정을 걸면 안 된다.

실행
----
    conda run -n sar-gee python make_test_dem.py
"""
from __future__ import annotations

from pathlib import Path

from s1.core.paths import COP30_KOREA_VRT, DEM_TEST_DIR

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import box

COP = str(COP30_KOREA_VRT)
NGII = r"D:\00_DEM\전국5mDEM\5m_DEM.tif"
OUT = DEM_TEST_DIR

# 육지 폴리곤 — **바다는 0 m가 맞으므로 건드리지 않는다.**
#
# 연결성(최대 덩어리 = 바다)으로 가르면 위험하다. 하구호가 수로로 바다와
# 이어져 있으면 통째로 바다로 묶여 안 고쳐진다. 실제로 GADM 기반
# `Korea_Peninsula.shp`는 해안선이 거칠어 **영암호·낙동강 하구를 바다로**
# 뺐다. 국토지리정보원 국가면은 둘 다 육지로 잡는다(2026-08-03 검정).
LAND = (r"D:\01_GIS_Data\Korea_Peninsula_shp\kmap_2024_120_korean_shp"
        r"\KOR_NAION_AS_국문.shp")

# 영산강 유역 + 하구를 넉넉히 덮는 창. RTC가 씬 전체를 처리하므로
# DEM은 그 씬을 다 덮어야 한다 — 좁게 자르면 밖이 nodata가 된다.
W, S, E, N = 126.0, 34.3, 127.4, 35.8
RES = 0.000277777777778          # COP30과 같은 1 arcsec
FILL = 0.1                       # 0 대신 넣을 미소 양수(m)


def read(path: str, prof: dict) -> np.ndarray:
    with rasterio.open(path) as s, \
            WarpedVRT(s, crs=prof["crs"], transform=prof["transform"],
                      width=prof["width"], height=prof["height"],
                      resampling=rasterio.enums.Resampling.bilinear,
                      src_nodata=s.nodata, nodata=np.nan) as v:
        a = v.read(1).astype("float32")
    return np.where(a < -1e30, np.nan, a)


def write(path: Path, a: np.ndarray, prof: dict, nodata: float) -> None:
    p = dict(prof, count=1, dtype="float32", nodata=nodata,
             compress="deflate", tiled=True, predictor=3)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(np.nan_to_num(a, nan=nodata).astype("float32"), 1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = int(round((E - W) / RES))
    h = int(round((N - S) / RES))
    prof = {"crs": rasterio.crs.CRS.from_epsg(4326),
            "transform": from_origin(W, N, RES, RES),
            "width": w, "height": h}
    print(f"창 {W}~{E}E {S}~{N}N  {w}x{h}화소 ({w*h/1e6:.1f} M)\n")

    cop = read(COP, prof)
    z0 = np.isfinite(cop) & (cop == 0)

    # **바다는 건드리지 않는다** — 바다는 실제로 0 m가 맞다.
    # 육지 폴리곤으로 가른다(연결성 휴리스틱은 하구호를 바다로 묶는다).
    import geopandas as gpd
    import pyogrio
    from rasterio.features import rasterize

    # ⚠ **pyogrio의 bbox는 레이어 원본 CRS로 해석된다.** `KOR_NAION_AS`는
    #   EPSG:5179인데 경위도 bbox를 그대로 넘겼다가 **빈 결과**가 왔다
    #   (육지 0.0%). 예외가 안 나서 조용히 틀린다 — 이 프로젝트에서
    #   다섯 번째 재발이다(gee/PITFALLS_KR.md §1-1).
    native = pyogrio.read_info(LAND)["crs"]
    bnds = (gpd.GeoSeries([box(W, S, E, N)], crs=4326)
            .to_crs(native).total_bounds if native else (W, S, E, N))
    g = pyogrio.read_dataframe(LAND, bbox=tuple(bnds))
    if g.empty:
        raise SystemExit(f"육지 폴리곤이 창 안에 없습니다 — bbox/CRS 확인: {native}")
    if g.crs is None:
        g = g.set_crs(native or 5179, allow_override=True)
    g = g.to_crs(4326)
    g["geometry"] = g.geometry.make_valid()
    land = rasterize([(x, 1) for x in g.geometry],
                     out_shape=(prof["height"], prof["width"]),
                     transform=prof["transform"], dtype="uint8").astype(bool)

    z = z0 & land                       # 고칠 대상 = **육지 안의** 0값
    print(f"COP30   결측 {np.isnan(cop).mean()*100:5.2f}%  "
          f"0값 {z0.mean()*100:5.2f}%  중앙 {np.nanmedian(cop):.2f} m")
    print(f"        육지 {land.mean()*100:.1f}%  ·  0값 중 육지 안 "
          f"**{z.sum()/z0.sum()*100:.1f}%**(고침) · "
          f"바다 {(z0 & ~land).sum()/z0.sum()*100:.1f}%(그대로)")

    # ① 원본
    write(OUT / "yeongsan_cop30.tif", cop, prof, -32768.0)

    # ② 내륙 0 → 미소 양수
    fix = np.where(z, FILL, cop)
    write(OUT / "yeongsan_cop30_fix.tif", fix, prof, -32768.0)
    print(f"        → 내륙 0값 {z.sum():,}화소를 {FILL} m로 치환 "
          f"(경사 변화 경계부 중앙 0.089°, 상한 0.191°)")

    # ③ NGII 우선 하이브리드
    ng = read(NGII, prof)
    ok = z & np.isfinite(ng)
    hyb = np.where(z, np.where(np.isfinite(ng), ng, FILL), cop)
    write(OUT / "yeongsan_ngii_hybrid.tif", hyb, prof, -32768.0)
    print(f"NGII    내륙 0값 중 값있음 {ok.sum()/max(1,z.sum())*100:5.1f}% "
          f"(중앙 {np.nanmedian(ng[ok]) if ok.any() else float('nan'):.2f} m), "
          f"나머지는 {FILL} m")

    print(f"\n산출 → {OUT}")
    for p in sorted(OUT.glob("yeongsan_*.tif")):
        print(f"  {p.name:<28}{p.stat().st_size/1e6:>7.0f} MB")
    print("\n다음: 같은 granule을 세 DEM으로 RTC 처리해 결측률을 비교한다.")


if __name__ == "__main__":
    main()
