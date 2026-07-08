from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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

def make_session():
    session = requests.Session()

    retry = Retry(
        total=10,
        connect=5,
        read=5,
        backoff_factor=10,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)

    return session

from typing import Literal

DownloadStatus = Literal["downloaded", "skipped"]

def download_odata_cdse(
    product_url: str,
    out_path: Path,
    access_token: str,
    *,
    chunk_size: int = 1024 * 1024,
    timeout: tuple[int, int] = (60, 600),
    overwrite: bool = False,
) -> tuple[DownloadStatus, Path]:
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

    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

        # ⭐ 이어받기 핵심
    downloaded = 0
    if tmp_path.exists():
        downloaded = tmp_path.stat().st_size
        headers["Range"] = f"bytes={downloaded}-"
        print(f"Resume from {downloaded / 1024**3:.2f} GB")

    print(f"Downloading OData product:")
    print(f"  {product_url}")
    print(f"  -> {out_path}")

    if out_path.exists() and not overwrite:
        print(f"SKIP existing: {out_path}")
        return "skipped", out_path

    with make_session() as session:
        session.headers.update(headers)

        with session.get(
            product_url,
            stream=True,
            timeout=timeout,
            allow_redirects=True,
        ) as r:
            
            print(f"HTTP status: {r.status_code}")
        
            # 206 = partial content (resume 성공)
            if r.status_code not in (200, 206):
                r.raise_for_status()

            # mode = "ab" if downloaded > 0 else "wb"
            if downloaded > 0 and r.status_code == 200:
                print("Server ignored Range request. Restarting download.")
                tmp_path.unlink(missing_ok=True)
                downloaded = 0
                mode = "wb"
            elif r.status_code == 206:
                mode = "ab"
            else:
                mode = "wb"

            # downloaded = 0
            last_print = time.time()

            with tmp_path.open(mode) as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if time.time() - last_print > 10:
                        print(f"  downloaded: {downloaded / 1024**3:.2f} GB")
                        last_print = time.time()

    # tmp_path.rename(out_path)
    tmp_path.replace(out_path)
    print(f"✅ Downloaded: {out_path}")
    return "downloaded", out_path


def download_odata_cdse_with_retry(
    product_url: str,
    out_path: Path,
    *,
    max_retries: int = 3,
    chunk_size: int = 1024 * 1024,
    timeout: tuple[int, int] = (60, 600),
) -> tuple[DownloadStatus, Path]:
    """시도할 때마다 access token을 새로 발급받아 다운로드한다.

    CDSE access token은 수명이 짧아(대개 10분), 여러 개를 순서대로 받는
    배치 작업에서는 앞선 파일들을 받는 동안 토큰이 만료되어 뒤쪽 항목이
    401로 실패할 수 있다. 항목 하나를 받을 때마다 토큰을 새로 받고, 실패하면
    (네트워크 타임아웃 포함) 새 토큰으로 재시도한다. 이미 받아둔 .part는
    이어받기로 재사용된다.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        access_token = get_cdse_access_token()
        try:
            return download_odata_cdse(
                product_url,
                out_path,
                access_token,
                chunk_size=chunk_size,
                timeout=timeout,
            )
        except Exception as e:
            last_error = e
            print(f"다운로드 시도 {attempt}/{max_retries} 실패: {e}")

    raise RuntimeError(f"{max_retries}번 시도 후 다운로드 실패: {out_path}") from last_error