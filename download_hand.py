# -*- coding: utf-8 -*-
"""
홍수 AOI를 덮는 GLO-30 HAND(Height Above Nearest Drainage) 타일 다운로드.

HAND는 "가장 가까운 하천(배수로)으로부터의 상대 고도"로, SAR 홍수 탐지에서
오탐 제거의 핵심 보조 데이터다: 물처럼 어두운 픽셀이라도 HAND가 높으면
(하천에서 수십 m 위 지형) 침수일 수 없으므로 걸러낸다 (레이더 그림자,
아스팔트 등 오탐 제거). 보통 HAND < 5~15 m 조건을 수체 후보에 결합한다.

데이터: ASF GLO-30 HAND (Copernicus GLO-30 DEM 유도, 30 m, AWS Open Data,
인증 불필요). 타일은 Copernicus DEM과 같은 1도x1도 격자이며 이름 규칙:
  https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_<N|S>xx_00_<E|W>xxx_00_HAND.tif

실행:
    conda run -n s1_snappy python download_hand.py
    # AOI(Korea_flood_AOI + 0.1도)를 덮는 타일들을 downloads/hand/ 에 받고
    # downloads/hand/hand_aoi.vrt 모자이크 생성
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent
AOI_GEOJSON = PROJECT_DIR / "geojson" / "Korea_flood_AOI.geojson"
OUT_DIR = PROJECT_DIR / "downloads" / "hand"
MARGIN_DEG = 0.1

URL_TMPL = (
    "https://glo-30-hand.s3.amazonaws.com/v1/2021/"
    "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_HAND.tif"
)


def aoi_bbox() -> tuple[float, float, float, float]:
    with open(AOI_GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    geom = gj["features"][0]["geometry"] if "features" in gj else gj.get("geometry", gj)
    coords = geom["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (
        min(lons) - MARGIN_DEG,
        min(lats) - MARGIN_DEG,
        max(lons) + MARGIN_DEG,
        max(lats) + MARGIN_DEG,
    )


def tile_name(lat: int, lon: int) -> tuple[str, str]:
    lat_s = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
    lon_s = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
    return lat_s, lon_s


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    min_lon, min_lat, max_lon, max_lat = aoi_bbox()
    print(f"AOI bbox(+{MARGIN_DEG}도): lon {min_lon:.3f}~{max_lon:.3f}, lat {min_lat:.3f}~{max_lat:.3f}")

    tiles = []
    for lat in range(math.floor(min_lat), math.floor(max_lat) + 1):
        for lon in range(math.floor(min_lon), math.floor(max_lon) + 1):
            tiles.append(tile_name(lat, lon))

    downloaded = []
    for lat_s, lon_s in tiles:
        url = URL_TMPL.format(lat=lat_s, lon=lon_s)
        out = OUT_DIR / Path(url).name
        if out.exists() and out.stat().st_size > 0:
            print(f"건너뜀 (이미 있음): {out.name}")
            downloaded.append(out)
            continue

        print(f"다운로드: {url}")
        r = requests.get(url, stream=True, timeout=120)
        if r.status_code != 200:
            # 바다만 있는 타일 등은 존재하지 않을 수 있음
            print(f"  -> 없음 (HTTP {r.status_code}), 건너뜀")
            continue
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        print(f"  -> 저장: {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
        downloaded.append(out)

    if not downloaded:
        raise RuntimeError("받은 HAND 타일이 없습니다.")

    if shutil.which("gdalbuildvrt") is None:
        print("gdalbuildvrt 없음 - VRT 생략 (개별 타일만 저장됨)")
        return

    vrt = OUT_DIR / "hand_aoi.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(vrt)] + [str(p) for p in downloaded],
        check=True,
        capture_output=True,
    )
    print(f"\n완료: 타일 {len(downloaded)}개, 모자이크 {vrt}")
    print("사용 예: 수체 후보(dB 임계값) AND (HAND < 5~15 m) 로 오탐 제거")


if __name__ == "__main__":
    main()
