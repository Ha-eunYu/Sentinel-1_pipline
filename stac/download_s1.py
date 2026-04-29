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


def choose_download_url(
    *,
    zipper_url: Optional[str],
    product_href: Optional[str],
    allow_fallback: bool = True,
) -> str:

    if zipper_url:
        return zipper_url

    if allow_fallback and product_href:
        return product_href

    raise ValueError(
        "No valid download URL available. "
        f"zipper_url={zipper_url}, product_href={product_href}"
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


def download_odata_cdse(
    product_url: str,
    out_path: Path,
    access_token: str,
    *,
    chunk_size: int = 1024 * 1024,
    timeout: tuple[int, int] = (60, 600),
    overwrite: bool = False,
) -> Path:
# ) -> None:
    """
    URL 하나를 SAFE zip 파일로 스트리밍 다운로드한다.
    주로 CDSE zipper/OData product URL을 입력으로 사용한다.
    Parameters:
    - product_url: OData product URL 또는 zipper URL    
    - out_path: 다운로드한 파일을 저장할 경로 (예: /path/to/S1A_IW_SLC__1SDV_20221117.zip)
    - access_token: CDSE 접근 토큰 (get_cdse_access_token()로 발급)
    - chunk_size: 다운로드 스트림에서 읽는 청크 크기 (기본: 1MB)
    - timeout: (연결 타임아웃, 읽기 타임아웃) 초 단위 (기본: (30, 300))
    - overwrite: 이미 파일이 존재할 때 덮어쓸지 여부 (기본: False)
    Returns:
    - 다운로드된 파일의 경로 (Path 객체)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not overwrite:
        print(f"SKIP existing: {out_path}")
        return "skipped"

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
            timeout=timeout,
            allow_redirects=True,
        ) as r:
            print(f"HTTP status: {r.status_code}")
            r.raise_for_status()

            downloaded = 0
            last_print = time.time()

            with tmp_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if time.time() - last_print > 10:
                        print(f"  downloaded: {downloaded / 1024**3:.2f} GB")
                        last_print = time.time()

    tmp_path.rename(out_path)
    print(f"✅ Downloaded: {out_path}")
    return "downloaded", out_path