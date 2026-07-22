# S1 파이프라인 코드 리뷰 (2026-07-22 갱신)

> **2026-07-22 추가 리뷰 — GTC 대조군·배치·경로 재구성**
> 이번 세션에 새로 들어온/바뀐 코드만 집중 리뷰. 아래 "2026-07-22 리뷰"
> 절 참고. 이전(7/14) 리뷰 본문은 그대로 유지.

- **리뷰 일자**: 2026-07-14 (최초 2026-07-13 리뷰 갱신판)
- **대상**: `f:\06_SAR_system\S1` 전체 파이프라인 코드 21개 파일 + `downloads/` 결과물 + 문서.
  `esa-snappy-master/`는 서드파티 소스 사본이므로 리뷰 대상에서 제외.
- **총평**: 검색→다운로드→RTC→모자이크→수체 baseline까지 이어지는 흐름이 명확하고,
  주석·README가 "왜 이렇게 했는지"까지 기록되어 있어 유지보수성이 좋은 편.
  이어받기/토큰 재발급/재실행 스킵 등 운영 배려도 잘 되어 있음.
  **7/13 리뷰 이후 코드 자체는 바뀌지 않았고(문서·git 정리만 진행됨), 아래 항목은
  전부 파일을 다시 읽고 현재 코드 기준으로 재확인한 결과**입니다.

## 7/13 리뷰 이후 달라진 것

| 항목 | 상태 |
|---|---|
| P0 — `.env` git 추적/히스토리 노출 | ✅ **해결**. `git filter-repo`로 전체 히스토리에서 제거 후 force push 완료. 단, public 저장소에 노출됐던 기간이 있어 **CDSE 비밀번호·S3 키 자체는 아직 미변경** — TODO 참고 |
| SLC RTC "실패 6건" | 재확인 결과 **버그 아님**. footprint 대조로 AOI 미교차 씬의 정상 스킵임을 확인 (아래 "결과값 리뷰" 참고). 이전 리뷰의 "의도 불명확" 서술을 정정 |
| EBE9 SLC 다운로드 | ✅ 완료 (7.38GB). 다만 이 씬은 위도 38.25°~40.28°(북한 쪽)라 RTC 대상 아님 |
| P1~P3의 코드 수정 항목들 | **전부 미착수**. 아래 내용은 지난 리뷰와 동일하며, 코드를 다시 읽고 현재도 유효함을 확인한 것 |

---

## 심각도 요약

| 등급 | 건수 | 내용 |
|------|------|------|
| **P0 (긴급/보안)** | 1 | ~~git 추적~~ 완료, **CDSE 비밀번호·S3 키 변경**은 아직 미완 |
| **P1 (결과값에 영향)** | 3 | 모자이크 NoData 미지정, HAND 다운로드 무결성, baseline CRS 가정 (GRD 미사용 항목은 방침 확인 필요로 재분류) |
| **P2 (견고성/중복)** | 8 | 다운로드 재시도 로직, 코드 중복(4계열), 하드코딩, 실험 산출물 정리 등 |
| **P3 (다음 단계/품질)** | 5 | detect_flood 미구현, 임계값 검증, 궤도 방향 혼합, 테스트/로깅 부재 등 |

---

## P0 — 보안: 자격증명 노출 (부분 해결, 후속 조치 필요)

**완료**: `git filter-repo --invert-paths --path .env`로 전체 커밋 히스토리에서 `.env` 제거,
`git push --force`로 GitHub(`Ha-eunYu/Sentinel-1_pipline`, public)에 반영. 현재 `git ls-files`에
`.env`가 나타나지 않음(추적 해제 확인).

**아직 안 끝난 것**: 히스토리 세척은 "앞으로의 노출"만 막을 뿐, **이미 public이었던 기간
(커밋 `b41b9b6`부터, 수개월) 동안 크롤러 캐싱이나 fork 가능성은 되돌릴 수 없습니다.**
노출됐던 값: `CDSE_USERNAME`, `CDSE_PASSWORD`, `CDSE_S3_ACCESS_KEY`, `CDSE_S3_SECRET_KEY`
(실제 값은 이 문서에 다시 남기지 않음 — TODO_KR.md P0 항목 참고).

**조치 (TODO_KR.md P0 항목 참고)**: CDSE 비밀번호 변경, S3 키 재발급/폐기. 코드 변경은 필요
없음 (`.env`는 이미 `.gitignore`에 있고 예시 파일 `.env.example`만 커밋됨).

---

## P1 — 결과값(데이터)에 영향을 주는 문제

### 1. `build_rtc_mosaic.py` — VRT 생성 시 NoData 미지정 ([build_rtc_mosaic.py:62](build_rtc_mosaic.py#L62))

SNAP이 쓰는 RTC dB GeoTIFF는 화면 밖 영역이 **0으로 채워져 있고 NoData 태그가 없습니다**
(그래서 `build_baseline_water.py`가 `src_nodata=0.0` 우회를 하고 있음).
`gdalbuildvrt`에 NoData를 알려주지 않으면, **VRT에서 프레임이 겹치는 구간은
"나중에 나열된 파일이 이긴다"** 규칙 때문에 위 프레임의 0(빈 영역)이 아래 프레임의
유효 dB 값을 덮습니다. 같은 날짜 이웃 프레임 경계에서 유효 데이터가 0으로 바뀌고,
baseline 단계에서는 그 픽셀이 "미관측"으로 처리되어 커버리지가 실제보다 줄어듭니다.

**수정:**

```python
cmd = ["gdalbuildvrt", "-overwrite", "-srcnodata", "0", "-vrtnodata", "0",
       str(out_vrt)] + [str(t) for t in tifs]
```

추가로 `subprocess.run(..., capture_output=True)`는 실패 시 stderr가 사라지므로,
`check=True`로 예외가 날 때 `e.stderr`를 출력하거나 `capture_output`을 빼는 것을 권장.
프레임 간 해상도가 미세하게 다를 수 있으므로 `-resolution highest`도 고려.

### 2. `download_hand.py` — 다운로드 무결성 검증 없음 ([download_hand.py:83-91](download_hand.py#L83-L91))

타일을 최종 파일명으로 직접 스트리밍하기 때문에, 중간에 끊기면 **잘린 .tif가 남고
재실행 시 `out.exists() and size > 0` 검사를 통과해 "이미 있음"으로 건너뜁니다.**
손상된 HAND가 조용히 수체 탐지에 들어가는 경로입니다. `stac/download_s1.py`는 이미
`.part` + 크기 검증 + rename 패턴을 갖추고 있으므로 같은 방식을 적용하세요:

```python
tmp = out.with_suffix(out.suffix + ".part")
r = requests.get(url, stream=True, timeout=120)
...
expected = int(r.headers.get("Content-Length", 0))
with open(tmp, "wb") as f:
    for chunk in r.iter_content(chunk_size=1 << 20):
        f.write(chunk)
if expected and tmp.stat().st_size != expected:
    tmp.unlink()
    raise IOError(f"불완전 다운로드: {out.name}")
tmp.replace(out)
```

### 3. `build_baseline_water.py` — CRS 가정이 코드로 강제되지 않음 ([build_baseline_water.py:108](build_baseline_water.py#L108))

`reproject_to_grid()`가 `dst_crs=src.crs`를 쓰면서 "전부 EPSG:4326이므로"라는 주석에
의존합니다. 기준 격자(transform)는 **경위도(도 단위)로 만들어지므로**, 나중에 UTM으로
Terrain-Correction한 산출물이 섞이면 조용히 완전히 어긋난 결과가 나옵니다. 가정을 assert로:

```python
with rasterio.open(src_path) as src:
    if src.crs and src.crs.to_epsg() != 4326:
        raise ValueError(f"EPSG:4326이 아닌 입력: {src_path} ({src.crs})")
```

부수 의견: `valid = np.isfinite(db) & (db != 0)`에서 정확히 0.0 dB인 유효 픽셀(선형 1.0,
드물지만 도심 강반사면에서 가능)이 미관측 처리됩니다. 현실적으로 영향은 미미하나,
근본 해결은 SNAP 출력에 NoData 태그를 부여하거나(후처리 `gdal_edit -a_nodata 0`)
전처리 그래프 출력 후 일괄 태깅입니다.

### (참고) GRD RTC 산출물(14개, ≈수십GB)이 다운스트림에서 미사용

`build_rtc_mosaic.py`는 `downloads/rtc`(SLC)만 읽고, `build_baseline_water.py`도 SLC
모자이크만 씁니다. `batch_grd_rtc.py`로 만든 `downloads/rtc_grd/*.tif` 14개는 QGIS 수동
확인 외에 파이프라인 어디에도 연결되어 있지 않습니다. **버그는 아니지만 방침을
정해야 함** — 의도(광역 육안 확인용)라면 README에 명시하고, 아니라면:

- `build_rtc_mosaic.py`에 `--dir rtc_grd` 옵션을 추가해 GRD도 날짜별 VRT 생성
- baseline을 SLC(AOI 정밀) / GRD(광역) 두 벌로 만들거나, GRD를 post-event 광역
  1차 스크리닝 용도로 명문화

---

## P2 — 견고성 / 구조 개선

### 4. `main_s1_list.py` ↔ `main_s1_list_grd.py` — 사실상 전체 중복 (각 ~215줄)

두 파일의 차이는 `collection`, manifest 파일명, 다운로드 폴더 3곳뿐입니다.
수정할 때마다 두 곳을 고쳐야 하고 실제로 diverge할 위험이 큽니다. 하나로 합치세요:

```python
# main_s1_list.py
parser.add_argument("--product", choices=["slc", "grd"], default="slc")
...
PRODUCT_PRESETS = {
    "slc": ("sentinel-1-slc", "s1_stac_list_manifest.json", "sentinel1"),
    "grd": ("sentinel-1-grd", "s1_stac_list_manifest_grd.json", "sentinel1_grd"),
}
```

같은 맥락에서 `targets`의 목표 시각과 `max_downloads`도 CLI 인자로 빼면
"검색 후보 전부(수십 GB) 무조건 다운로드" 리스크(README 주의사항에만 있는)를
`--max-downloads 4` 같은 명시적 선택으로 바꿀 수 있습니다.

**추가 관찰(7/14 재확인)**: 현재 top-k(기본 10) + 위성별 1개 보장 로직은 **같은 패스의
모든 프레임을 받아오지 못할 수 있습니다.** 실제로 6/25 S1A 프레임 중 하나
(`S1A_IW_SLC..._BA53`)가 South_Korea 폴리곤과 교차함에도 미다운로드였는데, 다행히 AOI
관점에서는 이미 받은 `1257` 프레임과 완전히 중복되어 실질적 손실은 없었습니다. 이런
우연에 의존하지 않으려면, "검색 AOI와 교차하는 후보는 위성/날짜와 무관하게 전부
포함" 옵션을 추가하는 것이 안전합니다 (현재는 시간 최근접 top-k라 프레임이 누락될
구조적 여지가 있음).

### 5. AOI/GeoJSON 처리 함수가 4곳에 산재

| 함수 | 위치 | 역할 |
|------|------|------|
| `load_geojson_geometry` | main_s1_list*.py (2벌 중복) | geometry 추출 |
| `aoi_wkt_from_geojson` + `_iter_lonlat` | prepro_gpt.py | bbox → WKT |
| `aoi_bbox` | build_baseline_water.py | bbox 튜플 |
| `aoi_bbox` | download_hand.py (또 중복) | bbox 튜플 |

`build_baseline_water.aoi_bbox`와 `download_hand.aoi_bbox`는 `coordinates[0]`만 읽으므로
MultiPolygon이나 FeatureCollection(피처 2개 이상)이 오면 **조용히 첫 링만 반영**됩니다.
`prepro_gpt`의 `_iter_lonlat` 재귀 방식이 가장 견고하므로, `geoutil.py` 하나로 통합 후
전부 그것을 쓰세요:

```python
# geoutil.py (신규)
def load_geometry(path) -> dict: ...          # main_s1_list의 것
def bbox_of(path, margin_deg=0.0) -> tuple: ...  # _iter_lonlat 기반
def bbox_to_wkt(bbox) -> str: ...
```

`AOI_MARGIN_DEG = 0.1`도 현재 prepro_gpt(기본 인자), build_baseline_water, download_hand
세 곳에 따로 존재합니다. 한 곳(예: config.py)으로 모으지 않으면 서로 어긋났을 때
HAND 커버리지와 RTC 서브셋 범위가 미묘하게 불일치하는 사고로 이어집니다.

### 6. `batch_slc_rtc.py` ↔ `batch_grd_rtc.py` — 러너 구조 중복

SSD 복사 → 그래프 빌드 → 실행 → 실패 시 산출물 삭제 → 복사본 정리 루프가 동일합니다.
`run_batch(zips, out_dir, graph_factory)` 형태의 공용 함수로 추출 가능. 추가 개선:

- `tempfile.gettempdir()`이 항상 SSD라는 보장이 없음(사용자/시스템 설정에 따라 이동 가능).
  복사 대상 경로를 설정으로 빼고, **복사 전 남은 용량 확인** (`shutil.disk_usage`).
- `KeyboardInterrupt`로 중단하면 gpt가 쓰다 만 `out_tif`가 남는데 현재는 정상 예외만
  삭제 처리됩니다. `finally`에서 "이번 실행에서 완료 flag가 없으면 삭제"로 바꾸면
  README의 "비정상 종료 후 수동 삭제" 주의사항 자체를 없앨 수 있습니다.
- `batch_slc_rtc.py`의 `YEAR_FILTER = "_2026"` 같은 부분 문자열 매칭은 씬 ID 다른 위치와
  우연히 일치할 수 있으므로 `DATE_PATTERN`(build_rtc_mosaic의 정규식)을 재사용해 날짜를
  파싱해서 비교 권장.
- **`batch_slc_rtc.py`의 "AOI 미교차 스킵"과 "진짜 실패"가 로그 문자열로만 구분됩니다**
  (`실패(AOI 미교차 씬일 수 있음)`). 7/13에 이 배치를 재실행했을 때 결과(성공 0/스킵
  6/실패 6)만 보면 버그처럼 보였고, 실제로는 SNAP 로그를 열어 `SubsetOp: No
  intersection`을 확인하고서야 정상임을 알 수 있었습니다. `SubsetOp` 예외 메시지를
  구분해 "AOI 미교차(정상)"와 "그 외 실패"를 별도 카운터로 나누면 재실행할 때마다
  이런 재확인이 필요 없어집니다.

### 7. `stac/download_s1.py` — 재시도 로직 다듬기

전체적으로 잘 만들어졌으나(이어받기, Range 무시 대응, 크기 검증, 토큰 재발급):

- **[download_s1.py:118](stac/download_s1.py#L118)** `out_path.exists()` 스킵 검사가
  Range 헤더 설정·"Downloading" 출력 **이후**에 있습니다. 함수 맨 앞으로 이동.
- **[download_s1.py:205-217](stac/download_s1.py#L205-L217)** 재시도 루프가 401/403/404
  같은 비일시적 오류에도 3회 반복합니다. `requests.HTTPError`의 상태코드를 보고
  4xx(429 제외)는 즉시 중단 권장. 시도 사이 대기(backoff)도 없습니다 —
  `time.sleep(30 * attempt)` 정도 삽입.
- `get_cdse_access_token()`이 루프 **안**에서 실패하면 재시도 카운트를 소모하지 않고
  즉시 전파됩니다(토큰 서버 일시 장애에 취약). try 안으로 이동.
- `make_session()`의 `Retry(backoff_factor=10, total=10)`은 최악의 경우 수십 분을
  침묵 대기합니다. 외부 재시도 루프가 있으므로 내부 Retry는 3~5회로 축소 권장.
- **(7/14 관찰)** `download.dataspace.copernicus.eu` OData 엔드포인트는 Range 요청을
  무시하고 200 전체 응답을 줄 수 있음을 실제로 확인했습니다(EBE9 재다운로드 때
  3.1GB 이어받기 실패, 전체 재다운로드). 현재 코드가 이 경우를 감지해 처음부터
  다시 받도록 처리하는 것 자체는 정확하지만(download_s1.py:139-143), zipper URL
  대신 이 엔드포인트를 쓸 때는 이어받기를 기대할 수 없다는 점을 주석/README에
  명시해두면 좋겠습니다.

### 8. `config.py` — 죽은 설정과 의외의 폴백

- `CDSEConfig.cdse_client_id/secret`은 어디서도 사용되지 않습니다(다운로드는
  USERNAME/PASSWORD 방식). 혼란 방지를 위해 제거하거나 "미사용/향후 OAuth용" 주석 명시.
- `load_env()`의 폴백 후보 `../s2/.env`는 이 저장소 밖의 경로라 다른 환경에서
  의도치 않은 자격증명을 읽을 수 있습니다. 제거하거나 README에 명시.
- `OutputConfig.out_dir`이 상대경로 `./downloads`라 **실행 위치에 따라 결과 폴더가
  바뀝니다.** 다른 스크립트들(`build_baseline_water.py` 등)은 `Path(__file__).parent`
  기준 절대경로를 쓰므로 통일 권장: `Path(__file__).resolve().parent / "downloads"`.

### 9. `prepro_gpt.py` / `prepro_grd_gpt.py` — 하드코딩

- `SNAP_BIN = r"C:\Program Files\snap\bin"` ([prepro_gpt.py:41](prepro_gpt.py#L41)),
  gpt 캐시 `-c 14G`, 스레드 수가 소스에 박혀 있습니다. `.env`로 이동:
  `SNAP_BIN`, `GPT_CACHE=14G`, `GPT_THREADS=8` → 다른 PC(램 32GB 미만 등)에서
  소스 수정 없이 조정 가능. **다른 컴퓨터로 이어서 작업하실 계획이 있다면
  이 항목의 우선순위가 특히 높습니다** — SNAP 설치 경로가 다르면 이 하드코딩된
  경로부터 깨집니다.
- import 시점에 `os.environ["PATH"]`를 변경하는 부작용은 이 모듈을 라이브러리로
  import하는 모든 곳(batch_*, compare_dem_rtc, export_graph_xml)에 전파됩니다.
  동작은 하지만, `get_gpt_cmd()` 호출 직전에 설정하는 함수로 감싸는 편이 안전.
- GRD 체인의 Speckle-Filter에 `numLooksStr` 미지정([prepro_grd_gpt.py:160](prepro_grd_gpt.py#L160)) —
  GRDH는 ENL≈4.4이므로 SLC 버전처럼 룩 수를 넘겨주면 필터 강도가 더 적절해집니다.
- `main()`의 수동 인자 파싱(`--dem`, `--aoi`)은 이미 표준 라이브러리 `argparse`를 쓰는
  다른 스크립트와 스타일이 갈립니다. argparse로 통일.

### 10. `compare_dem_rtc.py` — 차분 맵 비압축 저장

`_dem_diff.tif`가 673MB로 저장되어 있습니다(동일 정보의 `_dc_dem_diff.tif`는 41MB —
이미 압축 버전이 실험적으로 만들어져 있는 것으로 보아 압축 자체는 검증됨).
프로파일 복사 시 압축을 명시하세요:

```python
profile = src.profile | {"dtype": "float32", "nodata": np.nan,
                         "compress": "DEFLATE", "predictor": 3}
```

### 11. `stac/check_kml_dam_korea.py`, `stac/batch_check_kml_dams.py` — 이 저장소 소속이 아님

- K-water 댐 AOI 국가 분류 작업용 스크립트로, S1 홍수 파이프라인과 무관하며
  `E:\~K-water_지상국\...` 절대경로가 하드코딩되어 있습니다. 별도 저장소/폴더로 분리 권장.
- `import geopandas as gpd`가 두 번([check_kml_dam_korea.py:14,18](stac/check_kml_dam_korea.py#L14)).
- `batch_check_kml_dams.py`는 `from check_kml_dam_korea import ...`(패키지 접두사 없음)라
  **cwd가 `stac/`일 때만 동작** — 다른 스크립트들의 `from stac.models import ...` 방식과 충돌.
- geopandas는 `environment.yml` 어디에도 없어(`pip: shapely`만 있음) 현재 두 환경 모두에서
  이 스크립트가 실행 불가.
- `stac/` 패키지에 `__init__.py`가 없습니다. Python 3.3+ 네임스페이스 패키지로 동작은
  하지만, 도구(mypy, pytest) 호환성을 위해 빈 `__init__.py` 추가 권장.

---

## 결과값(downloads/) 리뷰 — 2026-07-14 기준

### 현황 요약

| 폴더 | 내용 | 상태 |
|------|------|------|
| `sentinel1/` (SLC 원본) | 2026년 씬 14개 (6/25~7/3) + 2022 Jeddah 1개(11GB) | ✅ 완결 |
| `sentinel1_grd/` (GRD 원본) | 14개 (6/25~7/3) | ✅ 완결 |
| `rtc/` (SLC RTC) | 6개(AOI 교차 씬 전부) + 날짜별 VRT 4개 | ✅ 완결 (지난 리뷰 때 "미완"으로 오인했던 부분 해소) |
| `rtc_grd/` (GRD RTC) | 14개 + DEM 비교 실험 4개(1개 씬) | ⚠ 실험 잔재 |
| `hand/` | 타일 4개 + VRT | 정상 |
| `water/` | 날짜별 마스크 4개 + baseline/frequency/observed | 정상 |
| `dem/` | NGII 5m AOI 클립 (2.2GB) | 정상 |

### 관찰 사항

1. **SLC 다운로드·RTC 완결**: `S1C_..._EBE9`(6/26, 3.1GB에서 중단됐던 것)를 7/13 재다운로드로
   완료했습니다(7.38GB). 다만 이 씬은 위도 38.25°~40.28°(휴전선 이북)라 홍수 AOI와
   무관하며 RTC 대상이 아닙니다 — SLC 원본 14개는 전부 갖췄지만 RTC가 필요한 건
   AOI 교차 씬 6개뿐이고, 이 6개는 전부 처리 완료된 상태입니다.
2. **7/3 SLC 3개 등 RTC 미생성분은 의도된 정상 동작**입니다(이전 리뷰에서 "의도 불명"으로
   남겼던 부분). SNAP 로그 확인 결과 `SubsetOp: No intersection with source product
   boundary`로 실패하며, 이는 이 씬들이 홍수 AOI 경계(126.61~127.39E, 35.91~36.72N)
   바깥이기 때문입니다. `batch_slc_rtc.py`의 로그 문자열 자체가 이미 이 가능성을
   언급하고 있었지만(`"실패(AOI 미교차 씬일 수 있음)"`), 실제 원인 확인에는 로그 파일을
   열어야 했습니다 — P2-6에 개선안 반영.
3. **DEM 비교 실험 잔재**: `*_dem_diff.tif`(673MB) / `*_dc_dem_diff.tif`(41MB, 압축됨) /
   `*_rtc_db_dc_cop.tif` / `*_dc_ngii.tif` 등 접두사·접미사 규칙이 섞인 산출물이
   rtc_grd에 혼재. 실험 결과는 `rtc_grd/experiments/` 하위로 분리하고 명명 규칙(항상
   접미사) 통일 권장 — 현재 상태로는 `*_rtc_db*.tif` 글롭을 쓰는 후속 코드가 실험
   파일을 오인 수집할 수 있음.
4. **2022 Jeddah SLC(11GB)**: 현재 캠페인과 무관한 과거 참조용. `YEAR_FILTER` 덕에 처리는
   안 되지만 디스크만 차지 — 별도 보관 폴더로 이동 권장.
5. **`output_partitioned_stac/output_partitioned_stac.zip`(524KB, 3/18 생성)**: 어떤
   스크립트도 이 폴더를 참조하지 않고 README/PROGRESS 어디에도 없습니다. 출처 불명
   산출물 — 필요하면 문서화, 아니면 삭제.
6. **`downloads/s1_frames_report_GRD.geojson` + `.qmd`**: 현재 `export_frames_geojson.py`는
   SLC+GRD 통합본(`s1_frames_report.geojson`)을 쓰므로 구버전 잔재로 보임. 삭제 권장.
7. **(신규, 7/14 발견) South_Korea 폴리곤과 교차하지만 미다운로드된 SLC 프레임 1개**:
   `S1A_IW_SLC__1SDV_20260625T093113_20260625T093143_065124_083589_BA53`. CDSE STAC을
   직접 조회해 발견했으며, 검색 top-k 로직이 시간상 더 가까운 `1257`을 선택하고
   `BA53`은 탈락시킨 결과입니다. AOI 커버리지 관점에서는 `1257`(위도 35.43~36.62)이
   이미 `BA53`의 AOI 관련 구간(35.91~35.96)을 포함하므로 실질적 손실은 없지만,
   **이건 우연**이며 다른 날짜/AOI에서는 실제 커버리지 손실로 이어질 수 있는 구조적
   허점입니다 (P2-4 참고).
8. **수체 결과 자체는 일관적**: 날짜별 마스크 4개 + union/frequency/observed_count 구성이
   QC 가능한 형태로 잘 설계됨. 다만 아래 P3-2(궤도 방향 혼합) 참고.

---

## P3 — 방법론 / 다음 단계

### 1. detect_flood.py (핵심 목표) — 아직 미구현, 여전히 최우선

홍수일이 7/8인데 확보된 씬이 7/3까지이므로 post-event 영상이 아직 없습니다
(7/14 새벽 촬영분이 카탈로그 등록 대기 중 — PROGRESS_KR.md 참고). 구현 시 권장 구조:

```text
post 수체 후보 = (post dB < th) AND (HAND < th_hand)
신규 침수     = post 수체 후보 AND (baseline == 0)     # 평상시 비수체
미관측 구분   = baseline == 255 인 픽셀은 "판정불가"로 별도 클래스
```

- baseline과 동일한 기준 격자(`build_target_grid`)를 재사용해야 픽셀 정렬이 보장됩니다 —
  P2-5의 공용 모듈로 빼두면 자연스럽게 해결.
- 산출물에 `flood_class.tif`(0=비침수, 1=신규침수, 2=기존수체, 255=판정불가)와
  면적 통계 JSON을 함께 남기면 보고 자동화가 쉬워집니다.
- `260709_침수피해현황_v2.kmz`(공식 피해 현황)가 이미 저장소에 있으므로,
  detect 결과와의 정확도 검증(confusion matrix) 스크립트까지 만들면 임계값 튜닝 근거가 생깁니다.

### 2. baseline에 승교(ascending)/강교(descending) 궤도 혼합

pre-event 4개 날짜 중 6/25·7/2는 오전(09:31, descending), 6/26·7/1은 저녁(21:31~,
ascending)입니다. 레이더 관측 기하가 달라 그림자/레이오버 위치와 수면 거칠기(바람) 조건이
다르므로, 합집합 baseline이 실제보다 넓어질 수 있습니다(의도한 보수성이긴 함).
post-event 영상이 확보되면 **post와 같은 궤도(relative orbit)의 baseline만** 비교에 쓰는
옵션(`--orbit`)을 고려하세요. `water_frequency.tif`로 날짜별 기여를 확인할 수 있게 만들어 둔
것은 좋은 설계입니다.

### 3. 고정 임계값(-16dB / HAND 10m)의 씬별 적응

현재 전 씬 공통 고정 임계값입니다. 씬별 입사각·바람 조건에 따라 최적값이 흔들리므로:

- AOI 히스토그램에서 **Otsu 임계값**을 구해 -16dB과 비교 출력(채택은 수동 판단)
- 수체/육지 이봉성(bimodality)이 약한 씬은 경고 출력

정도의 가벼운 QC만 추가해도 신뢰도가 올라갑니다. 참고로 HydroSAR/OPERA 계열도
초기값 -16dB에서 씬별 적응 임계값으로 발전한 경로를 밟았습니다.

### 4. 테스트 부재

순수 함수들은 테스트 비용이 매우 낮습니다. 최소한 다음 4개만이라도:

- `stac/models.py`: `parse_target_datetime_utc`(KST 오프셋), `make_datetime_range`
  — 특히 후자는 "±N일이지만 하루 경계로 스냅되어 실제 창이 최대 +1일 커지는" 현재 동작을
  테스트로 못박아 의도임을 명시
- `stac/search_s1.py`: `extract_product_id`(strict 양쪽 모드)
- `prepro_gpt.py`: `_iter_lonlat`/`aoi_wkt_from_geojson`(Polygon/MultiPolygon/Feature)
- `main_s1_list.py`: `load_geojson_geometry`(GeometryCollection 경로)

`pytest` + `tests/` 폴더, CI 없이 로컬 실행만으로도 충분한 가치가 있습니다.

### 5. 로깅/재현성

- 전부 `print` 기반이라 배치 실행 이력이 휘발됩니다. `logging` 모듈로 바꾸고 파일 핸들러
  하나만 붙여도(`downloads/logs/batch_YYYYMMDD.log`) 문제 추적이 쉬워집니다.
- `environment*.yml`에 버전 고정이 없습니다(`python=3.10`만 고정). 최소한
  `conda env export --no-builds > environment.lock.yml`을 주기적으로 남기세요.
  esa-snappy는 SNAP 버전과의 궁합이 중요하므로 SNAP 버전(예: 12.x)도 README에 기록 권장.
- `prepro.py`(esa_snappy GPF 직접 호출, 깨진 GeoTIFF 이슈)는 README에 참고용 경고가 잘
  되어 있으나, 실수로 실행하는 것 자체를 막으려면 `reference/` 폴더로 이동하거나
  파일 상단에서 `raise SystemExit("참고용 — prepro_gpt.py를 사용하세요")` 처리 권장.

---

## 우선순위 로드맵 (제안, 7/14 갱신)

| 순서 | 작업 | 규모 |
|------|------|------|
| ~~1~~ | ~~`.env` git 추적 해제~~ | ✅ 완료 (7/13) |
| 1 | **CDSE 비밀번호 변경 + S3 키 재발급** (P0 잔여) | 즉시, 10분 |
| 2 | post-event 영상 확보 대기 → 다운로드 + RTC (외부 요인, PROGRESS_KR.md 참고) | 대기 중 |
| 3 | `build_rtc_mosaic.py`에 `-srcnodata 0 -vrtnodata 0` 추가 후 VRT·baseline 재생성 (P1-1) | 10분 + 재실행 |
| 4 | `download_hand.py` .part 원자적 다운로드 (P1-2) | 30분 |
| 5 | `detect_flood.py` 설계·구현 (P3-1) — post 영상 확보 즉시 착수 가능하도록 골격 먼저 | 1~2일 |
| 6 | `prepro_gpt.py`/`prepro_grd_gpt.py`의 SNAP 경로·gpt 옵션 `.env`로 이동 (P2-9) — **다른 컴퓨터로 옮길 계획이면 우선순위 상향** | 30분 |
| 7 | `geoutil.py` 통합 + `AOI_MARGIN_DEG` 단일화 (P2-5) | 반나절 |
| 8 | main_s1_list 통합(SLC/GRD), argparse화, "AOI 교차 후보 전부 포함" 옵션 추가 (P2-4) | 반나절 |
| 9 | 다운로드 재시도 개선, batch 러너 공용화, AOI 미교차/실패 로그 분리 (P2-6/7) | 1일 |
| 10 | 실험 산출물 정리 + 불명 파일 정리 (결과 3/4/5/6) | 1시간 |
| 11 | 최소 테스트 + 로깅 도입 (P3-4/5) | 1일 |

---

## 잘 된 점 (유지할 것)

- **다운로드 견고성**: `.part` 이어받기, Range 무시 서버 대응, Content-Length 완결성 검증,
  항목별 토큰 재발급 — CDSE의 실제 운영 특성(짧은 토큰 수명, 불안정한 대용량 전송)을
  정확히 반영한 설계. 7/13 EBE9 재다운로드 때 Range 무시 상황이 실제로 발생했고 코드가
  정확히 감지해 처음부터 재다운로드로 전환한 것으로 실전 검증됨.
- **RTC 체인 선택의 근거 문서화**: esa_snappy JVM 방식의 DEM 다운로드 실패를 확인하고
  gpt 실행으로 전환한 이유가 코드 주석과 README에 남아 있어, 나중에 "왜 GPF 직접 호출을
  안 쓰지?"라는 회귀를 막아줌.
- **Beta0 → Terrain-Flattening → Terrain-Correction** 순서, TNR·스펙클 필터 배치 위치 등
  SAR 전처리 순서가 교과서적으로 정확하고 각 단계마다 이유가 주석으로 달림.
- **재실행 안전성**: 배치 러너의 스킵/실패 시 산출물 삭제, manifest 분리(SLC/GRD),
  다운로드 폴더 분리 등 "중간에 끊겨도 다시 돌리면 된다"는 원칙이 일관됨.
- **QC 산출물 동시 생성**: baseline과 함께 water_frequency / observed_count를 만들어
  결과 신뢰도를 별도 데이터 없이 자체 점검 가능.

---

## 2026-07-22 리뷰 — GTC 대조군·배치·경로 재구성

이번 세션 신규/변경분: `build_grd_gtc_graph`+`--gtc`([prepro_grd_gpt.py](prepro_grd_gpt.py)),
[batch_grd_gtc.py](batch_grd_gtc.py), geojson/yml 폴더 이동에 따른 경로 참조 갱신
11개 파일, zip 정리·씬 분리. 이전(7/14) 항목과 별개로 아래만 다룬다.

### 심각도 요약 (이번 분)

| 등급 | 건수 | 내용 |
|------|------|------|
| **P1 (버그, 조치 완료)** | 1 | RTC·GTC 배치 동시 실행 시 임시파일 경로 충돌 → **수정 완료** |
| **P2 (견고성/중복)** | 2 | 두 그래프 빌더 90% 중복, GTC 산출물의 탐지 파이프라인 오용 위험(문서로 방어) |
| **P3 (품질)** | 1 | 배치 대상 목록을 시작 시점에만 읽음(실행 중 유입분 누락) — 의도된 동작이나 명시 |

### P1 — 배치 임시파일 충돌 (✅ 수정 완료)

- **문제**: `batch_grd_rtc.py`·`batch_grd_gtc.py`가 둘 다 입력 zip을
  `Path(tempfile.gettempdir()) / zip_path.name`로 복사했다. 두 배치를
  **동시에** 돌리면(사용자가 검토했던 시나리오) 같은 씬을 비슷한 시각에
  처리할 때 동일 임시경로에 서로 덮어써 `shutil.copy2` 실패·gpt 입력 손상·
  `finally`의 `unlink`가 상대 프로세스 파일을 지우는 등 오작동 가능.
- **조치**: 각 러너가 모드별 접두사(`rtc_`/`gtc_`)를 붙이도록 수정 →
  경로가 절대 겹치지 않음. 단일 배치 내부는 원래부터 순차라 무관.
- **파일**: [batch_grd_rtc.py](batch_grd_rtc.py):46, [batch_grd_gtc.py](batch_grd_gtc.py):51.

### P2 — 그래프 빌더 중복

- `build_grd_gtc_graph`는 `build_grd_rtc_graph`와 ~90% 동일하고, 딱
  (a) Calibration 밴드(Beta0↔Sigma0), (b) Terrain-Flattening 유무만 다르다.
  Speckle 필터·리샘플링·픽셀간격 등을 나중에 바꾸면 **두 함수를 모두**
  고쳐야 하는 유지보수 부담이 있다.
- **권고(미적용)**: `flatten: bool` 파라미터 하나로 합치거나, 공통 앞단
  (Read~Speckle)을 헬퍼로 추출. 다만 현재는 "육안으로 두 그래프 차이를
  명확히 보여준다"는 교육적 이점이 있어 의도적 중복으로 볼 수도 있음 —
  즉시 수정보다 다음 리팩터 때 검토 권장.

### P2 — GTC 산출물 오용 위험 (문서로 방어)

- GTC는 Sigma0 기준, RTC는 Gamma0(TF) 기준이라 dB 절대수준이 다르다.
  고정 임계값 -16dB는 RTC에 맞춰진 값이므로 `_gtc_db.tif`를 수체 탐지·
  baseline에 넣으면 임계값이 어긋난다. 두 산출물이 **같은 폴더**
  (`downloads/rtc_grd/`)에 접미사만 다르게 저장되므로 실수 유입 소지가 있음.
- **조치**: [RTC_VS_GTC_KR.md](RTC_VS_GTC_KR.md) 5절에 "GTC는 육안 비교
  전용, 탐지에 넣지 말 것" 경고 추가. 코드 차원의 가드는 없음(탐지
  스크립트가 `_rtc_db.tif`만 glob하도록 이미 되어 있어 실질 위험은 낮음).

### P3 — 배치 대상 목록 스냅샷

- 두 배치 모두 시작 시 `sorted(GRD_DIR.glob("*.zip"))`을 한 번만 읽어,
  실행 중 NAS rsync로 새로 들어온 zip은 그 회차에 포함되지 않는다.
  재실행하면 잡히므로 버그는 아니나, GTC 배치 문서에 명시함.

### 좋은 점

- **모드 전환 설계가 깔끔**: `--gtc` 플래그 하나로 `graph_builder`만 바꾸고
  XML 파일명(`s1_grd_to_gtc_db.xml`)·출력 접미사(`_gtc_db`)까지 일관 분기.
- **경로 재구성 안전성**: geojson을 `geojson/`으로 옮기며 참조 11개 파일을
  일괄 갱신하고 AST 구문검사로 검증. `Path(__file__).parent / "geojson" / ...`
  패턴으로 cwd 비의존이라 어디서 실행해도 동작.
- **파괴적 작업 전 검증**: 씬 삭제·이동 전에 footprint 폴리곤 교차·픽셀
  좌표를 실제로 확인하고([SCENE_FOOTPRINT_REAUDIT_KR.md](SCENE_FOOTPRINT_REAUDIT_KR.md)),
  RTC+GTC 둘 다 끝난 zip만 골라 삭제하는 등 되돌리기 어려운 작업에 방어적.
