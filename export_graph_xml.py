# -*- coding: utf-8 -*-
"""
S1 SLC -> RTC(dB) 처리 그래프를 실행하지 않고 XML 파일로만 내보낸다.

생성된 XML은 두 가지 방법으로 사용할 수 있다:
  1) SNAP Desktop: Tools > GraphBuilder > Load 로 불러와 GUI에서 파라미터
     (입력 파일, AOI 등)를 바꿔가며 실행
  2) gpt CLI:  gpt graphs/s1_slc_to_rtc_db.xml  (bin 폴더가 PATH에 있을 때)

XML 안의 Read 노드 file 경로와 Subset 노드 geoRegion은 이 스크립트 실행 시점의
값(기본: downloads/sentinel1의 첫 zip, Korea_flood_AOI + 0.1도 여유)이 박히므로,
다른 씬/지역에 쓸 때는 SNAP GUI나 텍스트 편집기에서 그 두 값만 바꾸면 된다.

실행:
    conda run -n s1_snappy python export_graph_xml.py [SLC.zip 경로] [출력.xml 경로]
    # 인자 생략 시: downloads/sentinel1의 첫 zip -> graphs/s1_slc_to_rtc_db.xml
    # 전체 씬 그래프(AOI 서브셋 없이)를 원하면: --no-aoi
"""

from __future__ import annotations

import sys
from pathlib import Path

from prepro_gpt import aoi_wkt_from_geojson, build_rtc_graph

PROJECT_DIR = Path(__file__).resolve().parent


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--no-aoi"]
    use_aoi = "--no-aoi" not in sys.argv[1:]

    if len(args) > 0:
        slc_path = Path(args[0])
    else:
        candidates = sorted((PROJECT_DIR / "downloads/sentinel1").glob("*.zip"))
        if not candidates:
            raise FileNotFoundError("downloads/sentinel1 에 SLC(.zip)이 없습니다.")
        slc_path = candidates[0]

    # SNAP Desktop에서 열어도 입력을 찾을 수 있게 절대경로로 기록
    slc_path = slc_path.resolve()

    out_xml = Path(args[1]) if len(args) > 1 else PROJECT_DIR / "graphs" / "s1_slc_to_rtc_db.xml"

    aoi_wkt = None
    if use_aoi:
        aoi_wkt = aoi_wkt_from_geojson(PROJECT_DIR / "geojson" / "Korea_flood_AOI.geojson")

    graph = build_rtc_graph(
        slc_path,
        out_dir=PROJECT_DIR / "downloads/rtc",
        aoi_wkt=aoi_wkt,
    )

    out_xml.parent.mkdir(parents=True, exist_ok=True)
    graph.save_graph(str(out_xml))

    print(f"그래프 XML 저장: {out_xml}")
    print(f"  입력 SLC : {slc_path}")
    print(f"  AOI 서브셋: {'사용 (' + aoi_wkt[:60] + '...)' if aoi_wkt else '없음 (전체 씬)'}")
    print("SNAP Desktop에서: Tools > GraphBuilder > Load 로 불러오세요.")


if __name__ == "__main__":
    main()
