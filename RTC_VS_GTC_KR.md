# RTC를 쓴 이유 — GTC와의 차이 (392D 육안 비교용)

이 프로젝트의 GRD 전처리 그래프([prepro_grd_gpt.py](prepro_grd_gpt.py))가
왜 "지오코딩만"(GTC) 하지 않고 굳이 **지형 평탄화(Terrain-Flattening)를 포함한
RTC**까지 하는지 정리합니다. 육안 비교를 위해 동일 씬(392D, 2026-07-20 궤도
008632, 북한 함경남도~강원도를 지나는 남북 스와스)을 RTC/GTC 두 방식으로 각각
처리했습니다.

## 1. 용어 정리

| 약어 | 뜻 | 이 프로젝트 산출물 |
| --- | --- | --- |
| GRD | Ground Range Detected — 위성이 공급하는 원본, 슬랜트→지상거리 투영만 된 상태 | `downloads/sentinel1_grd/*.zip` |
| **GTC** | Geocoded Terrain Corrected — DEM으로 **기하(위치)만** 보정해 지도 좌표계에 올린 것. 밝기값은 손대지 않음 | `*_gtc_db.tif` (이번에 신규 생성) |
| **RTC** | Radiometric Terrain Corrected — GTC에 더해 **지형 경사·향에 따른 밝기 왜곡까지 보정**한 것 | `*_rtc_db.tif` (기존 파이프라인 산출물) |

즉 GTC는 "어디에 있는지"만 바로잡고, RTC는 "어디에 있는지 + 얼마나 밝아야
정상인지"까지 바로잡습니다. 두 산출물의 처리 그래프는 단 한 단계
(Terrain-Flattening)와 캘리브레이션 기준(Beta0 vs Sigma0)만 다르고 나머지는
동일합니다 — 그래서 이 비교가 "RTC가 정확히 무엇을 더 해주는지"를 순수하게
보여줍니다.

```text
공통:    Read → Apply-Orbit-File → ThermalNoiseRemoval → Calibration → Speckle-Filter
GTC만:                                                    (Sigma0 출력) → Terrain-Correction → dB
RTC만:                                                    (Beta0 출력)  → Terrain-Flattening → Terrain-Correction → dB
```

## 2. SAR 밝기가 지형 경사에 왜 영향을 받는가

레이더는 위성에서 비스듬히(입사각 30~45°) 지면을 내려다봅니다. 같은 재질이라도
**위성을 향한 사면(向斜面)은 실제보다 넓은 면적이 좁은 슬랜트 레인지 구간에
눌려 담기므로 비정상적으로 밝게**, **위성 반대쪽 사면(背斜面)은 넓게 퍼져
비정상적으로 어둡게** 찍힙니다 (foreshortening/layover 효과). 경사가 입사각을
넘으면 완전히 뒤집혀 겹치기도 하고, 급경사 반대쪽은 신호가 아예 안 닿는
레이더 그림자(shadow)로 완전히 어둡게 나옵니다.

GRD의 표준 캘리브레이션(Sigma0)은 위성-지면 간 **기하학적 투영**(슬랜트 레인지
면적 vs 지상 면적)만 보정하고, **실제 지면의 국지 경사**는 모릅니다 (DEM을 아예
안 쓰거나, 쓰더라도 위치 보정에만 씀). 그래서 GTC(=Sigma0 + 기하 보정만)까지는
평지에서는 문제없지만, **산지에서는 경사면 방향에 따라 같은 지표(예: 숲)가
수 dB씩 밝기가 달라지는 얼룩**이 남습니다.

Terrain-Flattening은 DEM에서 각 픽셀의 실제 국지 입사각(local incidence angle)을
계산해 이 경사 효과를 역산해 빼줍니다(Beta0 → Gamma0에 준하는 정규화). 그 결과가
RTC입니다.

## 3. 이 프로젝트에서 RTC가 필수인 구체적 이유

1. **한반도, 특히 북한 쪽은 산지 비중이 매우 높음**. 이번에 비교한 392D 스와스
   자체가 함경남도~강원도 산간을 관통합니다. 남한 AOI(충청권)도 평지가
   아니라 구릉·산지가 섞여 있습니다. GTC로는 경사면 밝기 얼룩이 광범위하게
   남습니다.
2. **탐지 로직이 전 영상에 걸친 고정 임계값(-16 dB)** 하나로 물/비물을
   가릅니다 ([FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md)). 지형 밝기 왜곡이
   남아 있으면:
   - 위성 반대쪽(배사면) 숲·나대지가 실제보다 어둡게 나와 **-16dB 밑으로
     떨어져 물로 오탐**됨 (특히 산간 하천 주변에서 흔함)
   - 위성 방향 사면(향사면)은 반대로 과대 보정되어 실제 얕은 물/젖은 지면이
     밝게 나와 **놓침(과소 탐지)**
   지형 정규화 없이는 임계값 하나로 지형이 다른 여러 스와스·궤도를 비교할 수
   없습니다. 이 프로젝트는 baseline(v3) 합성, 동일궤도 pre/post 비교, 날짜별
   단일시기 지도([FLOOD_NORTH_KOREA_KR.md](FLOOD_NORTH_KOREA_KR.md) 5·7절)까지
   전부 dB 값을 **날짜·궤도를 넘나들며 직접 비교**하므로, 각 씬이 지형에
   좌우되지 않고 일관된 dB 기준을 가져야만 이 비교들이 성립합니다.
3. **HAND 기반 오탐 필터**([TERRAIN_AUX_DATA_KR.md](TERRAIN_AUX_DATA_KR.md) §1.2)도
   "레이더 그림자로 인한 어두운 오탐"을 걸러내는 보조 수단이지만, 이건 완전
   그림자(신호 없음)만 잡아줄 뿐 **부분적 경사 밝기 왜곡(그림자는 아니지만
   기울어져 있어 밝기가 달라진 영역)은 걸러내지 못합니다** — 이걸 근본적으로
   없애는 것이 Terrain-Flattening의 역할이라 HAND 필터와 RTC는 서로 대체가
   아니라 보완 관계입니다.

## 4. 산출물 (육안 비교용)

| 파일 | 처리 | 씬 |
| --- | --- | --- |
| `downloads/rtc_grd/S1C_IW_GRDH_1SDV_20260720T213054_20260720T213119_008632_01119F_392D_COG_rtc_db.tif` | RTC (기존) | 392D |
| `downloads/rtc_grd/S1C_IW_GRDH_1SDV_20260720T213054_20260720T213119_008632_01119F_392D_COG_gtc_db.tif` | GTC (신규) | 392D |

QGIS 등에서 두 파일을 같은 스트레치(예: -20~0 dB, 그레이스케일)로 열어 산간
지형(함경남도~강원도 접경 산악 구간)을 확대해 보면, GTC 쪽에서 능선을 따라
위성을 향한 면과 반대쪽 면의 밝기 대비(줄무늬처럼 보이는 명암 패턴)가 뚜렷하고,
RTC 쪽에서는 같은 지형이 상대적으로 균일한 톤으로 나오는 것을 확인할 수
있습니다. 평지(하천·농경지 등)에서는 두 산출물이 거의 차이가 없습니다 — 경사가
없으니 애초에 왜곡될 게 없기 때문입니다.

## 5. 실행 방법 (재현용)

단일 씬:

```bash
# RTC (기존 표준 파이프라인)
conda run -n s1_snappy python prepro_grd_gpt.py <GRD.zip>

# GTC (Terrain-Flattening 생략, 비교용)
conda run -n s1_snappy python prepro_grd_gpt.py <GRD.zip> --gtc
```

전체 씬 배치([batch_grd_rtc.py](batch_grd_rtc.py)와 동일한 구조):

```bash
conda run -n s1_snappy python batch_grd_gtc.py
```

`downloads/sentinel1_grd/`의 모든 zip을 대상으로 하고, 이미
`<씬ID>_gtc_db.tif`가 있으면 건너뛰므로 중간에 멈추거나 NAS에서 zip이
계속 들어오는 중에도 다시 실행하면 새로 추가된 것만 이어서 처리됩니다
(단, 실행 중 새로 들어온 zip은 그 회차에는 포함되지 않고 다음 실행에서
잡힙니다 — 대상 목록을 시작 시점에 한 번만 읽기 때문).

두 그래프는 [prepro_grd_gpt.py](prepro_grd_gpt.py)의 `build_grd_rtc_graph`
/ `build_grd_gtc_graph`에 있으며, 출력은 같은 `downloads/rtc_grd/` 폴더에
`_rtc_db.tif` / `_gtc_db.tif`로 나란히 저장되어 파일명만으로 구분됩니다.

> **⚠️ GTC 산출물은 육안 비교 전용 — 수체 탐지에 넣지 말 것.** GTC는
> Sigma0 기준이고 RTC는 Gamma0(지형 평탄화) 기준이라 dB 값의 절대 수준이
> 다릅니다. 이 프로젝트의 고정 임계값(-16 dB, [FLOOD_DETECTION_KR.md](FLOOD_DETECTION_KR.md))은
> RTC(Gamma0)에 맞춰 잡힌 값이므로, `_gtc_db.tif`를 `detect_flood_grd_v2.py`나
> baseline 합성에 입력하면 임계값이 어긋나 잘못된 수체가 나옵니다. 수체
> 탐지 계열은 항상 `_rtc_db.tif`만 사용하세요.
>
> **동시 실행 주의**: `batch_grd_rtc.py`와 `batch_grd_gtc.py`를 병행하면
> 각각 CPU를 나눠 써서 둘 다 느려집니다. 임시파일 충돌은 모드별 접두사
> (`rtc_`/`gtc_`)로 방지되어 안전하지만, 속도상 순차 실행을 권장합니다.
