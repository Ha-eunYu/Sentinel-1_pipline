# -*- coding: utf-8 -*-
"""
NGII(국토지리정보원) DEM을 SNAP의 External DEM으로 바로 쓸 수 있게 변환한다.

SNAP의 Terrain-Flattening / Terrain-Correction external DEM은 WGS84
경위도(EPSG:4326) GeoTIFF를 기대하므로, NGII DEM(보통 EPSG:5186 등 투영좌표계)을
그대로 넣으면 좌표가 어긋나거나 읽기 오류가 날 수 있다. 이 스크립트는:

  1) 입력 DEM의 좌표계를 EPSG:4326으로 재투영 (gdalwarp)
  2) NoData 값을 지정된 값으로 통일
  3) GeoTIFF로 저장

gdal(gdalwarp, gdalinfo) CLI가 PATH에 있어야 한다 (env/environment_snappy.yml의
gdal 패키지로 설치됨).

사용 예:
    python prepare_ngii_dem.py \
        --input ngii_dem_5m.img \
        --output ngii_dem_5m_wgs84.tif \
        --src-epsg 5186 \
        --src-nodata -9999 \
        --dst-nodata -9999
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def require_gdal() -> None:
    for tool in ("gdalwarp", "gdalinfo"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"'{tool}'을 찾을 수 없습니다. GDAL이 설치된 환경(예: s1_snappy conda env)에서 "
                "실행해주세요."
            )


def reproject_to_wgs84(
    input_path: Path,
    output_path: Path,
    *,
    src_epsg: int | None,
    src_nodata: float | None,
    dst_nodata: float,
    resampling: str = "bilinear",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["gdalwarp", "-overwrite", "-of", "GTiff", "-t_srs", "EPSG:4326", "-r", resampling]

    if src_epsg is not None:
        cmd += ["-s_srs", f"EPSG:{src_epsg}"]
    if src_nodata is not None:
        cmd += ["-srcnodata", str(src_nodata)]
    cmd += ["-dstnodata", str(dst_nodata)]

    cmd += [str(input_path), str(output_path)]

    print("실행:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def print_gdalinfo(path: Path) -> None:
    print(f"\n=== gdalinfo: {path} ===")
    subprocess.run(["gdalinfo", "-stats", str(path)], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NGII DEM -> SNAP External DEM (EPSG:4326 GeoTIFF)")
    parser.add_argument("--input", required=True, help="원본 NGII DEM 경로 (.img/.tif 등 GDAL 지원 포맷)")
    parser.add_argument("--output", required=True, help="변환 결과 GeoTIFF 경로")
    parser.add_argument(
        "--src-epsg",
        type=int,
        default=None,
        help="입력 DEM의 EPSG 코드 (파일에 좌표계 정보가 없을 때만 지정, 예: NGII 흔한 값 5186)",
    )
    parser.add_argument(
        "--src-nodata",
        type=float,
        default=None,
        help="입력 DEM의 NoData 값 (모르면 생략하고 gdalinfo로 먼저 확인 권장)",
    )
    parser.add_argument("--dst-nodata", type=float, default=-9999.0, help="출력 DEM의 NoData 값 (기본 -9999)")
    parser.add_argument(
        "--resampling",
        default="bilinear",
        choices=["near", "bilinear", "cubic", "cubicspline"],
        help="재투영 리샘플링 방법 (표고값이므로 기본 bilinear 권장)",
    )
    parser.add_argument(
        "--skip-info",
        action="store_true",
        help="변환 후 gdalinfo 출력 생략",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_gdal()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 DEM을 찾을 수 없습니다: {input_path}")

    output_path = Path(args.output)

    if args.src_nodata is None:
        print(f"--src-nodata가 지정되지 않았습니다. 먼저 원본 NoData 값을 확인하세요:\n")
        print_gdalinfo(input_path)
        print(
            "\n위 출력에서 'NoData Value'를 확인한 뒤 --src-nodata로 다시 실행하세요 "
            "(값이 없으면 생략 가능)."
        )
        return

    reproject_to_wgs84(
        input_path,
        output_path,
        src_epsg=args.src_epsg,
        src_nodata=args.src_nodata,
        dst_nodata=args.dst_nodata,
        resampling=args.resampling,
    )

    print(f"\n완료: {output_path}")

    if not args.skip_info:
        print_gdalinfo(output_path)

    print(
        "\n이제 prepro.py의 terrain_flattening()/terrain_correction() 안에서 "
        "External DEM 주석을 풀고 externalDEMFile에 위 출력 경로를 넣으면 됩니다:\n"
        f'  params.put("externalDEMFile", "{output_path}")\n'
        f'  params.put("externalDEMNoDataValue", {args.dst_nodata})'
    )


if __name__ == "__main__":
    main()
