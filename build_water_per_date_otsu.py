# -*- coding: utf-8 -*-
"""
궤도별·날짜별 순수 수체 지도 생성 — 고정 dB 임계값(-16) 대신 **Otsu**로
그 관측(패스)에서 임계값을 자동 결정한다.

build_water_per_date.py 와의 차이
  - build_water_per_date.py: 한 날짜의 모든 프레임/패스를 하나로 모자이크한
    뒤 고정 임계값(dB < -16)을 적용한다.
  - 이 스크립트: 같은 날짜라도 **궤도(절대궤도번호)가 다르면 별도 그룹**으로
    나눈다. 궤도가 다르면 입사각·촬영기하가 달라 후방산란 dB 분포도 다르므로,
    여러 궤도를 한 히스토그램에 섞으면 임계값이 왜곡된다. 그래서 궤도별로
    따로 모자이크 -> 따로 Otsu -> 따로 수체 판정한다.

왜 "전역(global) Otsu"가 아니라 "타일 기반(split-based) Otsu"인가
  물(잔잔한 수면)은 VV dB 히스토그램에서 어두운(낮은) 봉우리다. 하지만 넓은
  장면에서 물 화소는 육지보다 압도적으로 적다(이 프로젝트 7/3 장면 기준 약
  1:150). 전역 Otsu는 클래스 간 분산을 최대화하려고 **다수인 육지 분포를
  반으로 가르는** 지점(≈ -8 dB)을 임계값으로 잡아버려, 장면의 절반을 물로
  오판한다.

  Martinis(2009)·Chini(2017)의 split-based 자동 임계값 기법을 쓴다:
    1) 장면을 타일(기본 1024px ≈ 10km)로 나눈다.
    2) 타일마다 Otsu 분리도(separability η∈[0,1])와 어두운클래스 비율을
       구해, **물+육지가 함께 있어 뚜렷이 이봉(bimodal)인 타일**만 고른다
       (η 상위 백분위 + 어두운클래스 비율이 한쪽으로 치우치지 않은 타일).
    3) 고른 타일들의 히스토그램을 모아(pool) 한 번의 Otsu로 임계값을 낸다.
       이봉 타일 안에서는 물:육지가 비슷한 비율이라 Otsu가 진짜 물/육지
       골짜기(이 장면 ≈ -15~-18 dB)를 찾는다.
    4) 그 임계값을 궤도 전체에 적용한다.
  이봉 타일이 충분히 없으면(장면이 대부분 육지/물) --fallback-db(-16) 로
  물러난다(경고 표시).

메모리 안전: VRT를 청크/타일 단위로 훑는다. 타일별 히스토그램(count 배열)만
들고 있어 원본 전체를 메모리에 올리지 않는다.

산출물 (downloads/water_otsu/):
  flood_water_total_<날짜>_o<절대궤도>.tif   궤도별·날짜별 수체 지도
      (0=비수체, 1=수체, 255=미관측). 접미사 _o<절대궤도>는 균일성을 위해
      그 날짜의 궤도 개수와 무관하게 항상 붙는다.
  otsu_thresholds.csv                        그룹별 Otsu 임계값·면적 로그

실행:
    conda run -n s1_snappy python build_water_per_date_otsu.py            # 전체 날짜
    conda run -n s1_snappy python build_water_per_date_otsu.py --dates 20260703,20260714
    conda run -n s1_snappy python build_water_per_date_otsu.py --tile 1024 --pctl 95
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from build_baseline_composite_grd import RTC_GRD_DIR, scene_date

PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "downloads" / "water_otsu"
VRT_DIR = OUT_DIR / "vrt"

NODATA_U8 = 255
CHUNK_ROWS = 512

# 히스토그램 범위/해상도 (0.1 dB 폭). 범위 밖 값은 히스토그램에서 자동 제외.
HIST_MIN_DEFAULT = -35.0
HIST_MAX_DEFAULT = 10.0
BINS_DEFAULT = 450

# 타일 기반 Otsu 파라미터
TILE_DEFAULT = 1024          # 타일 한 변(px). ~10m 해상도에서 약 10km.
MIN_VALID_FRAC = 0.25        # 타일이 이 비율 이상 유효해야 후보로 인정
PCTL_DEFAULT = 95.0          # 분리도 η 상위 (100-pctl)% 타일을 이봉 타일로 채택
BALANCE_MIN, BALANCE_MAX = 0.02, 0.98  # 타일 Otsu 어두운클래스 비율 허용 범위
MIN_SELECTED_TILES = 8       # 이보다 적으면 이봉 근거 부족 -> fallback
FALLBACK_DB_DEFAULT = -16.0  # 이봉 타일이 부족할 때 물러설 고정 임계값

# Otsu 임계값이 이 범위를 벗어나면 물/육지 골짜기가 아닐 가능성 -> 경고만.
SANE_THR_MIN, SANE_THR_MAX = -25.0, -10.0

# 절대궤도번호(6자리) 추출
ORBIT_RE = re.compile(r"_(\d{8})T\d{6}_\d{8}T\d{6}_(\d{6})_[0-9A-Fa-f]{6}_")


def scene_orbit(tif: Path) -> str | None:
    m = ORBIT_RE.search(tif.name)
    return m.group(2) if m else None


def group_scenes(dates: list[str] | None) -> dict[tuple[str, str], list[Path]]:
    """(날짜, 절대궤도) -> 프레임 목록. dates=None 이면 존재하는 모든 날짜."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for tif in sorted(RTC_GRD_DIR.glob("*_rtc_db.tif")):
        d, orbit = scene_date(tif), scene_orbit(tif)
        if d is None or orbit is None:
            continue
        if dates is not None and d not in dates:
            continue
        groups[(d, orbit)].append(tif)
    return groups


def build_group_vrt(date: str, orbit: str, frames: list[Path]) -> Path:
    """궤도별 모자이크 VRT 생성. 소스를 절대경로로 넣어 VRT 위치와 무관하게 열림."""
    VRT_DIR.mkdir(parents=True, exist_ok=True)
    vrt_path = VRT_DIR / f"mosaic_{date}_o{orbit}.vrt"
    cmd = ["gdalbuildvrt", "-srcnodata", "0", "-vrtnodata", "0", "-overwrite",
           str(vrt_path), *[str(f.resolve()) for f in frames]]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return vrt_path


def otsu_on_hist(counts: np.ndarray, centers: np.ndarray):
    """히스토그램에서 Otsu 임계값과 부가 지표를 계산.
    반환: (임계값 dB, 분리도 η∈[0,1], 어두운클래스 비율, 유효 화소수).
    분리도 η = 클래스간분산/전체분산 — 값이 클수록 뚜렷한 이봉."""
    counts = counts.astype("float64")
    total = counts.sum()
    if total == 0:
        return None, 0.0, 0.0, 0
    w0 = np.cumsum(counts)                 # 임계값 이하(어두운) 클래스 누적
    w1 = total - w0
    csum = np.cumsum(counts * centers)
    grand = (counts * centers).sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = csum / w0
        m1 = (grand - csum) / w1
        bcv = w0 * w1 * (m0 - m1) ** 2     # 클래스간 분산 * total^2 (비정규화)
    bcv[(w0 == 0) | (w1 == 0)] = 0.0
    idx = int(np.argmax(bcv))
    mean = grand / total
    total_var = (counts * (centers - mean) ** 2).sum()
    # σ_b²/σ_t² = (bcv/total²)/(total_var/total) = bcv/(total*total_var)
    eta = float(bcv[idx] / (total * total_var + 1e-12))
    thr = float(centers[idx])
    dark_frac = float(w0[idx] / total)
    return thr, eta, dark_frac, int(total)


def tile_based_threshold(vrt: Path, hist_min: float, hist_max: float, bins: int,
                         tile: int, pctl: float, fallback_db: float):
    """타일 기반 split Otsu 임계값. 반환: (임계값, meta dict)."""
    edges = np.linspace(hist_min, hist_max, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0

    tile_etas: list[float] = []
    tile_darks: list[float] = []
    tile_hists: list[np.ndarray] = []
    with rasterio.open(vrt) as src:
        H, W = src.height, src.width
        for r0 in range(0, H, tile):
            nr = min(tile, H - r0)
            for c0 in range(0, W, tile):
                nc = min(tile, W - c0)
                db = src.read(1, window=Window(c0, r0, nc, nr)).astype("float32")
                v = np.isfinite(db) & (db != 0)
                if v.sum() < MIN_VALID_FRAC * db.size:
                    continue
                c, _ = np.histogram(db[v], bins=bins, range=(hist_min, hist_max))
                thr_i, eta_i, dark_i, _ = otsu_on_hist(c, centers)
                if thr_i is None:
                    continue
                tile_etas.append(eta_i)
                tile_darks.append(dark_i)
                tile_hists.append(c)

    n_cand = len(tile_etas)
    meta = {"n_cand_tiles": n_cand, "method": "tile-otsu", "fallback": False}
    if n_cand == 0:
        meta.update(method="fallback", fallback=True, n_sel_tiles=0)
        return fallback_db, meta

    etas = np.asarray(tile_etas)
    eta_cut = np.percentile(etas, pctl)
    sel = [i for i in range(n_cand)
           if etas[i] >= eta_cut and BALANCE_MIN <= tile_darks[i] <= BALANCE_MAX]

    if len(sel) < MIN_SELECTED_TILES:
        meta.update(method="fallback", fallback=True, n_sel_tiles=len(sel))
        return fallback_db, meta

    pooled = np.zeros(bins, dtype="int64")
    for i in sel:
        pooled += tile_hists[i]
    thr, eta, dark, _ = otsu_on_hist(pooled, centers)
    meta.update(n_sel_tiles=len(sel), pooled_eta=round(eta, 4),
                pooled_dark_frac=round(dark, 4))

    # 이봉 타일이 충분해도, 합산 Otsu가 정상 수체 범위를 벗어나면(예: 이봉이
    # 약해 육지 봉우리를 갈라 -8dB로 튀는 경우) 신뢰할 수 없다 -> fallback.
    if not (SANE_THR_MIN <= thr <= SANE_THR_MAX):
        meta.update(method="fallback", fallback=True, otsu_raw=round(thr, 3))
        return fallback_db, meta
    return thr, meta


def write_water(vrt: Path, threshold: float, out_path: Path) -> tuple[int, int, float]:
    """dB < threshold 를 수체(1)로 청크 단위로 써 나간다.
    반환: (수체화소, 유효화소, 화소면적km2)."""
    with rasterio.open(vrt) as src:
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width,
            "count": 1, "dtype": "uint8", "crs": src.crs, "transform": src.transform,
            "nodata": NODATA_U8, "compress": "DEFLATE", "tiled": True,
            "bigtiff": "IF_SAFER",
        }
        res_deg = abs(src.transform.a)
        center_lat = (src.bounds.bottom + src.bounds.top) / 2
        px_area_km2 = (res_deg * 111_320.0) * (res_deg * 111_320.0 * np.cos(np.radians(center_lat))) / 1e6

        n_water = n_valid = 0
        with rasterio.open(out_path, "w", **profile) as dst:
            for row0 in range(0, src.height, CHUNK_ROWS):
                nrows = min(CHUNK_ROWS, src.height - row0)
                win = Window(0, row0, src.width, nrows)
                db = src.read(1, window=win).astype("float32")
                valid = np.isfinite(db) & (db != 0)
                water = valid & (db < threshold)
                dst.write(np.where(valid, water.astype("uint8"), NODATA_U8), 1, window=win)
                n_water += int(water.sum())
                n_valid += int(valid.sum())
    return n_water, n_valid, px_area_km2


def water_for_group(date: str, orbit: str, frames: list[Path], out_name: str,
                    args) -> dict:
    vrt = build_group_vrt(date, orbit, frames)
    threshold, meta = tile_based_threshold(
        vrt, args.hist_min, args.hist_max, args.bins, args.tile, args.pctl,
        args.fallback_db)

    out_path = OUT_DIR / out_name
    n_water, n_valid, px_area_km2 = write_water(vrt, threshold, out_path)

    flags = []
    if meta["fallback"]:
        if "otsu_raw" in meta:  # 이봉은 됐으나 임계값이 범위를 벗어나 물러남
            flags.append(f"Otsu {meta['otsu_raw']}dB가 통상 수체 범위 밖 "
                         f"-> fallback {args.fallback_db}dB")
        else:
            flags.append(f"이봉 타일 부족({meta['n_sel_tiles']}) "
                         f"-> fallback {args.fallback_db}dB")
    flag = ("  [경고: " + "; ".join(flags) + "]") if flags else ""

    print(f"[{date} o{orbit}] 프레임 {len(frames)}개, {meta['method']} "
          f"임계값={threshold:.2f} dB (이봉타일 {meta.get('n_sel_tiles', 0)}/{meta['n_cand_tiles']}), "
          f"커버리지 {n_valid:,}px, 수체 {n_water * px_area_km2:,.2f} km^2 "
          f"-> {out_name}{flag}")

    return {
        "date": date, "orbit": orbit, "frames": len(frames),
        "method": meta["method"], "otsu_db": round(threshold, 3),
        "sel_tiles": meta.get("n_sel_tiles", 0), "cand_tiles": meta["n_cand_tiles"],
        "pooled_eta": meta.get("pooled_eta", ""),
        "water_km2": round(n_water * px_area_km2, 3),
        "valid_px": n_valid, "output": out_name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="궤도별·날짜별 타일기반 Otsu 수체 지도")
    parser.add_argument("--dates", default=None,
                        help="쉼표구분 YYYYMMDD 목록 (생략 시 존재하는 모든 날짜)")
    parser.add_argument("--hist-min", type=float, default=HIST_MIN_DEFAULT)
    parser.add_argument("--hist-max", type=float, default=HIST_MAX_DEFAULT)
    parser.add_argument("--bins", type=int, default=BINS_DEFAULT)
    parser.add_argument("--tile", type=int, default=TILE_DEFAULT, help="타일 한 변(px)")
    parser.add_argument("--pctl", type=float, default=PCTL_DEFAULT,
                        help="이봉 타일 채택 분리도 백분위 (기본 95=상위 5%%)")
    parser.add_argument("--fallback-db", type=float, default=FALLBACK_DB_DEFAULT,
                        help="이봉 타일 부족 시 고정 임계값")
    parser.add_argument("--overwrite", action="store_true", help="기존 출력도 재계산")
    args = parser.parse_args()

    dates = [d.strip() for d in args.dates.split(",")] if args.dates else None
    groups = group_scenes(dates)
    if not groups:
        raise SystemExit("처리할 그룹이 없습니다 (해당 날짜의 *_rtc_db.tif 없음).")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for (date, orbit) in sorted(groups):
        # 궤도 접미사(_o<절대궤도>)는 균일성을 위해 궤도 개수와 무관하게 항상 붙인다.
        out_name = f"flood_water_total_{date}_o{orbit}.tif"
        if (OUT_DIR / out_name).exists() and not args.overwrite:
            print(f"[{date} o{orbit}] 이미 존재, 건너뜀: {out_name} (--overwrite 로 재계산)")
            continue
        rows.append(water_for_group(date, orbit, groups[(date, orbit)], out_name, args))

    if rows:
        csv_path = OUT_DIR / "otsu_thresholds.csv"
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if write_header:
                w.writeheader()
            w.writerows(rows)
        print(f"\n임계값 로그: {csv_path}")


if __name__ == "__main__":
    main()
