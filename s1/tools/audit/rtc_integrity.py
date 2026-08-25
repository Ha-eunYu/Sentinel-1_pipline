# -*- coding: utf-8 -*-
"""RTC 산출물의 **유효화소·압축률**을 재는 도구.

왜 도구로 고정하나
------------------
이 두 값은 **파일을 지울지 말지를 정하는 판정 기준**인데, 지금까지 손으로 계산해
문서에 수치만 박아 넣었다. 그러다 압축률의 분모를 **화소당 2바이트로 가정**해
기록된 값이 전부 정확히 2배가 된 사고가 있었다(ISSUES_KR #20). 그 기준을 그대로
적용하면 정상 산출물(25~44%)이 전부 불량으로 잡혀 **멀쩡한 2.5 GB 파일을 지운다.**

그래서 계산은 `s1.core.rtc_qc.measure()` 한 곳에만 두고(자료형은 가정하지 않고
`rasterio` 에서 읽는다), 문서에는 **도구 이름과 임계값만** 적는다.

무엇에 쓰나
-----------
- **배치 뒤 전수 점검** — 특히 강제 종료 후. 눈으로 "부분 산출물 없음"을 보는
  방식은 실패한 전례가 있다(엉뚱한 씬을 봤다).
- **재처리 대상 선정** — 유효화소가 낮은 산출물은 프레임이 external DEM 범위
  밖일 때 나온다. `--min-valid` 로 걸러 목록을 뽑는다(ISSUES_KR #17·#24).
- **재처리 결과 검증** — 다시 구운 뒤 같은 명령으로 유효화소가 올랐는지 본다.

판정
----
| 지표 | 정상 | 불량(`D635` 껍데기) |
| --- | --- | --- |
| 유효화소 | 42 ~ 100% | 0.0% |
| 압축률 (float32 기준) | 25 ~ 44% | 2.6% |

간격이 10배 이상이라 **"한 자릿수면 불량"** 이 식에 가장 덜 민감하다. 판정은
압축률 단독으로 하지 않고 **유효화소를 같이** 본다.

⚠ **유효화소가 낮다고 손상은 아니다.** 스와스가 기울어져 있어 북쪽 정렬 사각형의
네 모서리는 구조적으로 무효다. 2026-08 남한 위주 표본은 60~100%였지만 2026-07
북부 프레임 12장은 **42.9~66.8%** 이고 전부 정상이다. 그래서 이 도구는 40% 미만
에서만 ⚠ 를 달고, 지우는 선은 그보다 훨씬 낮은 5%다.

실행
----
    # 폴더 전수 (오래 걸린다 — 씬당 30~90초, 병렬 4)
    conda run -n s1_snappy python -m s1.tools.audit.rtc_integrity

    # 씬 몇 개만
    conda run -n s1_snappy python -m s1.tools.audit.rtc_integrity 32AE CE47

    # 재처리 대상 목록 뽑기 (유효화소 20% 미만인 씬 ID를 쉼표로)
    conda run -n s1_snappy python -m s1.tools.audit.rtc_integrity --min-valid 20 --only-bad --ids

    # CSV 로 남기기
    conda run -n s1_snappy python -m s1.tools.audit.rtc_integrity --csv temp/rtc_integrity.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from s1.core.paths import RTC_FROST_VH_DIR, rel
from s1.core.rtc_qc import LOW_VALID, NORMAL_COMPRESS, VALID_FLOOR, RtcStats, measure
from s1.core.scene import scene_date, scene_id


def scan(tifs: list[Path], jobs: int, progress: bool = True
         ) -> list[tuple[Path, RtcStats | None, str]]:
    """(경로, 지표, 오류문구) 목록. 열지 못한 파일도 빠뜨리지 않고 담는다.

    씬당 30~90초라 폴더 전수는 한 시간을 넘긴다. **끝난 것부터 바로 찍는다** —
    파이썬 stdout 은 파일로 리다이렉트하면 버퍼링돼서, 안 찍으면 로그가 몇십 분
    동안 비어 있고 도는 중인지 멈춘 건지 알 수 없다(WORKLOG 20260818 7절).
    """
    done = 0

    def one(p: Path):
        nonlocal done
        try:
            r = (p, measure(p), "")
        except Exception as e:                      # noqa: BLE001 (못 여는 것도 결과다)
            r = (p, None, str(e))
        done += 1                                   # GIL 아래 += 는 원자적이지 않지만 진행표시용이라 무방
        if progress:
            st = r[1]
            v = f"유효 {st.valid_frac * 100:6.2f}%" if st else "**열 수 없다**"
            print(f"  [{done}/{len(tifs)}] {scene_id(p) or p.stem[-4:]}  {v}", flush=True)
        return r

    # GDAL 읽기는 대부분 GIL 밖이라 스레드로도 실효가 있다. 디스크 경합을
    # 생각해 기본 4로 둔다(HDD 라면 --jobs 1 이 빠를 수 있다).
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(one, tifs))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tags", nargs="*", help="검사할 씬 ID(4 hex). 없으면 폴더 전체")
    ap.add_argument("--dir", type=Path, default=RTC_FROST_VH_DIR)
    ap.add_argument("--glob", default="*.tif", help="검사할 파일 패턴")
    ap.add_argument("--min-valid", type=float, default=VALID_FLOOR * 100,
                    help=f"유효화소 하한(%%). 미만이면 ❌. 기본 {VALID_FLOOR * 100:.0f}%%. "
                         f"재처리 대상을 넓게 뽑을 땐 20 정도로 올린다")
    ap.add_argument("--only-bad", action="store_true", help="하한 미달만 출력")
    ap.add_argument("--ids", action="store_true",
                    help="표 대신 씬 ID를 쉼표로 출력 (배치의 --only 에 그대로 붙인다)")
    ap.add_argument("--csv", type=Path, default=None, help="결과를 CSV 로도 남긴다")
    ap.add_argument("--jobs", type=int, default=4, help="동시 검사 수. 기본 4")
    args = ap.parse_args()

    tifs = sorted(args.dir.glob(args.glob))
    if args.tags:
        want = {t.strip().upper() for t in args.tags}
        tifs = [p for p in tifs if (scene_id(p) or "") in want]
    if not tifs:
        raise SystemExit(f"검사할 tif 가 없다: {args.dir.resolve()} ({args.glob})")

    if not args.ids:
        print(f"{args.dir.resolve()}")
        print(f"{len(tifs)}장 검사 (병렬 {args.jobs}) — 씬당 30~90초 걸린다\n")

    t0 = time.time()
    rows = scan(tifs, args.jobs, progress=not args.ids)
    # 나쁜 것부터. 못 연 파일이 가장 위로 온다.
    rows.sort(key=lambda r: (r[1].valid_frac if r[1] else -1.0))

    floor = args.min_valid / 100
    bad: list[Path] = []
    printed = 0
    if not args.ids:
        print(f"\n{'씬':<6}{'관측일':<10}{'유효%':>7}{'압축%':>7}{'GB':>7}  "
              f"{'크기':<18}{'자료형':<9}판정")
    for p, st, err in rows:
        tag = scene_id(p) or p.stem[-4:]
        date = scene_date(p) or "-"
        if st is None:
            bad.append(p)
            if not args.ids:
                print(f"{tag:<6}{date:<10}{'-':>7}{'-':>7}"
                      f"{p.stat().st_size / 1e9:>7.2f}  **열 수 없다** {err}")
            continue
        ok = st.valid_frac >= floor
        if not ok:
            bad.append(p)
        if args.only_bad and ok:
            continue
        printed += 1
        if not args.ids:
            note = "OK" if ok else f"❌ 하한 {args.min_valid:.0f}% 미달"
            if ok and st.valid_frac < LOW_VALID:
                # 기울어진 스와스는 기하만으로 40%대가 나온다(rtc_qc 주석).
                # 그보다 낮으면 그것만으로는 설명이 안 되니 따로 보라는 뜻이다.
                note = f"⚠ 낮음 — 스와스 기하인지 DEM 밖인지 확인 (기하 정상은 {LOW_VALID*100:.0f}%대까지)"
            elif ok and not (NORMAL_COMPRESS[0] <= st.compress_ratio <= NORMAL_COMPRESS[1]):
                note = "⚠ 압축률이 정상범위(25~44%) 밖"
            print(f"{tag:<6}{date:<10}{st.valid_frac * 100:>7.2f}"
                  f"{st.compress_ratio * 100:>7.1f}{st.file_bytes / 1e9:>7.2f}  "
                  f"{f'{st.width:,}x{st.height:,}':<18}{st.dtype:<9}{note}")

    if args.ids:
        print(",".join(sorted({scene_id(p) or p.stem[-4:] for p in bad})))
        return

    print(f"\n{len(tifs)}장 중 **하한 미달 {len(bad)}장** "
          f"(검사 {(time.time() - t0) / 60:.1f}분)")
    if bad:
        print("  → 재처리하려면 **먼저 지워야 한다.** 파일이 남으면 배치가 "
              "'이미 처리됨'으로 건너뛴다 (ISSUES_KR #24)")
        print(f"  → 대상 목록: --only-bad --ids 로 다시 실행하면 쉼표 목록이 나온다")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["scene", "date", "file", "valid_frac", "compress_ratio",
                        "file_bytes", "width", "height", "bands", "dtype",
                        "read_errors", "error"])
            for p, st, err in rows:
                w.writerow([scene_id(p) or "", scene_date(p) or "", p.name,
                            f"{st.valid_frac:.6f}" if st else "",
                            f"{st.compress_ratio:.6f}" if st else "",
                            st.file_bytes if st else p.stat().st_size,
                            st.width if st else "", st.height if st else "",
                            st.count if st else "", st.dtype if st else "",
                            st.read_errors if st else "", err])
        print(f"  CSV: {rel(args.csv)}")

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
