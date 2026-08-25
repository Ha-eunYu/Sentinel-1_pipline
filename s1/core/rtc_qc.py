# -*- coding: utf-8 -*-
"""RTC 산출물이 **내용물까지 정상인지** 재는 공용 함수.

왜 필요한가
-----------
**빈 산출물은 성공처럼 보인다.** SNAP은 DEM 밖 프레임을 오류 없이 정상 종료
시키고, 배치는 그것을 "성공 1"로 센다. 파일이 존재하므로 다음 실행은
`out_tif.exists()`에 걸려 **영원히 건너뛴다** — DEM을 넓혀도 조용히 지나간다
(ISSUES_KR #24, `8B48` 12.7분·14.8 MB·유효화소 0.00%).

2026-08-25 실측에서 VH RTC 105장 중 **14장이 유효화소 20% 미만**이었고 전부
"성공"으로 집계돼 있었다. 14장 모두 프레임이 39.9N을 넘는다 — 옛 DEM
(`korea_full_cop30.tif`, ≤39.9N) 밖이라 전부 무효가 된 것이다.

무엇을 재나
-----------
1. **유효화소 비율** — `유한값 AND 0이 아님 AND nodata가 아님`. 배치의
   합격/불합격 판정에 쓴다. 정상 산출물은 60~100%, 빈 껍데기는 0%다.
2. **압축률** — 파일 크기 ÷ `가로 × 세로 × 밴드 × 자료형바이트`.
   ⚠ **자료형을 눈으로 가정하지 않는다.** 문서에 적혀 있던 "정상 51.8~87.4%"는
   산출물을 16비트로 **가정**하고 계산한 값이라 실제(float32)의 정확히 2배였다
   (ISSUES_KR #20). 그 기준을 그대로 쓰면 **멀쩡한 2.5 GB 산출물을 지운다.**
   여기서는 `rasterio`의 `dtypes[0]`에서 읽는다.

   | 지표 | 정상(2026-08 실측 30장) | 불량(`D635`) |
   | --- | --- | --- |
   | 압축률 (float32 기준) | 25 ~ 44% | 2.6% |
   | 유효화소 | 60 ~ 100% | 0.0% |

   두 값의 간격이 10배 이상이라 **"한 자릿수면 불량"** 이 식에 가장 덜
   민감한 규칙이다. 판정은 압축률 단독으로 하지 않고 유효화소를 같이 본다.

왜 표본이 아니라 전량인가
-------------------------
3.9 GB 산출물에서 전량 블록 스캔 **91초**, 행 띠 표본(64×16) **80초**로 차이가
거의 없다. GDAL이 어차피 타일 전체를 풀어야 하기 때문이다. 씬당 처리시간이
71~128분이므로 전량 스캔의 비용은 2% 미만이고, 그 값이 정확하다.

사용:
    from s1.core.rtc_qc import VALID_FLOOR, measure
    st = measure(tif)
    if st.valid_frac < VALID_FLOOR:
        tif.unlink()            # 안 지우면 다음 실행이 건너뛴다
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 배치가 산출물을 **지우는** 기준이다. 정상 60~100% / 빈 껍데기 0% 사이에서
# 최대한 낮게 잡았다 — 여기 걸리는 것은 "부분 손실"이 아니라 "사실상 빈 파일"
# 이어야 한다. DEM 범위 밖으로 북쪽 일부만 날아간 씬(12~14%)은 자료가 실제로
# 들어 있으므로 지우지 않는다. 그런 부분 손실은 지우는 대신 **로그에 유효화소
# 비율을 늘 찍어** 눈에 띄게 한다(ISSUES_KR #17의 교훈 — 재처리 여부는 씬별로
# 재서 정하지, 일괄로 반사하지 않는다).
VALID_FLOOR = 0.05

# 참고용 정상 범위(2026-08 실측). 판정 기준이 아니라 보고서에 찍는 맥락이다.
NORMAL_VALID = (0.60, 1.00)
NORMAL_COMPRESS = (0.25, 0.44)


@dataclass(frozen=True)
class RtcStats:
    """산출물 한 장의 무결성 지표."""

    path: Path
    width: int
    height: int
    count: int          # 밴드 수
    dtype: str
    itemsize: int       # 자료형 1화소 바이트 (가정하지 말고 읽은 값)
    file_bytes: int
    valid: int          # 유효화소 수 (band 기준)
    total: int          # 검사한 화소 수
    read_errors: int    # 읽지 못한 블록 수 — 절단된 파일에서 나온다

    @property
    def valid_frac(self) -> float:
        return self.valid / self.total if self.total else 0.0

    @property
    def raw_bytes(self) -> int:
        """무압축 크기. 압축률의 분모 — 자료형을 실제 값에서 가져온다."""
        return self.width * self.height * self.count * self.itemsize

    @property
    def compress_ratio(self) -> float:
        return self.file_bytes / self.raw_bytes if self.raw_bytes else 0.0

    def summary(self) -> str:
        """로그 한 줄용. 예: `유효 70.2% · 압축 27.9% · 3.92 GB`"""
        txt = (f"유효 {self.valid_frac * 100:.1f}% · "
               f"압축 {self.compress_ratio * 100:.1f}% · "
               f"{self.file_bytes / 1e9:.2f} GB")
        if self.read_errors:
            txt += f" · 읽기실패 블록 {self.read_errors}"
        return txt


def measure(tif: Path, band: int = 1) -> RtcStats:
    """산출물을 블록 단위로 전량 훑어 유효화소·압축률을 잰다.

    `rasterio`가 없으면 ImportError를 그대로 올린다 — 호출하는 쪽에서
    "검사를 못 했다"를 **눈에 띄게** 알려야 한다. 조용히 통과시키면 이 검사를
    넣은 이유가 사라진다.
    """
    import numpy as np
    import rasterio

    tif = Path(tif)
    with rasterio.open(tif) as src:
        nodata = src.nodata
        valid = total = errors = 0
        for _, win in src.block_windows(band):
            try:
                a = src.read(band, window=win)
            except Exception:            # noqa: BLE001 (안 쓰인/깨진 타일)
                # 절단된 파일은 타일 읽기가 실패한다. 그 화소는 무효로 세고
                # 블록 수를 따로 남겨 원인을 구분할 수 있게 한다.
                errors += 1
                total += int(win.height) * int(win.width)
                continue
            m = np.isfinite(a) & (a != 0)
            if nodata is not None and np.isfinite(nodata):
                m &= a != nodata
            valid += int(m.sum())
            total += int(a.size)

        return RtcStats(
            path=tif,
            width=src.width,
            height=src.height,
            count=src.count,
            dtype=str(src.dtypes[0]),
            itemsize=int(np.dtype(src.dtypes[0]).itemsize),
            file_bytes=tif.stat().st_size,
            valid=valid,
            total=total,
            read_errors=errors,
        )
