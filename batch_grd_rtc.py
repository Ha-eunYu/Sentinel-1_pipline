# -*- coding: utf-8 -*-
"""
downloads/sentinel1_grd 의 GRD zip 전부를 순차적으로 RTC(dB) 처리하는 배치 러너.

- 이미 산출물(downloads/rtc_grd/<씬ID>_rtc_db.tif)이 있는 씬은 건너뛰므로
  중간에 끊겨도 다시 실행하면 이어서 진행된다.
- 처리 전 입력 zip을 시스템 임시 폴더(C: SSD)로 복사해서 HDD 랜덤 읽기
  병목을 피하고, 처리 후 복사본은 삭제한다.
- 한 씬이 실패해도 나머지는 계속 진행한다.

실행:
    conda run -n s1_snappy python batch_grd_rtc.py
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from prepro_grd_gpt import build_grd_rtc_graph

GRD_DIR = Path("downloads/sentinel1_grd")
OUT_DIR = Path("downloads/rtc_grd")


def main() -> None:
    zips = sorted(GRD_DIR.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"{GRD_DIR} 에 GRD zip이 없습니다.")

    print(f"대상 GRD: {len(zips)}개")
    done, skipped, failed = 0, 0, 0

    for i, zip_path in enumerate(zips, start=1):
        out_tif = OUT_DIR / f"{zip_path.stem}_rtc_db.tif"
        if out_tif.exists():
            print(f"[{i}/{len(zips)}] 건너뜀 (이미 처리됨): {zip_path.name}")
            skipped += 1
            continue

        print(f"[{i}/{len(zips)}] 처리 시작: {zip_path.name}")
        t0 = time.time()

        # GTC 배치(batch_grd_gtc.py)와 동시에 돌 때 같은 임시경로를 쓰면 같은
        # 씬에서 충돌하므로 씬별 임시 하위폴더로 격리한다(파일명 접두사는
        # SNAP의 Sentinel-1 리더가 파일명 패턴으로 포맷을 인식하는 걸 깨뜨려
        # "No product reader found" 오류를 내므로 쓰지 않는다 — 원본 파일명은
        # 그대로 유지해야 함, batch_grd_rtc_frost.py와 동일 패턴).
        tmpdir = Path(tempfile.mkdtemp(prefix="rtc_"))
        ssd_copy = tmpdir / zip_path.name
        try:
            shutil.copy2(zip_path, ssd_copy)
            graph = build_grd_rtc_graph(ssd_copy, out_dir=OUT_DIR)
            graph.run(gpt_options=["-q", "8", "-c", "14G"])
            print(f"[{i}/{len(zips)}] 완료 ({(time.time() - t0) / 60:.1f}분): {out_tif.name}")
            done += 1
        except Exception as e:
            print(f"[{i}/{len(zips)}] 실패: {zip_path.name} -> {e}")
            # 실패 시 불완전 산출물이 남아 재실행 때 '이미 처리됨'으로 오인되지 않게 삭제
            out_tif.unlink(missing_ok=True)
            failed += 1
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n배치 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")


if __name__ == "__main__":
    main()
