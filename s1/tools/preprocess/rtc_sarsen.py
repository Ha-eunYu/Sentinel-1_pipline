# -*- coding: utf-8 -*-
"""
SNAP 없이 Sentinel-1 GRD를 RTC(γ0) 또는 GTC로 지형보정하는 스크립트 — sarsen 사용.

SNAP을 설치할 수 없는 환경을 위한 대안. ESA SNAP의 Terrain-Flattening +
Terrain-Correction을 순수 파이썬(sarsen + xarray-sentinel + rasterio)으로 대체한다.
반드시 **sarsen 환경**(예: conda `sarsen_clean`)에서 실행한다.

  conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD.zip>
  conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD.zip> --gtc
  conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD.zip> \
      --external-dem downloads/dem/ngii_5m_wgs84.tif           # NGII 등 외부 DEM
  conda run -n sarsen_clean python rtc_sarsen.py --zip <GRD.zip> --no-egm

핵심 설계 (이 저장소에서 실측 검증한 사항, 2026-07-23)
------------------------------------------------------
1. **S1C/S1D 지원 패치**: xarray-sentinel 0.9.5의 애노테이션 파서 정규식이
   `s1[ab]`로 하드코딩돼 있어 Sentinel-1**C/D**를 인식 못 한다(그룹 0개 →
   "Invalid group 'IW/VV'"). 이 스크립트는 임포트 시 그 함수를 `s1[a-d]`로
   런타임 몽키패치한다(설치 파일·네트워크 불변). 유일한 하드코딩 지점이었다.
2. **DEM 수직기준(EGM2008 → 타원체고)**: COP30은 EGM2008 지오이드(정표고)
   기준인데 sarsen의 Range-Doppler 지오코딩은 **타원체고**를 가정한다. SNAP은
   이 보정을 내부에서 했지만(externalDEMApplyEGM) sarsen은 안 한다. 그래서
   PROJ 데이터의 `us_nga_egm08_25.tif`(EGM2008 undulation N)를 DEM 격자에
   리샘플해 **h_타원체 = h_정표고 + N** 으로 변환한 뒤 sarsen에 넣는다.
   (--no-egm로 끌 수 있음. NGII 등 정표고 외부 DEM도 같은 보정을 적용.)
3. **기본 DEM = COP30**, `--external-dem`으로 NGII 등 교체 가능. sardem 등으로
   매번 새로 받지 않고 **로컬에 이미 있는 타일**을 쓴다(--cop30-dir).

산출물: `<out-dir>/<씬ID>_rtc_db.tif` (또는 --gtc면 `_gtc_db.tif`).
        dB(10log10) 단일밴드, EPSG:4326, nodata=NaN. 기존 파이프라인(water_otsu 등)과 호환.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

# --- (1) 호환 몽키패치 (버전에 따라 자동 적용/생략) ---
# 이 프로젝트는 sarsen 여러 버전을 오갈 수 있어(0.9.3 stock ↔ 0.9.6/main), 아래
# 패치는 "필요할 때만, 없으면 조용히 건너뛰기(no-op)"로 방어적으로 적용한다.
#
# (1a) S1C/S1D 지원: 구버전 xarray-sentinel(<=0.9.5)의 애노테이션 파서 정규식이
#      s1[ab]로 하드코딩돼 S1C/D 파일을 전부 스킵한다(esa_safe.parse_manifest_sentinel1
#      의 continue). s1[a-d]로 넓힌다. main/0.9.6은 이미 s1[abcd]라 이 패치는 무해.
# (1b) datetime[ns] 강제: 구버전 sarsen orbit이 궤도 시각을 반드시 [ns]로 단정하는데
#      최신 pandas가 [us]를 줘서 AssertionError. 클래스가 있을 때만 세 메서드 입력
#      시각을 ns로 강제한다. 0.9.6은 클래스명이 OrbitPolyfitInterpolator로 바뀌고
#      pandas2용으로 자체 처리하므로 이 패치는 적용되지 않고 건너뛴다.
import xarray_sentinel.esa_safe as _esa_safe


def _parse_annotation_filename_s1cd(name: str):
    m = re.match(r"([a-z-]*)s1[a-d]-([^-]*)-[^-]*-([^-]*)-([\dt]*)-", os.path.basename(name))
    if m is None:
        raise ValueError(f"cannot parse name {name!r}")
    return tuple(m.groups())


try:
    _esa_safe.parse_annotation_filename = _parse_annotation_filename_s1cd
except Exception:  # pragma: no cover
    pass

import sarsen  # noqa: E402  (패치 후 임포트)


def _coerce_ns(da):
    n = getattr(getattr(da, "dtype", None), "name", "")
    if n.startswith("datetime64") and n != "datetime64[ns]":
        return da.astype("datetime64[ns]")
    if n.startswith("timedelta64") and n != "timedelta64[ns]":
        return da.astype("timedelta64[ns]")
    return da


def _install_orbit_ns_patch() -> bool:
    """구버전 sarsen orbit에 ns 강제 패치. 대상 클래스가 없으면(신버전) no-op."""
    try:
        import sarsen.orbit as _orb
    except Exception:
        return False
    cls = getattr(_orb, "OrbitPolyfitIterpolator", None)  # 구버전 오타 클래스명
    if cls is None:
        return False  # 0.9.6/main은 OrbitPolyfitInterpolator → 패치 불필요
    of, op, ov = cls.from_position.__func__, cls.position, cls.velocity

    def _fp(c, position, dim="azimuth_time", **kw):
        if dim in position.coords:
            position = position.assign_coords({dim: _coerce_ns(position.coords[dim])})
        return of(c, position, dim=dim, **kw)

    cls.from_position = classmethod(_fp)
    cls.position = lambda self, time=None, **kw: op(self, None if time is None else _coerce_ns(time), **kw)
    cls.velocity = lambda self, time=None, **kw: ov(self, None if time is None else _coerce_ns(time), **kw)
    return True


_ORBIT_NS_PATCHED = _install_orbit_ns_patch()


def _install_chunking_patch() -> bool:
    """sarsen 라디오메트리 시뮬레이션의 map_overlap 교체.

    기본값 `simple_dask_map_overlap`은 (1) 첫 dask 청크가 overlap 깊이(128)보다
    작으면 `allow_rechunk=False`로 즉시 실패하고(일부 씬의 청크 배치에서 발생),
    (2) 풀사이즈 IW GRD(약 26k×16k)에서 full float64 그리드를 여러 개 적재해
    피크 메모리가 20GB+로 튀어 OOM 위험이 크다.

    sarsen이 같은 시그니처로 제공하는 `sync_map_overlap`(수동 2048 타일 + bound 128,
    dask overlap 미사용)으로 교체하면 두 문제를 모두 피한다. apps.py가
    `chunking.map_overlap`을 호출 시점에 조회하므로 모듈 속성 교체로 충분하다.
    구버전에 sync 구현이 없으면 no-op."""
    try:
        import sarsen.chunking as _ch
    except Exception:
        return False
    sync = getattr(_ch, "sync_map_overlap", None)
    if sync is None or getattr(_ch, "map_overlap", None) is sync:
        return False
    _ch.map_overlap = sync
    return True


_CHUNKING_PATCHED = _install_chunking_patch()

from s1.core.paths import PROJECT_DIR  # 저장소 루트(경로는 s1.core.paths에서만 정의)
# 이미 로컬에 받아둔 COP30 전지구 VRT(EGM2008 지오이드 기준, EPSG:4326 30m).
# 대상 환경이 다르면 --cop30-vrt로 지정.
DEFAULT_COP30_VRT = Path(r"D:/00_COP30/COP30_hh.vrt")
DEFAULT_OUT_DIR = PROJECT_DIR / "downloads" / "rtc_grd_sarsen"
CHUNK_ROWS = 1024


def require_gdal() -> None:
    for tool in ("gdalbuildvrt", "gdalwarp"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"'{tool}'을 PATH에서 찾을 수 없습니다(GDAL 필요).")


def find_egm2008_grid(override: str | None) -> Path:
    """EGM2008 undulation 그리드(us_nga_egm08_25.tif) 경로. PROJ 데이터에서 자동 탐색."""
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"--egm-grid 파일 없음: {p}")
        return p
    import pyproj
    cand = Path(pyproj.datadir.get_data_dir()) / "us_nga_egm08_25.tif"
    if cand.exists():
        return cand
    hits = glob.glob(str(Path(pyproj.datadir.get_data_dir()) / "*egm08*.tif"))
    if hits:
        return Path(hits[0])
    raise FileNotFoundError(
        "EGM2008 그리드(us_nga_egm08_25.tif)를 PROJ 데이터에서 못 찾음. "
        "--egm-grid로 지정하거나 --no-egm 사용."
    )


def extract_safe(zip_path: Path, work_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(work_dir)
    safes = glob.glob(str(work_dir / "*.SAFE"))
    if not safes:
        raise RuntimeError(f"{zip_path.name} 안에서 .SAFE를 찾지 못함")
    return Path(safes[0])


def scene_bbox(safe_dir: Path, pol: str) -> tuple[float, float, float, float]:
    """씬의 (min_lon, min_lat, max_lon, max_lat). 측정 그룹의 geospatial 속성 우선,
    없으면 GCP 그룹의 위경도에서 산출."""
    import xarray_sentinel
    grp = f"IW/{pol.upper()}"
    ds = xarray_sentinel.open_sentinel1_dataset(str(safe_dir), group=grp)
    a = ds.attrs
    keys = ("geospatial_lon_min", "geospatial_lat_min", "geospatial_lon_max", "geospatial_lat_max")
    if all(k in a for k in keys):
        return (float(a["geospatial_lon_min"]), float(a["geospatial_lat_min"]),
                float(a["geospatial_lon_max"]), float(a["geospatial_lat_max"]))
    gcp = xarray_sentinel.open_sentinel1_dataset(str(safe_dir), group=f"{grp}/gcp")
    lon, lat = gcp["longitude"].values, gcp["latitude"].values
    return (float(np.nanmin(lon)), float(np.nanmin(lat)),
            float(np.nanmax(lon)), float(np.nanmax(lat)))


def build_dem_wgs84(bbox, margin: float, cop30_vrt: Path, external_dem: str | None,
                    work_dir: Path) -> Path:
    """씬 bbox(+margin)를 덮는 EPSG:4326 DEM(정표고, 아직 EGM 보정 전)을 만든다.
    소스는 COP30 전지구 VRT(기본) 또는 외부 DEM(NGII 등). gdalwarp로 bbox 클립하며
    VRT는 필요한 타일만 읽으므로 전지구라도 빠르다."""
    w, s, e, n = bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin
    source = external_dem if external_dem else str(cop30_vrt)
    if not Path(source).exists():
        raise FileNotFoundError(f"DEM 소스 없음: {source}")
    out = work_dir / "dem_wgs84.tif"
    subprocess.run(
        ["gdalwarp", "-overwrite", "-t_srs", "EPSG:4326", "-r", "bilinear",
         "-te", str(w), str(s), str(e), str(n), "-of", "GTiff", source, str(out)],
        check=True, stdout=subprocess.DEVNULL)
    return out


def apply_egm2008(dem_in: Path, egm_grid: Path, dem_out: Path) -> None:
    """정표고 DEM에 EGM2008 undulation N을 더해 타원체고 DEM으로 변환.
    N을 DEM 격자에 bilinear 리샘플(rasterio.reproject)해 행블록 단위로 더한다."""
    with rasterio.open(dem_in) as dem, rasterio.open(egm_grid) as egm:
        profile = dem.profile.copy()
        profile.update(dtype="float32", count=1, compress="deflate", predictor=3, BIGTIFF="IF_SAFER")
        dem_nodata = dem.nodata
        egm_arr = egm.read(1)
        egm_transform, egm_crs = egm.transform, egm.crs
        with rasterio.open(dem_out, "w", **profile) as dst:
            for row0 in range(0, dem.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, dem.height - row0)
                win = rasterio.windows.Window(0, row0, dem.width, nrows)
                h = dem.read(1, window=win).astype("float32")
                win_transform = rasterio.windows.transform(win, dem.transform)
                n_block = np.zeros((nrows, dem.width), dtype="float32")
                reproject(source=egm_arr, destination=n_block,
                          src_transform=egm_transform, src_crs=egm_crs,
                          dst_transform=win_transform, dst_crs=dem.crs,
                          resampling=Resampling.bilinear)
                out = h + n_block
                if dem_nodata is not None:
                    out = np.where(h == dem_nodata, dem_nodata, out)
                dst.write(out.astype("float32"), 1, window=win)


def run_terrain_correction(safe_dir: Path, dem_ellip: Path, out_linear: Path,
                           pol: str, gtc: bool, radiometry: str,
                           tc_chunks: int | None = None) -> None:
    product = sarsen.Sentinel1SarProduct(str(safe_dir), measurement_group=f"IW/{pol.upper()}")
    kwargs = dict(product=product, dem_urlpath=str(dem_ellip), output_urlpath=str(out_linear))
    if tc_chunks:
        # 풀사이즈 IW GRD는 기본 청크(1024/2048)에서 지오코딩 interp가 full float64
        # 그리드를 적재해 OOM 위험 → 청크를 줄여 map_blocks 타일·피크 메모리를 낮춘다.
        kwargs["chunks"] = int(tc_chunks)
        kwargs["radiometry_chunks"] = int(tc_chunks)
    if not gtc:
        kwargs["correct_radiometry"] = radiometry  # gamma_bilinear / gamma_nearest
    sarsen.terrain_correction(**kwargs)


def linear_to_db(in_tif: Path, out_tif: Path) -> None:
    """linear power -> dB(10log10). 0/음수/nodata는 NaN. 기존 *_rtc_db.tif 규약과 동일."""
    with rasterio.open(in_tif) as src:
        profile = src.profile.copy()
        profile.update(dtype="float32", count=1, nodata=float("nan"),
                       compress="deflate", predictor=3, BIGTIFF="IF_SAFER")
        src_nodata = src.nodata
        with rasterio.open(out_tif, "w", **profile) as dst:
            for _, win in src.block_windows(1):
                a = src.read(1, window=win).astype("float64")
                valid = np.isfinite(a) & (a > 0)
                if src_nodata is not None:
                    valid &= a != src_nodata
                db = np.full(a.shape, np.nan, dtype="float32")
                db[valid] = (10.0 * np.log10(a[valid])).astype("float32")
                dst.write(db, 1, window=win)


def main() -> None:
    ap = argparse.ArgumentParser(description="SNAP 없이 S1 GRD RTC/GTC (sarsen)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip", help="S1 GRD .zip 경로")
    src.add_argument("--safe", help="이미 푼 .SAFE 폴더 경로")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--pol", default="VV", choices=["VV", "VH"], help="편파 (기본 VV)")
    ap.add_argument("--gtc", action="store_true", help="지형평탄화 생략(GTC). 기본은 RTC(γ0)")
    ap.add_argument("--radiometry", default="gamma_bilinear",
                    choices=["gamma_bilinear", "gamma_nearest"], help="RTC 방사보정 방식")
    ap.add_argument("--tc-chunks", type=int, default=None,
                    help="지형보정 청크 크기(chunks·radiometry_chunks). 풀사이즈 씬 OOM 시 "
                         "256~512로 낮춤. 생략 시 sarsen 기본(1024/2048)")
    ap.add_argument("--external-dem", default=None, help="외부 DEM(NGII 등). 생략 시 COP30 VRT")
    ap.add_argument("--cop30-vrt", type=Path, default=DEFAULT_COP30_VRT, help="로컬 COP30 전지구 VRT")
    ap.add_argument("--no-egm", action="store_true", help="EGM2008->타원체고 보정 생략")
    ap.add_argument("--egm-grid", default=None, help="EGM2008 undulation 그리드 경로(자동탐색 기본)")
    ap.add_argument("--margin", type=float, default=0.2, help="DEM을 씬보다 넓힐 여백(도)")
    ap.add_argument("--keep-temp", action="store_true", help="임시폴더 유지(디버깅)")
    ap.add_argument("--dry-run", action="store_true", help="지형보정 직전(DEM 준비)까지만")
    args = ap.parse_args()

    require_gdal()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="rtc_sarsen_"))
    print(f"작업 폴더: {work_dir}")

    try:
        if args.safe:
            safe_dir = Path(args.safe)
            stem = safe_dir.stem
        else:
            zip_path = Path(args.zip)
            print(f"[1/5] SAFE 추출: {zip_path.name}")
            safe_dir = extract_safe(zip_path, work_dir)
            stem = zip_path.stem

        print("[2/5] 씬 bbox 산출")
        bbox = scene_bbox(safe_dir, args.pol)
        print(f"  bbox lon {bbox[0]:.4f}~{bbox[2]:.4f}, lat {bbox[1]:.4f}~{bbox[3]:.4f}")

        print(f"[3/5] DEM 구성 ({'외부 DEM' if args.external_dem else 'COP30 VRT'})")
        dem_wgs84 = build_dem_wgs84(bbox, args.margin, args.cop30_vrt, args.external_dem, work_dir)

        if args.no_egm:
            dem_ellip = dem_wgs84
            print("  EGM 보정 생략(--no-egm)")
        else:
            egm_grid = find_egm2008_grid(args.egm_grid)
            dem_ellip = work_dir / "dem_ellipsoidal.tif"
            print(f"  EGM2008 보정 적용: {Path(egm_grid).name}")
            apply_egm2008(dem_wgs84, Path(egm_grid), dem_ellip)

        if args.dry_run:
            keep = work_dir / "dem_ellipsoidal_dryrun.tif"
            shutil.copy2(dem_ellip, args.out_dir / f"{stem}_DEM_ellipsoidal.tif")
            print(f"[dry-run] DEM 준비 완료 -> {args.out_dir / (stem + '_DEM_ellipsoidal.tif')}")
            return

        suffix = "gtc_db" if args.gtc else "rtc_db"
        out_linear = work_dir / f"{stem}_{'gtc' if args.gtc else 'rtc'}_linear.tif"
        out_db = args.out_dir / f"{stem}_{suffix}.tif"
        print(f"[4/5] sarsen 지형보정 ({'GTC' if args.gtc else 'RTC γ0 ' + args.radiometry})")
        import time as _time
        _t0 = _time.perf_counter()
        run_terrain_correction(safe_dir, dem_ellip, out_linear, args.pol, args.gtc,
                                args.radiometry, tc_chunks=args.tc_chunks)

        print(f"[5/5] dB 변환 -> {out_db.name}")
        linear_to_db(out_linear, out_db)
        _dt = _time.perf_counter() - _t0
        print(f"완료: {out_db}  (지형보정+dB {_dt/60:.1f}분)")
        print(f"PROCESS_SECONDS={_dt:.2f}")

    finally:
        if args.keep_temp:
            print(f"임시폴더 유지: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
