# -*- coding: utf-8 -*-
"""C:의 FE43 GRD zip을 직접 RTC 처리 (F->C 복사 단계 없음). 출력은 F: rtc_grd."""
import sys
import time
from pathlib import Path

PROJECT = Path(r"f:\06_SAR_system\S1")
sys.path.insert(0, str(PROJECT))

from prepro_grd_gpt import build_grd_rtc_graph

ZIP = Path(r"C:\Users\chlwn\s1_grd_c") / (
    "S1D_IW_GRDH_1SDV_20260714T093103_20260714T093131_003668_0068CE_FE43_COG.zip"
)
OUT_DIR = PROJECT / "downloads" / "rtc_grd"
out_tif = OUT_DIR / f"{ZIP.stem}_rtc_db.tif"

if out_tif.exists():
    print(f"이미 존재: {out_tif.name}")
    sys.exit(0)

print(f"입력(C:): {ZIP}")
print(f"출력(F:): {out_tif}")
t0 = time.time()
graph = build_grd_rtc_graph(ZIP, out_dir=OUT_DIR)  # 파이프라인 기본값(Refined Lee)
graph.run(gpt_options=["-q", "8", "-c", "14G"])
print(f"완료 ({(time.time() - t0) / 60:.1f}분): {out_tif.name}")
