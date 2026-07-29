"""watercompare.auth — Earth Engine 초기화(대화식 / 서비스계정).

geeflood.auth와 동일 로직의 독립 사본(폴더 상대 import 원칙, gee/ 의존 없음).
"""
from __future__ import annotations

import ee

from . import config


def init_ee(project: str | None = None,
            sa_key: str | None = None,
            sa_email: str | None = None) -> None:
    """Earth Engine 초기화.

    서비스계정 키(sa_key)+이메일(sa_email)이 주어지면 비대화식으로,
    없으면 `earthengine authenticate` 로 저장된 토큰으로 초기화한다.
    인자를 생략하면 config.AUTH(환경변수 EE_PROJECT/EE_SA_KEY/EE_SA_EMAIL)를 쓴다.
    """
    project = project or config.AUTH["ee_project"]
    sa_key = sa_key or config.AUTH["sa_key"]
    sa_email = sa_email or config.AUTH["sa_email"]

    if sa_key and sa_email:
        creds = ee.ServiceAccountCredentials(sa_email, sa_key)
        ee.Initialize(creds, project=project)
    else:
        ee.Initialize(project=project)
