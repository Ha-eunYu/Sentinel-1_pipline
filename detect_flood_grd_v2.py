# -*- coding: utf-8 -*-
"""
7/13+7/14 post-event GRD 전체(93FC/3C22/1A5A/FE43/8EF1/B126, 6프레임, 서로 다른
3개 패스)를 모두 합쳐 baseline과 비교하는 "최대한 많이 잡기" 버전.

detect_flood_grd.py(3프레임, 보수적 3중조건)와의 차이:
  - post 쪽 관측을 latest-wins가 아니라 **여러 관측 중 가장 어두운(dB가 가장
    낮은) 값을 픽셀별로 채택**한다. 관측마다 촬영 기하(승/하강)가 달라 같은
    수체도 각도에 따라 다르게 보일 수 있는데, 최솟값을 쓰면 "어느 한 패스
    에서라도 물처럼 보이면 물"로 간주해 탐지를 극대화한다.
  - 판정 단계를 3단계로 나눠 함께 출력한다 (느슨한 것부터):
      1) total_post_water   : post_db_min < DB_THRESHOLD (baseline 무관, 그냥
                               post 관측 중 하나라도 물로 보이는 모든 곳)
      2) new_flood_relaxed  : total_post_water AND NOT baseline_water
                               (하락폭 조건 없음 - "최대한 많이")
      3) new_flood_strict   : new_flood_relaxed AND diff <= DROP_THRESHOLD
                               (detect_flood_grd.py와 동일한 보수적 조건,
                               비교용으로 함께 계산)

분석 범위 (2026-07-16 변경): Korea_flood_AOI.geojson은 애초에 위성영상
"다운로드" 범위를 정하려던 용도였고, 홍수 모니터링 자체를 그 안으로 제한할
이유가 없다는 지적에 따라 AOI 클리핑을 없앴다. 대신 baseline 합성
(s1_rtc_db_composite_latest_pre.vrt, pre-event 5개 날짜 전체 촬영범위의
합집합)의 자체 격자를 그대로 분석 범위로 쓴다 - "위성영상이 확보되는 모든
지역"이 자연스럽게 이 범위가 된다 (baseline이 없는 곳은 애초에 신규침수
여부를 판단할 기준이 없으므로 어차피 valid=False로 제외됨).

baseline은 build_baseline_composite_grd.py가 만든 pre-event(~7/3) 최신관측
합성을 그대로 쓴다.

산출물 (downloads/water/, --dates 조합에 따라 파일명 접미사가 달라짐. 기본
7/13+7/14 조합은 기존 파일명 "20260713_14"를 유지하고, 그 외 조합은 날짜를
그대로 이어붙인다. 예: --dates 20260714 -> "..._20260714.tif"):
  diff_min_<접미사>_vs_baseline.tif   post_db_min - baseline_db (dB)
  flood_water_total_<접미사>.tif      1) 전체 post 수체 (baseline 무관)
  flood_water_relaxed_<접미사>.tif    2) 신규침수, 느슨(하락폭 조건 없음)
  flood_water_strict_<접미사>.tif     3) 신규침수, 보수적(하락폭 조건 포함)

실행:
    conda run -n s1_snappy python detect_flood_grd_v2.py                 # 7/13+7/14
    conda run -n s1_snappy python detect_flood_grd_v2.py --dates 20260714  # 7/14만
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

PROJECT_DIR = Path(__file__).resolve().parent
RTC_GRD_DIR = PROJECT_DIR / "downloads" / "rtc_grd"
OUT_DIR = PROJECT_DIR / "downloads" / "water"

BASELINE_VRT = RTC_GRD_DIR / "s1_rtc_db_composite_latest_pre.vrt"

DEFAULT_POST_DATES = ("20260713", "20260714")
SCENE_DATE_RE = re.compile(r"_(\d{8})T\d{6}_")


def output_paths(dates: tuple[str, ...], tag: str = "") -> tuple[Path, Path, Path, Path]:
    # 기본(7/13+7/14) 조합은 기존에 이미 커밋/보고된 파일명을 그대로 유지하고,
    # 그 외 날짜 조합(예: 7/14만)은 날짜를 이어붙인 접미사를 쓴다.
    # tag: 같은 post 날짜를 서로 다른 baseline으로 돌릴 때 파일명 충돌을 피하기
    # 위한 추가 접미사 (예: 동일궤도 비교 "vs0701").
    suffix = "20260713_14" if dates == DEFAULT_POST_DATES else "_".join(dates)
    if tag:
        suffix = f"{suffix}_{tag}"
    return (
        OUT_DIR / f"diff_min_{suffix}_vs_baseline.tif",
        OUT_DIR / f"flood_water_total_{suffix}.tif",
        OUT_DIR / f"flood_water_relaxed_{suffix}.tif",
        OUT_DIR / f"flood_water_strict_{suffix}.tif",
    )

DB_THRESHOLD_DEFAULT = -16.0
DROP_THRESHOLD_DEFAULT = -3.0
NODATA_U8 = 255
CHUNK_ROWS = 512  # baseline 자체 범위라 훨씬 커진 격자를 처리 - 여유 메모리 봐가며 조정


def post_scenes(dates: tuple[str, ...]) -> list[Path]:
    tifs = sorted(RTC_GRD_DIR.glob("*_rtc_db.tif"))
    out = [t for t in tifs if (m := SCENE_DATE_RE.search(t.name)) and m.group(1) in dates]
    if not out:
        raise FileNotFoundError(f"{dates} 날짜의 _rtc_db.tif가 없습니다.")
    return out


def reproject_chunk(src_path: Path, window_transform, win_width: int, win_height: int, dst_crs) -> np.ndarray:
    with rasterio.open(src_path) as src:
        dst = np.full((win_height, win_width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1), destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=window_transform, dst_crs=dst_crs,
            resampling=Resampling.bilinear, src_nodata=0.0, dst_nodata=np.nan,
        )
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="7/13+7/14 전체 프레임 vs baseline, 최대 탐지 버전")
    parser.add_argument("--db", type=float, default=DB_THRESHOLD_DEFAULT)
    parser.add_argument("--drop", type=float, default=DROP_THRESHOLD_DEFAULT)
    parser.add_argument(
        "--dates", default=",".join(DEFAULT_POST_DATES),
        help="쉼표로 구분한 post-event 날짜(YYYYMMDD). 기본은 7/13+7/14 전체",
    )
    parser.add_argument(
        "--baseline", default=str(BASELINE_VRT),
        help="비교 기준 baseline VRT 경로. 기본은 pre-event 합성. 동일궤도 "
             "비교 시 특정 pre 날짜 모자이크 VRT를 지정한다.",
    )
    parser.add_argument(
        "--tag", default="",
        help="출력 파일명 추가 접미사 (같은 post 날짜를 다른 baseline으로 돌릴 때 "
             "충돌 방지, 예: vs0701).",
    )
    args = parser.parse_args()

    baseline_vrt = Path(args.baseline)
    if not baseline_vrt.exists():
        raise FileNotFoundError(f"{baseline_vrt} 없음 - baseline VRT를 먼저 생성")

    dates = tuple(args.dates.split(","))
    scenes = post_scenes(dates)
    print(f"post-event 프레임 {len(scenes)}개: {[s.name[:35] for s in scenes]}")
    print(f"baseline: {baseline_vrt.name}")

    DIFF_OUT, TOTAL_OUT, RELAXED_OUT, STRICT_OUT = output_paths(dates, args.tag)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 분석 범위 = baseline 격자 ∩ post 씬들의 경계 합집합 (2026-07-20 최적화).
    # 이전에는 baseline 전체 격자(86395x72001)를 날짜와 무관하게 다 스캔해서,
    # 커버 면적이 좁은 날짜(예: 7/8 소형 프레임 1개)도 30분씩 걸렸다. post 씬이
    # 없는 곳은 어차피 valid=False이므로, 씬 경계 합집합으로 윈도우를 좁혀도
    # 결과(면적/마스크)는 동일하고 시간만 준다. 산출물 격자는 이 윈도우 기준.
    with rasterio.open(baseline_vrt) as ref:
        base_transform = ref.transform
        base_width = ref.width
        base_height = ref.height
        crs = ref.crs
        res_deg = abs(base_transform.a)

    sb = None  # (minx, miny, maxx, maxy) 합집합
    for scene in scenes:
        with rasterio.open(scene) as ds:
            b = (ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top)
        if sb is None:
            sb = b
        else:
            sb = (min(sb[0], b[0]), min(sb[1], b[1]), max(sb[2], b[2]), max(sb[3], b[3]))

    win = rasterio.windows.from_bounds(*sb, transform=base_transform)
    row0_g = max(0, int(win.row_off))
    col0_g = max(0, int(win.col_off))
    row1_g = min(base_height, int(win.row_off + win.height) + 1)
    col1_g = min(base_width, int(win.col_off + win.width) + 1)
    if row1_g <= row0_g or col1_g <= col0_g:
        print("post 씬들이 baseline 범위와 전혀 겹치지 않습니다 - 비교 불가")
        return

    width = col1_g - col0_g
    height = row1_g - row0_g
    transform = rasterio.windows.transform(
        rasterio.windows.Window(col0_g, row0_g, width, height), base_transform
    )
    print(f"분석 격자(baseline ∩ post 씬 합집합): {width} x {height} px, 해상도 {res_deg:.7f}도 (~10m)")
    print(f"임계값: post_min dB < {args.db} | 하락폭(strict) <= {args.drop}")

    m_per_deg = 111_320.0  # 위도 범위가 넓어 청크마다 중심위도로 재계산

    f32_profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": crs, "transform": transform, "nodata": np.nan,
        "compress": "DEFLATE", "tiled": True, "bigtiff": "IF_SAFER",
    }
    u8_profile = {**f32_profile, "dtype": "uint8", "nodata": NODATA_U8}

    n_valid_px = 0
    area_total_water = area_relaxed = area_strict = 0.0

    with rasterio.open(DIFF_OUT, "w", **f32_profile) as diff_dst, \
         rasterio.open(TOTAL_OUT, "w", **u8_profile) as total_dst, \
         rasterio.open(RELAXED_OUT, "w", **u8_profile) as relaxed_dst, \
         rasterio.open(STRICT_OUT, "w", **u8_profile) as strict_dst:

        for row0 in range(0, height, CHUNK_ROWS):
            nrows = min(CHUNK_ROWS, height - row0)
            win = rasterio.windows.Window(0, row0, width, nrows)
            win_transform = rasterio.windows.transform(win, transform)

            chunk_center_lat = transform.f + (row0 + nrows / 2) * transform.e
            px_area_km2 = (res_deg * m_per_deg) * (res_deg * m_per_deg * np.cos(np.radians(chunk_center_lat))) / 1e6

            post_min = np.full((nrows, width), np.nan, dtype="float32")
            for scene in scenes:
                chunk = reproject_chunk(scene, win_transform, width, nrows, crs)
                valid = np.isfinite(chunk)
                post_min = np.where(
                    valid & (np.isnan(post_min) | (chunk < post_min)), chunk, post_min
                )

            base_db = reproject_chunk(baseline_vrt, win_transform, width, nrows, crs)

            valid = np.isfinite(post_min) & np.isfinite(base_db)
            diff = np.where(valid, post_min - base_db, np.nan).astype("float32")

            baseline_water = valid & (base_db < args.db)
            total_water = valid & (post_min < args.db)
            relaxed = valid & total_water & (~baseline_water)
            strict = relaxed & (diff <= args.drop)

            diff_dst.write(diff, 1, window=win)
            total_dst.write(np.where(valid, total_water.astype("uint8"), NODATA_U8), 1, window=win)
            relaxed_dst.write(np.where(valid, relaxed.astype("uint8"), NODATA_U8), 1, window=win)
            strict_dst.write(np.where(valid, strict.astype("uint8"), NODATA_U8), 1, window=win)

            n_valid_px += int(valid.sum())
            area_total_water += int(total_water.sum()) * px_area_km2
            area_relaxed += int(relaxed.sum()) * px_area_km2
            area_strict += int(strict.sum()) * px_area_km2

    total_px = width * height
    print(f"\n두 시점 모두 유효(교차 커버리지): {100 * n_valid_px / total_px:.1f}%")
    print(f"1) 전체 post 수체(baseline 무관): {area_total_water:,.2f} km^2")
    print(f"2) 신규침수(느슨, 하락폭 조건 없음): {area_relaxed:,.2f} km^2")
    print(f"3) 신규침수(보수적, 하락폭 조건 포함): {area_strict:,.2f} km^2")
    print(f"\n저장: {DIFF_OUT.name}, {TOTAL_OUT.name}, {RELAXED_OUT.name}, {STRICT_OUT.name}")


if __name__ == "__main__":
    main()
