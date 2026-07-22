# -*- coding: utf-8 -*-
"""FE43 GRD를 C: 드라이브로 직접 다운로드 (F: 용량 절약, 처리도 C:에서)."""
import sys
from pathlib import Path

PROJECT = Path(r"f:\06_SAR_system\S1")
sys.path.insert(0, str(PROJECT))

from config import load_env
from stac.download_s1 import download_odata_cdse_with_retry

load_env(PROJECT / ".env")

URL = "https://download.dataspace.copernicus.eu/odata/v1/Products(57c29522-037e-46fb-9096-96793b67d3d7)/$value"
OUT = Path(r"C:\Users\chlwn\s1_grd_c") / (
    "S1D_IW_GRDH_1SDV_20260714T093103_20260714T093131_003668_0068CE_FE43_COG.zip"
)

status, path = download_odata_cdse_with_retry(URL, OUT, max_retries=5)
print(f"결과: {status} -> {path}")
