from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    # default_factory로 감싸서 인스턴스 생성 시점에 os.getenv를 평가한다.
    # (모듈 import 시점에 평가하면 그 뒤 load_env(".env")로 채운 값이 반영되지 않음)
    stac_url: str = field(
        default_factory=lambda: os.getenv(
            "CDSE_STAC_URL", "https://stac.dataspace.copernicus.eu/v1"
        )
    )
    cdse_client_id: Optional[str] = field(default_factory=lambda: os.getenv("CDSE_CLIENT_ID"))
    cdse_client_secret: Optional[str] = field(
        default_factory=lambda: os.getenv("CDSE_CLIENT_SECRET")
    )


@dataclass
class OutputConfig:
    out_dir: Path = Path("./downloads")