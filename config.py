from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(env_path: Optional[str] = None) -> None:
    """
    Load .env file.
    If env_path is None, try default local .env.
    """
    if env_path:
        load_dotenv(env_path)
        return

    # 기본 우선순위:
    # 1) 현재 작업 디렉터리 .env
    # 2) s2/.env  (사용자 현재 구조 반영)
    candidates = [
        Path(".env"),
        Path("../s2/.env"),
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p)
            return


@dataclass
class CDSEConfig:
    stac_url: str = os.getenv("CDSE_STAC_URL", "https://stac.dataspace.copernicus.eu/v1")
    cdse_client_id: Optional[str] = os.getenv("CDSE_CLIENT_ID")
    cdse_client_secret: Optional[str] = os.getenv("CDSE_CLIENT_SECRET")


@dataclass
class OutputConfig:
    out_dir: Path = Path("./downloads")