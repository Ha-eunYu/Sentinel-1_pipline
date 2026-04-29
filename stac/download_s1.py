from __future__ import annotations


import os
import time
from pathlib import Path
from typing import Optional

import requests


TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)


def get_cdse_access_token() -> str:
    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")

    if not username or not password:
        raise RuntimeError("CDSE_USERNAME / CDSE_PASSWORD not found in .env")

    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    r = requests.post(TOKEN_URL, data=data, timeout=(30, 120))
    r.raise_for_status()
    return r.json()["access_token"]


def download_odata_product(
    product_url: str,
    out_path: Path,
    access_token: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        print(f"SKIP existing: {out_path}")
        return

    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    print(f"Downloading OData product:")
    print(f"  {product_url}")
    print(f"  -> {out_path}")

    with requests.Session() as session:
        session.headers.update(headers)

        with session.get(
            product_url,
            stream=True,
            timeout=(60, 600),
            allow_redirects=True,
        ) as r:
            print(f"HTTP status: {r.status_code}")
            r.raise_for_status()

            downloaded = 0
            last_print = time.time()

            with tmp_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if time.time() - last_print > 10:
                        print(f"  downloaded: {downloaded / 1024**3:.2f} GB")
                        last_print = time.time()

    tmp_path.rename(out_path)
    print(f"✅ Downloaded: {out_path}")