# -*- coding: utf-8 -*-
"""
같은 GRD 씬을 Copernicus 30m DEM과 NGII 5m DEM(External DEM)으로 각각
RTC 처리한 뒤 비교하는 실험 스크립트.

산출물 (downloads/rtc_grd/):
  <씬ID>_rtc_db_aoi_cop.tif    # Copernicus 30m, AOI 서브셋
  <씬ID>_rtc_db_aoi_ngii.tif   # NGII 5m,       AOI 서브셋
  <씬ID>_dem_diff.tif           # dB 차이 맵 (NGII - Copernicus), QGIS 확인용

비교 항목 (TERRAIN_AUX_DATA_KR.md 2.3절):
  1) 육지 Gamma0 dB 백분위 분포
  2) 차분 맵 통계 — 평지에서 작고 산지 사면에서 큰 것이 정상.
     평지에서도 계통적 오프셋이 크면 datum/지오이드(EGM) 설정 의심.

실행:
    conda run -n s1_snappy python compare_dem_rtc.py [GRD.zip 경로]
    # 경로 생략 시 홍수 AOI를 덮는 S1D 7/2 씬 사용
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from prepro_gpt import aoi_wkt_from_geojson
from prepro_grd_gpt import build_grd_rtc_graph

PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "downloads" / "rtc_grd"
NGII_DEM = PROJECT_DIR / "downloads" / "dem" / "ngii_5m_aoi.tif"

DEFAULT_GRD = (
    PROJECT_DIR / "downloads" / "sentinel1_grd"
    / "S1D_IW_GRDH_1SDV_20260702T093102_20260702T093130_003493_0062D7_5469_COG.zip"
)

PCTS = [1, 5, 25, 50, 75, 95, 99]


def run_rtc(grd_path: Path, aoi_wkt: str, *, use_ngii: bool) -> Path:
    tag = "_aoi_ngii" if use_ngii else "_aoi_cop"
    out = OUT_DIR / f"{grd_path.stem}_rtc_db{tag}.tif"
    if out.exists():
        print(f"건너뜀 (이미 있음): {out.name}")
        return out

    kwargs = {}
    if use_ngii:
        if not NGII_DEM.exists():
            raise FileNotFoundError(f"NGII DEM 클립이 없습니다: {NGII_DEM} (download_hand.py 아님 — gdalwarp 클립 필요)")
        kwargs = {"external_dem_file": NGII_DEM}

    print(f"RTC 실행 ({'NGII 5m' if use_ngii else 'Copernicus 30m'}): {out.name}")
    t0 = time.time()
    graph = build_grd_rtc_graph(grd_path, out_dir=OUT_DIR, out_tag=tag, aoi_wkt=aoi_wkt, **kwargs)
    graph.run(gpt_options=["-q", "8", "-c", "14G"])
    print(f"  -> 완료 ({(time.time() - t0) / 60:.1f}분)")
    return out


def load_band(path: Path):
    import rasterio

    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform, ds.crs, ds.bounds


def compare(cop_path: Path, ngii_path: Path, diff_out: Path) -> None:
    import rasterio
    from rasterio.warp import Resampling, reproject

    cop, cop_tr, cop_crs, cop_bounds = load_band(cop_path)
    ngii, ngii_tr, ngii_crs, _ = load_band(ngii_path)

    # NGII 결과를 Copernicus 결과 격자에 리샘플해서 픽셀 단위 비교
    ngii_on_cop = np.full_like(cop, np.nan)
    reproject(
        source=ngii,
        destination=ngii_on_cop,
        src_transform=ngii_tr,
        src_crs=ngii_crs,
        dst_transform=cop_tr,
        dst_crs=cop_crs,
        resampling=Resampling.bilinear,
        src_nodata=0.0,
        dst_nodata=np.nan,
    )

    valid = np.isfinite(cop) & (cop != 0) & np.isfinite(ngii_on_cop)
    c, n = cop[valid], ngii_on_cop[valid]
    diff = n - c

    print("\n=== 육지 Gamma0 dB 분포 비교 ===")
    print(f"{'':18s}" + " ".join(f"p{p:<4d}" for p in PCTS))
    print("Copernicus 30m   " + " ".join(f"{v:5.1f}" for v in np.percentile(c, PCTS)))
    print("NGII 5m          " + " ".join(f"{v:5.1f}" for v in np.percentile(n, PCTS)))

    print("\n=== 차이 (NGII - Copernicus) ===")
    print(f"공통 유효 픽셀: {valid.sum():,}개")
    print(f"평균 {diff.mean():+.2f} dB | 표준편차 {diff.std():.2f} dB | 중앙값 {np.median(diff):+.2f} dB")
    print("차이 백분위: " + " ".join(f"p{p}={v:+.1f}" for p, v in zip(PCTS, np.percentile(diff, PCTS))))
    within_1db = 100 * (np.abs(diff) < 1.0).mean()
    print(f"|차이| < 1 dB 픽셀 비율: {within_1db:.1f}%")

    diff_full = np.where(valid, ngii_on_cop - cop, np.nan).astype("float32")
    with rasterio.open(cop_path) as src:
        profile = src.profile | {"dtype": "float32", "nodata": np.nan}
    with rasterio.open(diff_out, "w", **profile) as dst:
        dst.write(diff_full, 1)
    print(f"\n차분 맵 저장: {diff_out} (QGIS에서 확인)")


def main() -> None:
    grd_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GRD
    if not grd_path.exists():
        raise FileNotFoundError(grd_path)

    aoi_wkt = aoi_wkt_from_geojson(PROJECT_DIR / "geojson" / "Korea_flood_AOI.geojson")

    cop_out = run_rtc(grd_path, aoi_wkt, use_ngii=False)
    ngii_out = run_rtc(grd_path, aoi_wkt, use_ngii=True)

    diff_out = OUT_DIR / f"{grd_path.stem}_dem_diff.tif"
    compare(cop_out, ngii_out, diff_out)


if __name__ == "__main__":
    main()
