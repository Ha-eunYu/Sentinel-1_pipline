"""river_water_area.py — 4대강 수면적 전년 동기 비교 CLI.

watercompare 패키지로 4대강(낙동강·섬진강·영산강·금강)의 올해(2026-07)와
작년 동기(2025-07) S1 수면적을 각각 산출해 증감을 표+CSV로 낸다.

실행
    python river_water_area.py                 # 전체 4대강 표 + CSV
    python river_water_area.py --basin nakdong  # 특정 강만
    python river_water_area.py --download       # 시점별 GeoJSON도 저장

사전조건: conda activate sar-gee (gee/environment.yml과 동일 env 재사용),
earthengine authenticate 완료.
"""
from __future__ import annotations

import argparse
import csv
import os

import ee

from watercompare import auth, config, export, water


def analyze_basin(name: str, cfg: dict) -> dict:
    """한 유역의 올해/작년 수면적과 증감을 반환."""
    aoi = ee.Geometry.Rectangle(cfg["aoi"])
    results = {}
    for period_key, (start, end) in config.PERIODS.items():
        print(f"  [{period_key}] {start} ~ {end}")
        img, mask = water.water_mask(aoi, start, end)
        results[period_key] = {
            "img": img, "mask": mask,
            "km2": round(water.area_km2(mask, aoi), 2),
        }

    this_km2 = results["this_year"]["km2"]
    last_km2 = results["last_year"]["km2"]
    delta = round(this_km2 - last_km2, 2)
    pct = round((delta / last_km2 * 100), 1) if last_km2 else float("nan")

    row = {
        "basin": name,
        "basin_kr": cfg["name_kr"],
        "this_year_km2": this_km2,
        "last_year_km2": last_km2,
        "delta_km2": delta,
        "delta_pct": pct,
    }
    return {"row": row, "aoi": aoi, "results": results}


def print_table(rows: list) -> None:
    hdr = ["basin_kr", "this_year_km2", "last_year_km2", "delta_km2", "delta_pct"]
    w = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in hdr}
    line = " | ".join(h.ljust(w[h]) for h in hdr)
    print("\n=== 4대강 수면적 비교 (2026-07 vs 2025-07) ===")
    print(line)
    print("-" * len(line))
    for r in rows:
        print(" | ".join(str(r[h]).ljust(w[h]) for h in hdr))


def main() -> None:
    ap = argparse.ArgumentParser(description="4대강 수면적 전년 동기 비교")
    ap.add_argument("--download", action="store_true", help="시점별 수면 GeoJSON도 저장")
    ap.add_argument("--basin", help="특정 유역만 처리(BASINS 키)")
    ap.add_argument("--csv", default=os.path.join(config.OUT_DIR, "river_water_area.csv"),
                    help="결과 CSV 경로")
    args = ap.parse_args()

    auth.init_ee()
    targets = {args.basin: config.BASINS[args.basin]} if args.basin else config.BASINS

    rows = []
    for name, cfg in targets.items():
        print(f"[처리 중] {cfg['name_kr']} ({name}) ...")
        res = analyze_basin(name, cfg)
        rows.append(res["row"])
        if args.download:
            for period_key, r in res["results"].items():
                path = os.path.join(config.OUT_DIR, f"{name}_{period_key}_water.geojson")
                export.export_water_vector(r["mask"], res["aoi"], path)
                print(f"  → 저장: {os.path.basename(path)}")

    print_table(rows)

    os.makedirs(config.OUT_DIR, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
        wtr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wtr.writeheader()
        wtr.writerows(rows)
    print(f"\nCSV 저장 → {args.csv}")


if __name__ == "__main__":
    main()
