# -*- coding: utf-8 -*-
"""
downloads/sentinel1_grd 의 GRD zip 전부를 순차적으로 GTC(dB) 처리하는 배치 러너.

RTC(batch_grd_rtc.py)와 대조용 — Terrain-Flattening을 생략한 GTC 산출물을
같은 폴더에 `_gtc_db.tif`로 나란히 만든다. 왜 이 비교를 하는지는
RTC_VS_GTC_KR.md 참고.

- 이미 산출물(downloads/rtc_grd/<씬ID>_gtc_db.tif)이 있는 씬은 건너뛰므로
  중간에 끊겨도, 혹은 NAS에서 zip이 계속 추가되는 중에도 다시 실행하면
  새로 들어온 것만 이어서 처리된다.
- 처리 전 입력 zip을 시스템 임시 폴더(C: SSD)로 복사해서 HDD 랜덤 읽기
  병목을 피하고, 처리 후 복사본은 삭제한다.
- 한 씬이 실패해도 나머지는 계속 진행한다.

실행:
    conda run -n s1_snappy python batch_grd_gtc.py
"""

from __future__ import annotations

from pathlib import Path

from s1.core.paths import GRD_DIR, RTC_GRD_DIR, rel
from s1.preprocess.batch_runner import run_batch
from s1.preprocess.prepro_grd_gpt import build_grd_gtc_graph


def main() -> None:
    zips = sorted(GRD_DIR.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"{rel(GRD_DIR)} 에 GRD zip이 없습니다.")

    print(f"대상 GRD: {len(zips)}개 -> {rel(RTC_GRD_DIR)} (GTC)")
    # RTC 배치와 동시에 돌 수 있다. 임시 폴더가 씬별로 격리돼 충돌하지 않는다.
    run_batch(zips, RTC_GRD_DIR,
              lambda src, out: build_grd_gtc_graph(src, out_dir=out),
              suffix="_gtc_db", tmp_prefix="gtc_", label="GTC 배치")


if __name__ == "__main__":
    main()
