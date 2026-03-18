from __future__ import annotations

import pystac_client

from config import CDSEConfig


def open_cdse_stac_client(cfg: CDSEConfig | None = None) -> pystac_client.Client:
    cfg = cfg or CDSEConfig()
    return pystac_client.Client.open(cfg.stac_url)