# 작업일지 2026-08-13 — 저장소 재구성(패키지화)과 공용 모듈 분리

루트에 파이썬 58개·마크다운 27개가 평평하게 쌓여 있던 저장소를 **`s1/` 파이썬
패키지**로 재구성하고, 스크립트마다 복사돼 있던 공통 로직 4가지를 모듈로
분리했다. 기능 변경은 없다 — **구조와 중복 제거만** 했다.

---

## 1. 왜 했나

| 증상 | 결과 |
| --- | --- |
| 경로가 스크립트마다 `Path("downloads/...")`로 박혀 있음 | 저장소 루트에서 실행할 때만 동작. 폴더 하나 옮기면 수십 파일 수정 |
| 씬 ID를 `split("_")[-2]`로 뽑는 코드가 여럿 | `_COG` 유무에 따라 **take ID를 씬 ID로 착각**. 실제로 조사 중 오판 발생 |
| footprint 커버율 계산이 임시 스크립트에만 존재 | 궤도 선별을 재현하려면 매번 다시 작성 |
| 배치 러너 4개가 같은 로직을 복사 보유 | 한쪽만 고쳐지는 표류. 예: 실패 시 반쯤 쓰인 tif 삭제 |
| 하드코딩된 절대경로 14곳 (`F:\06_SAR_system\...`) | 저장소를 옮기면 전부 깨짐 |

## 2. 새 구조

```text
s1/                    # 파이썬 패키지 (실행 코드 전부)
  core/                #   paths.py · scene.py · aoi.py · config.py
  stac/                #   CDSE STAC 검색·다운로드
  footprint/           #   bbox 대신 footprint로 촬영지역 판정
  preprocess/          #   SNAP gpt 그래프 + batch_runner.py
  tools/               #   실행 스크립트
    download/ preprocess/ water/ mosaic/ dem/ audit/ monitor/ scratch/
docs/                  # 문서 (pipeline/ water/ flood/ drought/ worklog/ review/)
scripts/               # PowerShell 래퍼
geojson/ graphs/ env/ filtering/ qa/ data/ kmz/
downloads/             # 산출물 (git 미추적)
```

- 파이썬 86개가 `s1/` 아래로, 마크다운 26개가 `docs/` 아래로 이동.
- 루트에 남은 것은 `README_KR.md` · `README_ENG.md` · `pyproject.toml` 뿐.
- `git mv`로 옮겨 **이력이 끊기지 않는다**(`git log --follow`로 추적 가능).

### 실행 방법이 바뀌었다

```bash
# 이전
conda run -n s1_snappy python batch_grd_rtc_frost.py --month 202607

# 지금 (저장소 루트에서)
conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc_frost --month 202607
```

`pyproject.toml`을 추가해 `pip install -e .`도 가능하다(어느 디렉터리에서든
import). 런타임 의존은 종전대로 conda 환경(`env/`)으로 관리한다 — SNAP
(`esa_snappy`)은 pip으로 설치되지 않기 때문이다.

## 3. 분리한 공용 모듈 4개

### 3-1. `s1/core/paths.py` — 경로 단일 정의

이 파일 위치에서 저장소 루트를 찾아, **그 아래 상대경로로** 모든 폴더를
정의한다. 코드 어디에도 드라이브 문자가 없다.

```python
from s1.core.paths import RTC_FROST_DIR, WATER_OTSU_DIR, rel
print(rel(tif))     # downloads/rtc_grd_frost/S1C_....tif
```

- 하드코딩 절대경로 **14곳을 전부 상수로 교체**했다.
- 형제 폴더인 `gee/`도 `PROJECT_DIR.parent / "gee"`로 잡아 상대화했다
  (`GEE_WATER_DIR`, `BASIN_SHP`, `DAM_BASIN_SHP`).
- `rel()`은 로그에 절대경로가 찍히지 않게 하는 보조 함수다.

> 확인된 사실: `downloads/sentinel1_grd`는 실제로 `E:\06_SAR_system_archive\
> sentinel1_grd`를 가리키는 junction이다. 경로 상수가 이를 그대로 따라가므로
> 스크립트는 영향받지 않는다.

### 3-2. `s1/core/scene.py` — 파일명 파싱 통합

```text
S1C_IW_GRDH_1SDV_20260727T212332_20260727T212357_008734_0114F4_9B8B_COG.zip
 └위성            └관측 시작                      └절대궤도 └take └씬ID
```

`parse_scene()` 하나로 다섯 필드를 뽑고, `scene_date` / `scene_orbit` /
`scene_id` / `group_key`(날짜+궤도) / `normalize_orbit`(6자리 0채움) /
`matches_scene_id`를 제공한다.

- **`split("_")[-2]` 방식을 전부 제거**했다. 산출물(`..._9B8B_COG_rtc_db.tif`)
  에서는 그 위치가 `COG`라 씬 ID가 아니다.
- `normalize_orbit`은 셸이 `008632`를 숫자로 읽어 앞의 0을 떨구는 사고
  ([PROCESS_202507_202607_KR.md](../pipeline/PROCESS_202507_202607_KR.md) 7-4절)
  를 코드 쪽에서 막는다.

### 3-3. `s1/core/aoi.py` — footprint 커버율 산정

원본 zip의 `preview/map-overlay.kml`에서 실제 촬영 폴리곤을 읽어, 경계
폴리곤과 point-in-polygon으로 커버율을 잰다. 7월 남한 궤도 선별에 쓴 임시
스크립트를 본모듈로 승격한 것이다.

```python
from s1.core.aoi import coverage_percent, south_korea_scenes
pct  = coverage_percent(zip_path)                       # 이 프레임의 남한 %
keep = south_korea_scenes(GRD_DIR.glob("*2026*.zip"), min_pct=1.0)
```

bbox로 판정하면 기울어진 프레임의 빈 삼각형까지 "촬영"으로 세어, 100% 바다인
프레임이 육지를 찍은 것으로 오판된다
([SCENE_FOOTPRINT_REAUDIT_KR.md](../pipeline/SCENE_FOOTPRINT_REAUDIT_KR.md)).

### 3-4. `s1/preprocess/batch_runner.py` — 배치 뼈대 통합

`run_batch(zips, out_dir, build_graph, ...)`가 임시복사·건너뛰기·실패정리·
집계를 담당하고, 각 배치 스크립트는 **그래프를 만드는 함수만** 넘긴다.

- `batch_grd_rtc.py` 71줄 → 37줄, `batch_grd_gtc.py` 75줄 → 42줄,
  `batch_grd_rtc_frost.py`의 실행 루프 33줄 → 6줄(파일 전체 151 → 125줄).
- 공통 러너에 규약을 주석으로 고정했다: 임시 폴더는 **씬별 하위폴더 + 원본
  파일명 유지**(파일명에 접두사를 붙이면 SNAP 리더가 "No product reader found"
  를 낸다), 실패 시 반쯤 쓰인 산출물 삭제(안 지우면 재실행이 '이미 처리됨'으로
  건너뛴다).

## 4. import·경로 검증

- 저장소 내 import를 전수 조사해 패키지 경로로 고쳤다(`from config import` →
  `from s1.core.config import` 등, 40여 곳).
- `sys.path.insert` 해킹 3곳 제거. 남은 1곳은 **별도 저장소인 `gee/`의 모듈**을
  쓰는 `export_reservoir_points.py`뿐이고, 이유를 주석으로 남겼다.
- `python -m compileall s1` 전량 통과.
- 주요 CLI 6종을 `python -m ...`로 기동 확인:
  `water_area_report` · `split_flood_area_nk_sk` · `verify_scene_footprint` ·
  `make_basin_dem` · `batch_grd_rtc_frost` · `build_water_per_date_otsu` 정상.
- 핵심 모듈 동작 확인: 경로 상수가 실제 폴더를 가리키고, `parse_scene`이
  산출물 파일명에서도 씬 ID `9B8B`를 정확히 뽑는다.

### 알려진 제약

- `s1.core.config`(및 `s1.stac.*`)는 `python-dotenv`가 필요해 **s1_snappy
  환경에서는 import되지 않는다.** 검색·다운로드는 원래 `s1_pipeline` 환경에서
  돌리므로 정상이다. 재구성 이전부터 그랬다.
- `s1/tools/scratch/`의 일회성 스크립트는 재현을 보장하지 않는다.

## 5. 문서 정리

- 27개 문서를 주제별 6개 폴더로 이동.
- 이동으로 깨진 **마크다운 상대링크 291개를 자동 교정**했다(1차 257 + 2차 34).
- 남은 미해결 링크는 재구성 이전부터 대상이 없던 것들이다
  (`TODO.md`, 외부 저장소 `gee/geeflood/sar.py`, 괄호가 든 esa-snappy 문서명).
- `README_KR.md`의 폴더 구조 절을 새 구조로 교체하고, quick start 명령을
  모듈 경로로 갱신했다.

## 6. 이어서 할 일

- [ ] **`geojson/South_Korea.geojson` 재검증** — `download_south_korea_month.py`
      주석에 따르면 이 폴리곤은 **부산·강릉·여수·해남·완도·제주를 제외**하는
      거친 내륙 덩어리다. 7월 남한 궤도 선별
      ([PROCESS_202507_202607_KR.md](../pipeline/PROCESS_202507_202607_KR.md) 1절)이
      이걸 썼으므로, 대권역 shp(`BASIN_SHP`) 기준으로 커버율을 다시 재고
      결과가 바뀌면 문서를 갱신해야 한다.
- [ ] **공통 관측영역 마스크** — 25 vs 26년 유일한 상대궤도 짝
      (2025-07-18 o003280 ↔ 2026 계열 A)이 유효화소 8.79억 vs 17.85억으로
      관측 범위가 2배 차이다. 교집합으로 잘라야 면적 비교가 성립한다
      ([DROUGHT_KR.md](../drought/DROUGHT_KR.md) 3절).
- [ ] **내수면 마스크** — 현재 면적은 서해·남해를 포함한 "상태 면적"이라
      가뭄 지표로 직접 못 쓴다.
- [ ] 남은 배치 스크립트(`batch_slc_rtc.py`)도 `run_batch`로 통합
      (AOI 미교차 자동 건너뜀 로직이 있어 러너에 훅이 필요).

## 7. 참고

- 전처리·수체판별 전 과정: [PROCESS_202507_202607_KR.md](../pipeline/PROCESS_202507_202607_KR.md)
- 궤도별 임계값·면적: [WATER_AREA_KR.md](../water/WATER_AREA_KR.md)
- 가뭄 비교 설계: [DROUGHT_KR.md](../drought/DROUGHT_KR.md)
- 이전 작업일지: [WORKLOG_20260807_KR.md](WORKLOG_20260807_KR.md)
