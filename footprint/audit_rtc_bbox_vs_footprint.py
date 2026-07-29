# -*- coding: utf-8 -*-
"""
처리 완료된 RTC 산출물의 **bbox 판정 vs 실제 footprint 판정** 차이를 일괄 감사한다.

배경 (S1_PIPELINE_REVIEW_KR.md ②)
---------------------------------
SNAP Terrain-Correction을 거친 `*_rtc_db.tif`는 지도투영 north-up 래스터라
geotransform 회전항이 0이다. 즉 래스터 범위 = 축정렬 bbox이고, SAR 프레임의
실제 기울어진 평행사변형 형상은 **파일에 남지 않는다**. 이 래스터 범위로
"이 씬이 어디를 찍었나"를 판정하면 실제로 찍지 않은 삼각형 여백까지
촬영지역으로 계상된다(footprint_aoi.py 모듈 설명 참조).

이 스크립트는 원본 zip의 `manifest.safe`에서 진짜 footprint를 복원해,
같은 씬의 RTC bbox와 나란히 경계 폴리곤과 대조한다. 산출:

  footprint/rtc_bbox_vs_footprint_audit.csv
      씬별 bbox/footprint 겹침비율 (한반도·북한·남한) + bbox 오판 여부
  footprint/rtc_phantom_land_audit.csv
      씬별 "유령 육지" — bbox는 찍었다고 주장하나 footprint는 안 찍은 육지 km²
      = area(bbox ∩ 육지) − area(footprint ∩ 육지)

원본 zip이 이미 삭제된 씬은 footprint 복원이 불가하므로 `zip=False`로 표시하고
비교에서 제외한다(그 씬들은 CDSE STAC 재조회가 유일한 복원 경로다).

의존성: rasterio + shapely + numpy. 면적은 pyproj 없이 프로젝트 자체 구면
면적 함수(water_area_report._polygon_area_m2)를 재사용한다.

실행(저장소 루트에서):
    conda run -n s1_pipeline python footprint/audit_rtc_bbox_vs_footprint.py
    conda run -n s1_pipeline python footprint/audit_rtc_bbox_vs_footprint.py \\
        --rtc-dir downloads/rtc_grd_frost
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path

import rasterio
from shapely.geometry import Polygon, shape

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from footprint import bbox_to_polygon, load_boundary_union  # noqa: E402
from water_area_report import _polygon_area_m2  # noqa: E402

GEOJSON_DIR = PROJECT_DIR / "geojson"

# SAFE 씬 ID (CDSE GRD는 _COG로 끝남). S1A~S1D 모두 대응.
SCENE_RE = re.compile(r"(S1[A-D]_IW_GRD[HM]_\S+?_COG)")


def km2(geom) -> float:
    """shapely (Multi)Polygon의 구면 면적(km²). pyproj 불필요."""
    if geom.is_empty:
        return 0.0
    total = 0.0
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon":
            continue
        rings = [list(p.exterior.coords)] + [list(r.coords) for r in p.interiors]
        total += _polygon_area_m2(rings)
    return total / 1e6


def manifest_footprint(zip_path: Path) -> Polygon | None:
    """SAFE zip의 manifest.safe에서 gml:coordinates(lat,lon 쌍)를 읽어
    실제 촬영 footprint 폴리곤으로 반환."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith("manifest.safe")]
        if not names:
            return None
        xml = zf.read(names[0]).decode("utf-8", "ignore")
    m = re.search(r"<gml:coordinates>(.*?)</gml:coordinates>", xml, re.S)
    if not m:
        return None
    # manifest는 "lat,lon" 순서 -> GeoJSON 규약(lon,lat)으로 뒤집는다
    pts = []
    for tok in m.group(1).split():
        lat, lon = tok.split(",")
        pts.append((float(lon), float(lat)))
    return Polygon(pts) if len(pts) >= 3 else None


def index_zips(download_root: Path) -> dict[str, Path]:
    """다운로드 폴더 전체에서 씬ID -> zip 경로 색인."""
    zips: dict[str, Path] = {}
    for z in download_root.glob("**/*.zip"):
        m = SCENE_RE.match(z.stem)
        if m:
            zips[m.group(1)] = z
    return zips


def ratio(geom, boundary) -> float:
    """geom 면적 대비 경계와의 교집합 비율(경위도 평면 근사, 0.0~1.0)."""
    if geom is None or geom.area == 0:
        return 0.0
    return geom.intersection(boundary).area / geom.area


def main() -> None:
    ap = argparse.ArgumentParser(description="RTC bbox vs 실제 footprint 일괄 감사")
    ap.add_argument("--rtc-dir", type=Path,
                    default=PROJECT_DIR / "downloads" / "rtc_grd")
    ap.add_argument("--suffix", default="rtc_db", help="입력 파일명 접미사")
    ap.add_argument("--download-root", type=Path,
                    default=PROJECT_DIR / "downloads",
                    help="원본 zip을 찾을 최상위 폴더")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()

    peninsula = load_boundary_union(GEOJSON_DIR / "Korea_Peninsula.geojson")
    nk = load_boundary_union(GEOJSON_DIR / "NK.geojson")
    sk = load_boundary_union(GEOJSON_DIR / "South_Korea.geojson")

    zips = index_zips(args.download_root)
    tifs = sorted(args.rtc_dir.glob(f"*_{args.suffix}.tif"))
    if not tifs:
        raise SystemExit(f"{args.rtc_dir}에 *_{args.suffix}.tif 가 없습니다.")
    print(f"RTC {len(tifs)}개 / 원본 zip 색인 {len(zips)}개\n")

    hdr = (f"{'씬':<6}{'날짜':<10}{'회전항':>7}{'bbox한':>9}{'fp한':>8}"
           f"{'유령육지':>10}{'유령%':>7}")
    print(hdr)
    print("-" * len(hdr))

    overlap_rows, land_rows = [], []
    n_rot, n_norec, n_fpos = 0, 0, 0

    for t in tifs:
        m = SCENE_RE.match(t.name)
        sid = m.group(1) if m else None
        tag = sid.split("_")[-2] if sid else "?"
        dm = re.search(r"_(\d{8})T", t.name)
        date = dm.group(1) if dm else "?"

        with rasterio.open(t) as d:
            tr, b = d.transform, d.bounds
        rotated = (tr.b != 0) or (tr.d != 0)
        n_rot += rotated
        bpoly = shape(bbox_to_polygon([b.left, b.bottom, b.right, b.top]))

        z = zips.get(sid)
        fp = manifest_footprint(z) if z else None

        r = {"scene": tag, "date": date, "zip": bool(z), "rotated": rotated,
             "bbox_kp": round(ratio(bpoly, peninsula), 4),
             "bbox_nk": round(ratio(bpoly, nk), 4),
             "bbox_sk": round(ratio(bpoly, sk), 4)}

        if fp is None:
            n_norec += 1
            overlap_rows.append({**r, "fp_kp": "", "fp_nk": "", "fp_sk": "",
                                 "bbox_false_positive": ""})
            print(f"{tag:<6}{date:<10}{str(rotated):>7}{r['bbox_kp']*100:>8.2f}%"
                  f"{'  원본 zip 없음':>26}")
            continue

        fp_kp = ratio(fp, peninsula)
        # bbox는 겹친다고 하는데 footprint는 0% = 촬영지역 오판
        fpos = r["bbox_kp"] > 0 and fp_kp == 0
        n_fpos += fpos
        overlap_rows.append({**r, "fp_kp": round(fp_kp, 4),
                             "fp_nk": round(ratio(fp, nk), 4),
                             "fp_sk": round(ratio(fp, sk), 4),
                             "bbox_false_positive": fpos})

        bl = km2(bpoly.intersection(peninsula))
        fl = km2(fp.intersection(peninsula))
        phantom = km2(bpoly.difference(fp).intersection(peninsula))
        pct = 100 * phantom / bl if bl else 0.0
        land_rows.append({"scene": tag, "date": date,
                          "bbox_land_km2": round(bl, 1), "fp_land_km2": round(fl, 1),
                          "phantom_land_km2": round(phantom, 1),
                          "phantom_pct_of_bbox_land": round(pct, 1)})
        print(f"{tag:<6}{date:<10}{str(rotated):>7}{r['bbox_kp']*100:>8.2f}%"
              f"{fp_kp*100:>7.2f}%{phantom:>10,.0f}{pct:>6.1f}%"
              f"{'  <= bbox 오판' if fpos else ''}")

    for rows, name in ((overlap_rows, "rtc_bbox_vs_footprint_audit.csv"),
                       (land_rows, "rtc_phantom_land_audit.csv")):
        out = args.out_dir / name
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"CSV: {out}")

    tot_b = sum(r["bbox_land_km2"] for r in land_rows)
    tot_p = sum(r["phantom_land_km2"] for r in land_rows)
    print(f"\n요약: RTC {len(tifs)}개 | geotransform 회전항 보존 {n_rot}개 "
          f"(0이면 전부 bbox로 소실) | footprint 복원 가능 {len(land_rows)}개 / "
          f"원본 소실 {n_norec}개 | bbox 오판 {n_fpos}개")
    if tot_b:
        print(f"      bbox가 촬영했다고 주장하는 한반도 육지 {tot_b:,.0f} km² 중 "
              f"실제 미촬영 {tot_p:,.0f} km² ({100*tot_p/tot_b:.1f}%)")


if __name__ == "__main__":
    main()
