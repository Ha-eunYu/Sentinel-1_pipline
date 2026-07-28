#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nk_crawl.py — 얇은 CLI 래퍼 (하위호환).

실제 구현은 ``nkcrawl/`` 패키지에 있다. 다음 세 방법 모두 동일하게 동작한다::

    python nk_crawl.py latest -n 3 --md      # 이 래퍼
    python -m nkcrawl latest -n 3 --md       # 패키지 모듈 실행
    from nkcrawl import spn_latest           # 라이브러리 import

패키지를 import 경로에 올리기 위해 이 파일의 폴더를 sys.path에 추가한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nkcrawl.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
