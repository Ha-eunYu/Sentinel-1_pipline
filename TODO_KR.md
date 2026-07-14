# TODO (2026-07-14 갱신)

다른 컴퓨터에서 이어서 작업할 때 참고하는 실행 목록. 배경·근거는
[CODE_REVIEW_KR.md](CODE_REVIEW_KR.md)(코드 품질)와 [PROGRESS_KR.md](PROGRESS_KR.md)
(작업 이력·데이터 현황)에 있고, 여기는 "무엇을 해야 하는지"만 체크리스트로 정리합니다.

## P0 — 지금 바로 (다른 작업보다 먼저)

- [ ] **CDSE 비밀번호 변경**. `.env`가 한동안 public GitHub에 커밋돼 있었고
      (`git filter-repo`로 히스토리에서는 제거했지만 노출 자체는 되돌릴 수 없음),
      실제 `CDSE_PASSWORD` 값이 노출됐었습니다.
      <https://dataspace.copernicus.eu> 계정 설정에서 변경.
- [ ] **S3 access/secret key 재발급**. 같은 `.env`에 `CDSE_S3_ACCESS_KEY`,
      `CDSE_S3_SECRET_KEY`도 있었습니다. 발급받은 콘솔에서 폐기 후 재발급.
- [ ] 두 값을 로컬 `.env`(현재 이 컴퓨터)와, 다른 컴퓨터로 옮길 경우 그쪽 `.env`에도 갱신.
- [ ] **(신규, 7/14) `.env` 재발급 시 반드시 백업해둘 것**: 오늘 `git filter-repo`
      실행 중 로컬 `.env`가 통째로 삭제되는 사고가 있었음(아래 P4 참고). 지금
      만드는 새 `.env`는 프로젝트 밖(예: 비밀번호 관리자, 클라우드 노트)에도
      한 부 저장해두면 같은 사고가 나도 git 작업만으로 복구 가능.

## P1 — post-event 영상 (진행 중)

- [x] **S1C 하강 패스(2026-07-13 21:39~21:40 UTC, KST 7/14 06:39경) 카탈로그
      게시 확인** — 홍수일(7/8) 이후 최초 post-event 영상. 촬영→게시까지 실측
      약 4시간 걸림(오전 10:13 KST 확인 때는 게시 전이라 놓쳤었음, 10:43 게시).
- [x] **post-event GRD 다운로드 완료** (7/14 14:05~14:08) — 3개 신규:
      `93FC`/`3C22`/`1A5A` (`sentinel1_grd/`에 있음, 이 중 `3C22`·`1A5A`가 홍수
      AOI와 직접 겹침).
- [x] **post-event GRD RTC 완료** (7/14 14:08~15:54) — `93FC`(북한, AOI 무관)
      69.4분, `3C22`(AOI 겹침) 25.8분, `1A5A`(AOI 겹침) 10.5분. 뒤 두 개가 훨씬
      빠른 이유: 인접 pre-event 씬 처리 때 이미 Copernicus 30m DEM 타일이
      캐시돼 있었기 때문(93FC는 처음 다루는 위도대라 DEM을 새로 받음).
- [x] 모자이크 생성 — **단, `build_rtc_mosaic.py`가 아니라 `gdalbuildvrt`를
      직접 실행**했습니다. 이 스크립트는 `downloads/rtc`(SLC)만 읽도록
      하드코딩돼 있어 GRD(`downloads/rtc_grd`)는 지원하지 않기 때문
      (P5 항목 참고 — `--dir` 옵션 추가하면 스크립트로도 가능해짐). 대신
      P3의 NoData 버그 수정(`-srcnodata 0 -vrtnodata 0`)은 이번 명령에 반영
      해뒀습니다. 결과: `downloads/rtc_grd/s1_rtc_db_mosaic_20260713.vrt`
      (93FC 포함 3개 전부). 3C22·1A5A만 다시 묶고 싶으면 같은 명령에서
      93FC만 빼고 재실행.
- [ ] **post-event SLC는 보류 중** (사용자가 "다음에 하겠습니다"로 명시적으로
      미룸). 재개 시 대응 씬 ID: `S1C_IW_SLC__1SDV_20260713T213913..._41E9`,
      `..._213938..._64C0`, `..._214004..._04E2`. `conda run -n s1_pipeline
      python main_s1_list.py` (기존 파일은 자동 스킵) →
      `conda run -n s1_snappy python batch_slc_rtc.py`.

## P2 — detect_flood.py 구현 (핵심 목표, post 영상 확보 후 착수)

- [ ] `detect_flood.py` 신규 작성. `build_baseline_water.py`의 `build_target_grid`,
      `reproject_to_grid`, dB+HAND 판정 로직을 재사용:
  ```
  post 수체 후보 = (post dB < -16) AND (HAND < 10m)
  신규 침수     = post 수체 후보 AND (baseline_water_union == 0)
  판정불가      = baseline_water_union == 255 인 픽셀
  ```
- [ ] 산출물: `flood_class.tif` (0=비침수, 1=신규침수, 2=기존수체, 255=판정불가) +
      면적 통계 JSON.
- [ ] `260709_침수피해현황_v2.kmz`(저장소에 이미 있음, 공식 피해 현황)와 대조해
      confusion matrix 스크립트 작성 → 임계값(-16dB/HAND 10m) 튜닝 근거 확보.
- [ ] baseline 궤도 방향(ascending/descending) 혼합 이슈 — post와 같은
      relative orbit의 baseline만 비교하는 `--orbit` 옵션 고려
      (CODE_REVIEW_KR.md P3-2).

## P3 — 결과값 정확도에 영향 (코드 수정, 언제든 가능)

- [ ] `build_rtc_mosaic.py:62` — `gdalbuildvrt`에 `-srcnodata 0 -vrtnodata 0` 추가.
      현재 프레임 겹침 구간에서 위 프레임의 빈 영역(0)이 아래 프레임의 유효 dB를
      덮어써 baseline 커버리지가 실제보다 줄어드는 버그. 수정 후
      **기존 VRT·baseline 재생성 필요**. (7/14, GRD post-event 모자이크는
      `gdalbuildvrt`를 직접 실행하면서 이 옵션을 수동으로 넣었지만, 스크립트
      본체는 아직 안 고쳐서 SLC 쪽 기존 VRT 4개는 여전히 버그 있는 상태.)
- [ ] `download_hand.py:83-91` — HAND 타일 다운로드에 `.part` 임시파일 +
      Content-Length 검증 추가 (`stac/download_s1.py` 패턴 재사용). 현재는
      중간에 끊긴 손상 타일이 재실행 시 "이미 있음"으로 조용히 통과됨.
- [ ] `build_baseline_water.py:108` — `dst_crs=src.crs`가 "전부 EPSG:4326"이라는
      주석에만 의존. UTM 등 다른 CRS 입력이 섞이면 조용히 어긋나므로 assert 추가.

## P4 — 이식성 (다른 컴퓨터로 옮길 계획이 있다면 우선순위 높음)

- [ ] **(7/14 사고 기록)** `git filter-repo --invert-paths --path .env` 실행 중
      로컬 `.env`가 디스크에서도 삭제됨 — `.gitignore`에 있어도 "추적되던 파일"이
      히스토리 재작성으로 트리에서 사라지면 작업 트리 정리 과정에서 함께 지워짐.
      reflog도 filter-repo가 즉시 만료시켜 git으로 복구 불가했음. **앞으로 히스토리
      재작성(filter-repo, rebase, reset --hard 등) 전에는 `.env`류를 프로젝트 밖으로
      먼저 복사해둘 것.**
- [ ] `prepro_gpt.py:41`, `prepro_grd_gpt.py:36` — `SNAP_BIN = r"C:\Program
      Files\snap\bin"` 하드코딩. 다른 PC는 SNAP 설치 경로가 다를 수 있으므로
      `.env`의 `SNAP_BIN`으로 이동.
- [ ] 같은 파일들의 `-c 14G`(gpt 캐시), `-q 8`(스레드 수)도 `.env`의
      `GPT_CACHE`/`GPT_THREADS`로 이동 — 램 32GB 미만 PC에서는 `14G`가 과함.
- [ ] `config.py`의 `OutputConfig.out_dir`이 상대경로(`./downloads`)라 실행
      위치에 따라 결과 폴더가 바뀜. `Path(__file__).resolve().parent /
      "downloads"`로 통일.
- [ ] `environment.yml` / `environment_snappy.yml`에 버전 고정이 없음
      (`python=3.10`만 고정). `conda env export --no-builds`로 lock 파일을
      만들어두면 다른 컴퓨터에서 같은 환경 재현이 쉬움. SNAP 버전(예: 12.x)도
      README에 기록 권장.

## P5 — 구조 정리 (급하지 않음, 유지보수성)

- [ ] `main_s1_list.py` / `main_s1_list_grd.py` 통합 (`--product slc|grd` 인자).
      겸사겸사 "검색 AOI와 교차하는 후보는 위성/날짜와 무관하게 전부 포함" 옵션
      추가 — 현재 top-k 로직은 같은 패스의 일부 프레임이 우연히 탈락할 수 있음
      (실례: 7/14 재검증 중 발견한 `S1A..._BA53` 미다운로드, 다행히 AOI상 중복이라
      손실은 없었음).
- [ ] AOI/geojson 처리 함수 4곳 중복(`main_s1_list*.py`, `prepro_gpt.py`,
      `build_baseline_water.py`, `download_hand.py`) → `geoutil.py`로 통합.
      `AOI_MARGIN_DEG = 0.1`도 세 곳에 흩어져 있음 → 한 곳으로.
- [ ] `batch_slc_rtc.py` / `batch_grd_rtc.py` 러너 중복 → 공용 함수로 추출.
      실패 시 "AOI 미교차(정상)"와 "그 외 실패"를 로그에서 구분 (현재는 SNAP 로그를
      직접 열어봐야 구분 가능).
- [ ] `stac/check_kml_dam_korea.py`, `stac/batch_check_kml_dams.py` — 이 저장소와
      무관한 K-water 댐 스크립트(하드코딩된 `E:\` 경로 포함). 별도 저장소로 이동.
- [ ] 정리 대상 파일: `downloads/rtc_grd`의 DEM 비교 실험 산출물(`*_dem_diff.tif`
      등 4개) → `experiments/` 하위로, 2022 Jeddah SLC(11GB) → 별도 보관,
      `output_partitioned_stac/`(출처 불명, 524KB) → 문서화 또는 삭제,
      `downloads/s1_frames_report_GRD.qmd` → 구버전 잔재, 삭제 권장
      (`s1_frames_report_GRD.geojson`은 7/14에 재생성해서 최신 상태 — 삭제 대상
      아님, 다만 export_frames_geojson.py에는 아직 GRD 전용 옵션이 없어 별도
      스크립트로 만듦. `export_frames_geojson.py`에 `--product grd|slc|all`
      옵션을 추가하면 이 별도 스크립트가 필요 없어짐).
- [ ] 최소 단위 테스트 추가: `stac/models.py`의 `parse_target_datetime_utc`,
      `make_datetime_range`; `stac/search_s1.py`의 `extract_product_id`;
      `prepro_gpt.py`의 `_iter_lonlat`/`aoi_wkt_from_geojson`.
- [ ] `print` 기반 로깅을 `logging` + 파일 핸들러(`downloads/logs/`)로 전환.

## 완료된 것 (참고용, 재작업 불필요)

- [x] GRD 검색·다운로드·RTC 파이프라인 전체 (14/14, 14/14)
- [x] SLC 검색·다운로드 전체 (14/14, EBE9 포함)
- [x] SLC RTC — 홍수 AOI 교차 씬 6/6 (나머지 8개는 AOI 밖이라 처리 대상 아님, 버그 아님)
- [x] HAND 다운로드, NGII DEM 클립, pre-event baseline 수체 지도
- [x] `.env` git 히스토리 세척 + force push (단, 비밀번호/키 자체 변경은 P0 참고)
- [x] git upstream 추적 연결(`git branch --set-upstream-to=origin/main main`)
- [x] post-event GRD 다운로드 + RTC + 모자이크 (3/3, 7/14 완료)
- [x] `s1_frames_report_GRD.geojson` 재생성 (7/14, 17개 프레임 반영)
