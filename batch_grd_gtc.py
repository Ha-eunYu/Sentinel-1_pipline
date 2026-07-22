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

import shutil
import tempfile
import time
from pathlib import Path

from prepro_grd_gpt import build_grd_gtc_graph

GRD_DIR = Path("downloads/sentinel1_grd")
OUT_DIR = Path("downloads/rtc_grd")


def main() -> None:
    zips = sorted(GRD_DIR.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR} 에 GRD zip이 없습니다.")

    print(f"대상 GRD: {len(zips)}개")
    done, skipped, failed = 0, 0, 0

    for i, zip_path in enumerate(zips, start=1):
        out_tif = OUT_DIR / f"{zip_path.stem}_gtc_db.tif"
        if out_tif.exists():
            print(f"[{i}/{len(zips)}] 건너뜀 (이미 처리됨): {zip_path.name}")
            skipped += 1
            continue

        print(f"[{i}/{len(zips)}] 처리 시작: {zip_path.name}")
        t0 = time.time()

        # RTC 배치(batch_grd_rtc.py)와 동시에 돌 때 같은 임시경로를 쓰면 같은
        # 씬에서 충돌하므로 모드별 접두사로 분리한다.
        ssd_copy = Path(tempfile.gettempdir()) / f"gtc_{zip_path.name}"
        try:
            shutil.copy2(zip_path, ssd_copy)
            graph = build_grd_gtc_graph(ssd_copy, out_dir=OUT_DIR)
            graph.run(gpt_options=["-q", "8", "-c", "14G"])
            print(f"[{i}/{len(zips)}] 완료 ({(time.time() - t0) / 60:.1f}분): {out_tif.name}")
            done += 1
        except Exception as e:
            print(f"[{i}/{len(zips)}] 실패: {zip_path.name} -> {e}")
            out_tif.unlink(missing_ok=True)
            failed += 1
        finally:
            ssd_copy.unlink(missing_ok=True)

    print(f"\n배치 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
