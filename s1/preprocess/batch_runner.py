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
4. **산출물의 유효화소가 하한 미만이면 실패로 처리하고 지운다** — gpt가 정상
   종료해도 내용이 비어 있을 수 있다(아래).
5. 씬별 소요시간과 성공/건너뜀/실패 집계를 찍는다.

유효화소 하한 검사 (2026-08-25 추가, ISSUES_KR #24)
--------------------------------------------------
**빈 산출물은 성공처럼 보인다.** 프레임이 external DEM 범위 밖이면
Terrain-Flattening 결과가 전부 무효가 되는데, SNAP은 오류 없이 정상 종료한다.
그러면 위 3번(실패 시 삭제)이 걸리지 않고 배치는 "성공"으로 센다. 파일이
남으니 위 1번(건너뛰기)에 걸려 **DEM을 넓혀도 다시는 처리되지 않는다.**
실제로 VH RTC 105장 중 14장이 이 상태로 "성공" 집계돼 있었다.

그래서 gpt가 끝난 뒤 산출물을 열어 유효화소를 재고, `min_valid_frac` 미만이면
**실패로 세고 파일을 지운다.** 지우는 것이 핵심이다 — 남기면 다음 실행이
건너뛴다.

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
from s1.core.rtc_qc import VALID_FLOOR, measure

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
    min_valid_frac: float = VALID_FLOOR,
) -> tuple[int, int, int]:
    """zip 목록을 순서대로 처리한다. 반환: (성공, 건너뜀, 실패).

    build_graph(입력zip, 출력폴더) 가 snapista Graph를 돌려주면 되고, 나머지
    (임시복사·건너뛰기·실패정리·검사·집계)는 여기서 처리한다.

    min_valid_frac:
        산출물의 유효화소 비율이 이 값 미만이면 **실패로 세고 파일을 지운다**
        (0 이면 검사하지 않는다). 기본값의 근거는 `s1.core.rtc_qc`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0
    total = len(zips)
    qc_warned = False

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
        except Exception as e:                      # noqa: BLE001 (씬 하나 실패로 배치를 멈추지 않는다)
            print(f"[{i}/{total}] 실패: {zip_path.name} -> {e}")
            out_tif.unlink(missing_ok=True)
            failed += 1
            continue
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        # gpt 는 정상 종료했다. 여기서 끝내면 안 된다 — 내용물을 본다.
        mins = (time.time() - t0) / 60      # 처리시간은 gpt 구간만 (근거표와 비교 가능하게)
        ok, note, qc_warned = _check_output(out_tif, min_valid_frac, qc_warned)
        if ok:
            print(f"[{i}/{total}] 완료 ({mins:.1f}분): {rel(out_tif)}  {note}")
            done += 1
        else:
            print(f"[{i}/{total}] 실패 ({mins:.1f}분): {rel(out_tif)}  {note}")
            failed += 1

    print(f"\n{label} 완료: 성공 {done} / 건너뜀 {skipped} / 실패 {failed}")
    return done, skipped, failed


def _check_output(out_tif: Path, min_valid_frac: float,
                  qc_warned: bool) -> tuple[bool, str, bool]:
    """산출물을 열어 합격 여부를 판정한다. 반환: (합격, 로그문구, 경고했었나).

    불합격이면 **파일을 지운다.** 남기면 다음 실행이 '이미 처리됨'으로
    건너뛰어 재처리 기회가 영영 사라진다(ISSUES_KR #24).
    """
    if not out_tif.exists():
        # gpt 가 예외 없이 끝났는데 파일이 없다 = 산출물명 규약이 어긋났다.
        return False, "**산출물이 없다** — 접미사(suffix) 규약을 확인할 것", qc_warned

    if min_valid_frac <= 0:
        return True, f"{out_tif.stat().st_size / 1e9:.2f} GB (유효화소 검사 꺼짐)", qc_warned

    try:
        st = measure(out_tif)
    except ImportError as e:
        # 조용히 넘어가면 이 검사를 넣은 의미가 없다. 배치당 한 번 크게 알린다.
        if not qc_warned:
            print(f"  ⚠⚠ rasterio 를 못 불러 **유효화소 검사를 못 한다** ({e}). "
                  f"빈 산출물이 성공으로 집계될 수 있다 — 배치 후 "
                  f"`python -m s1.tools.audit.rtc_integrity` 로 반드시 점검할 것.")
            qc_warned = True
        return True, f"{out_tif.stat().st_size / 1e9:.2f} GB (검사 불가)", qc_warned
    except Exception as e:                          # noqa: BLE001 (열 수 없는 산출물 = 불량)
        out_tif.unlink(missing_ok=True)
        return False, f"**산출물을 열 수 없다 — 삭제함** ({e})", qc_warned

    if st.valid_frac < min_valid_frac:
        out_tif.unlink(missing_ok=True)
        return False, (f"**유효화소 {st.valid_frac * 100:.2f}% < 하한 "
                       f"{min_valid_frac * 100:.0f}% — 삭제함** ({st.summary()}). "
                       f"프레임이 DEM 범위 밖인지 확인할 것"), qc_warned

    return True, st.summary(), qc_warned
