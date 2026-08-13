# -*- coding: utf-8 -*-
"""SNAP gpt 배치 실행의 **공통 뼈대**.

batch_grd_rtc / batch_grd_rtc_frost / batch_grd_gtc / batch_slc_rtc 가 각자
같은 로직을 복사해 갖고 있었다. 네 벌이 조금씩 어긋나면서 한쪽만 고쳐지는
일이 생겨(예: 실패 시 반쯤 쓰인 tif 삭제) 여기로 합쳤다.

공통 로직이 하는 일
-------------------
1. **이미 산출물이 있으면 건너뛴다** — 중간에 끊겨도 이어서 재실행 가능.
2. **입력 zip을 SSD 임시 하위폴더로 복사**한 뒤 처리한다. HDD/네트워크
   랜덤 읽기가 병목이라 복사가 오히려 빠르다.
   - 씬별 **하위폴더**로 격리하고 **원본 파일명은 유지**한다. 파일명에 접두사를
     붙이면 SNAP의 Sentinel-1 리더가 포맷 인식에 실패해 "No product reader
     found"가 난다. 폴더로 나누므로 배치를 동시에 돌려도 충돌하지 않는다.
3. **실패하면 반쯤 쓰인 산출물을 지운다** — 남겨두면 다음 실행이 '이미 처리됨'
   으로 오인해 조용히 건너뛴다.
4. 씬별 소요시간과 성공/건너뜀/실패 집계를 찍는다.

사용:
    from s1.preprocess.batch_runner import run_batch
    run_batch(zips, out_dir, lambda src, out: build_grd_rtc_graph(src, out_dir=out),
              suffix="_rtc_db", gpt_options=["-q", "8", "-c", "14G"])
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Sequence

from s1.core.paths import rel

# (입력 zip 경로, 출력 폴더) -> snapista Graph
GraphBuilder = Callable[[Path, Path], object]


def output_path(zip_path: Path, out_dir: Path, suffix: str, ext: str = ".tif") -> Path:
    """산출물 경로. 입력 파일명(확장자 제외) + 접미사 규칙을 한 곳에서 정한다."""
    return out_dir / f"{zip_path.stem}{suffix}{ext}"


def run_batch(
    zips: Sequence[Path],
    out_dir: Path,
    build_graph: GraphBuilder,
    *,
    suffix: str = "_rtc_db",
    gpt_options: Sequence[str] = ("-q", "8", "-c", "14G"),
    tmp_prefix: str = "snapbatch_",
    label: str = "배치",
) -> tuple[int, int, int]:
    """zip 목록을 순서대로 처리한다. 반환: (성공, 건너뜀, 실패).

    build_graph(입력zip, 출력폴더) 가 snapista Graph를 돌려주면 되고, 나머지
    (임시복사·건너뛰기·실패정리·집계)는 여기서 처리한다.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    total = len(zips)

    for i, zip_path in enumerate(zips, start=1):
        out_tif = output_path(zip_path, out_dir, suffix)
        if out_tif.exists():
            print(f"[{i}/{total}] 건너뜀 (이미 처리됨): {out_tif.name}")
            skipped += 1
            continue

        print(f"[{i}/{total}] 처리 시작: {zip_path.name}")
        t0 = time.time()
        tmpdir = Path(tempfile.mkdtemp(prefix=tmp_prefix))
        ssd_copy = tmpdir / zip_path.name
        try:
            shutil.copy2(zip_path, ssd_copy)
            graph = build_graph(ssd_copy, out_dir)
            graph.run(gpt_options=list(gpt_options))
            mins = (time.time() - t0) / 60
            print(f"[{i}/{total}] 완료 ({mins:.1f}분): {rel(out_tif)}")
            done += 1
        except Exception as e:                      # noqa: BLE001 (씬 하나 실패로 배치를 멈추지 않는다)
            print(f"[{i}/{total}] 실패: {zip_path.name} -> {e}")
            out_tif.unlink(missing_ok=True)
            failed += 1
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{label} 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")
    return done, skipped, failed
