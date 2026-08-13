"""레이오버·섀도 마스크만 뽑는 경량 그래프 — 기존 RTC 산출물은 건드리지 않는다.

왜 필요한가
-----------
Terrain-Flattening은 **방사보정**이다. 밝기를 지형으로 정규화할 뿐, 그 화소가
못 쓰는 화소라고 **표시하지 않는다**. 그래서 섀도가 값으로 남는데, 실측상
정상역보다 5~7 dB 어둡고 **물 오탐 위험이 10배**다.

    구간        SNAP 유효   SNAP 중앙     −20 dB 미만
    정상            99%     −13.2 dB          1.8%
    layover        100%     −14.6 dB          0.4%   ← 원래 밝아 안전
    **shadow**   86~93%   **−16.8 dB**   **14.6~23.8%**   ← 위험

OPERA는 섀도의 90% 이상을 nodata로 뺀다. 우리 산출물은 값을 남기므로 같은
처리를 해야 한다. 상세: gee/ASF_HyP3/RTC_VS_OPERA_QUANT_KR.md §3-a

왜 별도 경량 그래프인가
-----------------------
마스크는 **DEM + 궤도 기하**만으로 정해진다 — 방사정보가 전혀 안 들어간다.
그래서 Calibration·ThermalNoise·Speckle·Terrain-Flattening을 전부 건너뛸 수
있고, **기존 dB 산출물 34개를 재처리하지 않아도** 된다.

    정식 그래프   Read → Orbit → TNR → Calib → Speckle → TF → TC → dB
    이 그래프     Read → Orbit → TC(mask only)

`prepro_grd_gpt.py`에는 `saveLayoverShadowMask="true"`를 이미 넣었으므로
**앞으로 처리하는 것은 자동으로 마스크가 붙는다.** 이 스크립트는 그 전에 만든
것들을 메우는 용도다.

격자 정합
---------
같은 `pixelSpacingInMeter`·같은 DEM 파라미터를 쓰면 dB 산출물과 **같은 격자**로
나온다. 다르면 소용없으므로 기본값을 정식 그래프와 맞춰 뒀다.

마스크 값 (SNAP `layover_shadow_mask`)
--------------------------------------
    0  정상
    1  layover
    2  shadow
    3  layover + shadow

⚠ **OPERA와 비트 배정이 다르다**(OPERA는 1=shadow, 2=layover). 섞어 쓰지 말 것.

실행
----
    conda run -n s1_snappy python make_ls_mask.py
    conda run -n s1_snappy python make_ls_mask.py --month 202507
    conda run -n s1_snappy python make_ls_mask.py --only 4458,0ABD
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import time
from pathlib import Path

# prepro_grd_gpt를 import하면 그 안에서 SNAP PATH 설정 + esa_snappy 초기화가
# 함께 일어난다. 그래서 이 import가 esa_snappy 사용의 전제다.
from s1.preprocess.prepro_grd_gpt import _terrain_dem_params

GRD_DIR = Path("downloads/sentinel1_grd")
DATE_RE = re.compile(r"_(\d{8})T\d{6}_")


def scene_date(p: Path) -> str:
    m = DATE_RE.search(p.name)
    return m.group(1) if m else "00000000"


def build_mask_graph(
    grd_path: str | Path,
    out_dir: str | Path,
    *,
    polarization: str = "VH",
    dem_name: str = "Copernicus 30m Global DEM",
    external_dem_file: str | Path | None = None,
    external_dem_nodata: float = -9999.0,
    external_dem_apply_egm: bool = True,
    pixel_spacing_m: float = 10.0,
    out_tag: str = "_lsmask",
):
    """레이오버·섀도 마스크만 내는 최소 그래프.

    Terrain-Correction은 소스 밴드가 하나는 있어야 하므로 원 밴드를 그대로
    통과시킨다(`saveSelectedSourceBand="true"`). 산출물에 밴드가 둘 생기며,
    쓰는 것은 `layover_shadow_mask` 쪽이다.
    """
    from esa_snappy.snapista import Graph, Operator

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dem_params = _terrain_dem_params(
        dem_name, external_dem_file, external_dem_nodata, external_dem_apply_egm
    )

    g = Graph()
    g.add_node(Operator("Read", file=str(grd_path)), node_id="Read")

    # 궤도는 필수다 — 마스크가 조사 기하로 정해지므로 정밀궤도가 있어야 한다
    g.add_node(
        Operator(
            "Apply-Orbit-File",
            orbitType="Sentinel Precise (Auto Download)",
            polyDegree="3",
            continueOnFail="false",
        ),
        node_id="Apply-Orbit-File",
        source="Read",
    )

    # 한 편파만 남겨 연산량을 줄인다. 마스크는 편파와 무관하지만 밴드 수가
    # 줄면 TC가 빨라진다.
    #
    # 밴드명은 실측으로 확인했다(2026-08-02, S1C GRD 1SDV):
    #   ['Amplitude_VH', 'Intensity_VH', 'Amplitude_VV', 'Intensity_VV']
    # 이름이 틀리면 BandSelect가 **예외 없이 빈 결과**를 낸다 — 이 프로젝트의
    # 단골 함정이라 확인 결과를 남긴다. 단일편파(1SSV/1SSH) 제품에는 해당
    # 편파만 있으므로, 없는 편파를 요구하면 여기서 걸린다.
    g.add_node(
        Operator("BandSelect", sourceBands=f"Amplitude_{polarization}"),
        node_id="BandSelect",
        source="Apply-Orbit-File",
    )

    g.add_node(
        Operator(
            "Terrain-Correction",
            pixelSpacingInMeter=str(float(pixel_spacing_m)),
            imgResamplingMethod="NEAREST_NEIGHBOUR",   # 마스크는 범주형이다
            demResamplingMethod="BILINEAR_INTERPOLATION",
            # ⚠ SNAP은 출력 밴드를 **최소 하나** 요구한다. `false`로 두면
            #   "Please select output band for terrain corrected image"로 죽는다.
            #   그래서 원 밴드를 통과시키고, 쓰는 것은 2번 밴드(마스크)다.
            saveSelectedSourceBand="true",
            saveLayoverShadowMask="true",
            **dem_params,
        ),
        node_id="Terrain-Correction",
        source="BandSelect",
    )

    g.add_node(
        Operator(
            "Write",
            file=str(out_dir / f"{Path(grd_path).stem}{out_tag}.tif"),
            formatName="GeoTIFF-BigTIFF",
        ),
        node_id="Write",
        source="Terrain-Correction",
    )
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default="downloads/ls_mask")
    ap.add_argument("--month", default="", help="촬영일 접두사 (예: 202607). 생략하면 전부")
    ap.add_argument("--only", default="", help="쉼표로 구분한 씬 ID(4자리)")
    ap.add_argument("--pol", default="VH", choices=["VV", "VH"])
    ap.add_argument("--pixel-spacing", type=float, default=10.0,
                    help="dB 산출물과 **같아야** 격자가 맞는다")
    ap.add_argument("--gpt-q", default="8")
    ap.add_argument("--gpt-c", default="7G")
    ap.add_argument("--oldest-first", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zips = sorted(GRD_DIR.glob("*.zip"))
    if args.month:
        zips = [z for z in zips if scene_date(z).startswith(args.month)]
    if args.only:
        want = {s.strip().upper() for s in args.only.split(",") if s.strip()}
        zips = [z for z in zips if any(f"_{s}" in z.name.upper() for s in want)]
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR} 에 대상 GRD zip이 없습니다.")
    zips.sort(key=scene_date, reverse=not args.oldest_first)

    todo = [z for z in zips
            if not (out_dir / f"{z.stem}_lsmask.tif").exists()]
    print(f"대상 {len(zips)}개 · 미처리 {len(todo)}개 "
          f"({'오래된순' if args.oldest_first else '최신순'})", flush=True)

    for i, z in enumerate(todo, 1):
        t0 = time.time()
        # 입력을 SSD 임시폴더로 복사 — 원본 파일명을 유지해 산출물 이름을 지킨다
        tmp = Path(tempfile.mkdtemp(prefix="lsmask_"))
        try:
            local = tmp / z.name
            shutil.copy2(z, local)
            g = build_mask_graph(local, out_dir,
                                 polarization=args.pol,
                                 pixel_spacing_m=args.pixel_spacing)
            # ⚠ gpt 옵션을 안 넘기면 타일 캐시가 기본값이라 **쓰다가 죽는다**
            #   (실측 2026-08-02: 전 밴드 0인 잘린 파일이 남았고 예외도 없었다).
            #   정식 배치(batch_grd_rtc_frost.py)와 같은 값을 준다.
            g.run(gpt_options=["-q", args.gpt_q, "-c", args.gpt_c])
            print(f"[{i}/{len(todo)}] {z.stem[-9:]} "
                  f"{time.time() - t0:,.0f}s", flush=True)
        except Exception as e:                       # noqa: BLE001
            print(f"[{i}/{len(todo)}] {z.stem[-9:]} 실패: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n산출: {out_dir}")
    print("검증: gee/Korea_WaterDetection_2025_2026/ls_mask_verify.py "
          "(OPERA mask와 겹침률 대조)")


if __name__ == "__main__":
    main()
