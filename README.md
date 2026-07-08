# Sentinel-1 SLC 검색·다운로드 파이프라인

Copernicus Data Space Ecosystem(CDSE)의 STAC API로 관심 지역(AOI)과 목표 시각에 가장 가까운
Sentinel-1 SLC 영상을 검색하고, OData(zipper) API로 SAFE(zip) 원본을 다운로드하는 파이프라인입니다.
현재는 **2026년 7월 한국 홍수 모니터링**을 위해 Sentinel-1A/C/D 위성을 대상으로 설정되어 있습니다.

(English version: [README_ENG.md](README_ENG.md))

## 결론부터: 클론 후 실행 순서

```bash
git clone <repo-url>
cd Sentinel-1_pipline

conda env create -f environment.yml
conda activate s1_pipeline

cp .env.example .env
# .env 파일을 열어 CDSE_USERNAME / CDSE_PASSWORD 입력

python main_s1_list.py
```

네, **clone 후에는 `main_s1_list.py` 하나만 실행**하면 검색(manifest 저장) + 다운로드까지 한 번에 진행됩니다.
다만 아래 "실행 전 확인할 것"과 "주의사항"은 꼭 먼저 읽어주세요 (특히 디스크 용량 관련).

## 요구사항

- conda (miniconda/anaconda)
- CDSE(Copernicus Data Space Ecosystem) 계정 — <https://dataspace.copernicus.eu> 에서 무료 가입
  - `main_s1_list.py`가 쓰는 인증은 `CDSE_USERNAME`/`CDSE_PASSWORD` (아이디/비밀번호) 방식입니다.
    OAuth client id/secret이 아닙니다.
- 여유 디스크 공간 (아래 "주의사항" 참고 — SLC 1개당 5~8GB 내외)

## 설치

```bash
conda env create -f environment.yml   # 환경 이름: s1_pipeline
conda activate s1_pipeline
```

`.env` 파일은 git에 커밋되지 않습니다(`.gitignore`). `.env.example`을 복사해서 본인 계정 정보를 채워주세요.

```bash
cp .env.example .env
```

```dotenv
# .env
CDSE_USERNAME=본인_CDSE_아이디
CDSE_PASSWORD=본인_CDSE_비밀번호
```

## 폴더 구조

```text
main_s1_list.py           # 실행 진입점: 검색 -> manifest 저장 -> 다운로드
config.py                 # .env 로드, CDSEConfig / OutputConfig
Korea_Peninsula.geojson   # 한반도 전체 폴리곤 (넓은 범위 모니터링용)
Korea_flood_AOI.geojson   # 이번 홍수 피해 확정 지역 AOI (좁은 범위, 빠른 검색용)
stac/
  client.py               # pystac_client로 CDSE STAC 클라이언트 오픈
  models.py                # S1SearchConfig, 날짜/시간 파싱, datetime range 계산
  search_s1.py             # STAC 검색 + 목표 시각 근접도 정렬 + 위성별 커버리지 보장
  download_s1.py           # CDSE 토큰 발급, OData zipper 다운로드(이어받기 지원)
downloads/                 # 실행 결과물 (git에는 안 올라감)
  s1_stac_list_manifest.json
  sentinel1/*.zip
```

## AOI(관심 지역) 설정

`main_s1_list.py`는 기본적으로 `Korea_flood_AOI.geojson`(홍수 피해 확정 지점 4곳을 감싸는 좁은 bbox)을
사용하도록 되어 있습니다.

```python
korea_geojson = Path(__file__).resolve().parent / "Korea_flood_AOI.geojson"
```

한반도 전체를 넓게 모니터링하고 싶다면 이 줄만 `Korea_Peninsula.geojson`으로 바꾸면 됩니다.
단, 범위가 넓을수록 검색 결과가 많아지고 원치 않는(동해/서해 먼바다 등) 영상까지 걸릴 수 있으니
가능하면 `Korea_flood_AOI.geojson`처럼 실제 관심 지역으로 좁히는 것을 권장합니다.

새 지점으로 AOI를 다시 만들고 싶다면 `Korea_flood_AOI.geojson`의 `coordinates`를
[lon, lat] 순서로 수정하면 됩니다 (bbox 사각형 + 여유 buffer 형태).

## 목표 시각(촬영 시각) 설정

`main_s1_list.py`의 `targets` 리스트에서 검색 기준 시각을 지정합니다.

```python
targets = [
    ("Korea_flood", "2026-07-08T18:30:00+09:00"),  # KST 촬영 시각
]
```

- **반드시 타임존 오프셋을 포함해서** 적어주세요 (`+09:00` = KST). 오프셋을 빼고 날짜만 쓰면
  자정(00:00 UTC = 09:00 KST) 기준으로 계산되어 실제 촬영 시각과 어긋난 정렬이 나올 수 있습니다.
- `window_days`(현재 15일)는 이 목표 시각 앞뒤로 며칠 범위를 검색할지 정합니다. `cfg.window_days`에서 조정하세요.

## 검색 결과 정렬 방식

- `sort_by_time_diff=True`(기본값)이면 목표 시각과의 시간차가 작은 순으로 정렬됩니다.
- 전체 상위 k개(top-k, 기본 10개)만 뽑을 때, 특정 위성(S1A/S1C/S1D)이 시간차가 조금 더 크다는
  이유만으로 top-k에서 통째로 빠지지 않도록, **검색 결과에 등장한 위성마다 최근접 후보를 최소 1개씩
  강제로 포함**시킵니다 (`stac/search_s1.py: list_s1_items_for_date`).

## 실행

```bash
python main_s1_list.py
```

실행하면:

1. `Korea_flood_AOI.geojson` AOI + `targets`에 설정한 시각 기준으로 CDSE STAC 검색
2. 검색 결과를 `downloads/s1_stac_list_manifest.json`에 저장
3. **검색된 후보(top-k) 전부**를 순서대로 `downloads/sentinel1/*.zip`에 다운로드
   (이미 받은 파일은 자동 스킵, 중간에 끊기면 다음 실행 시 이어받기)

## 주의사항 (실행 전 꼭 확인)

- **`main_s1_list.py`를 그냥 실행하면 검색된 후보를 전부 다운로드합니다.** Sentinel-1 SLC 1개는
  보통 5~8GB이고, 후보가 여러 개면 순식간에 수십 GB가 필요합니다. 실행 전에 디스크 여유 공간을
  꼭 확인하세요 (`df -h`). 일부만 받고 싶다면 `main()`의 `selected_items` 루프 앞에서 개수를
  제한하거나, `list_s1_items_for_date(..., k=원하는개수)`를 줄이세요.
- CDSE 서버 다운로드가 네트워크 타임아웃으로 중간에 끊기는 경우가 있습니다. `download_odata_cdse`가
  `.part` 임시 파일 기준으로 이어받기를 지원하므로, 에러가 나면 **같은 명령을 다시 실행**하면 됩니다.
- 검색 대상 위성은 코드에 하드코딩되어 있지 않고 CDSE STAC 검색 결과를 그대로 따릅니다. 즉 S1A/S1C/S1D
  중 실제로 해당 AOI·기간에 촬영 이력이 있는 위성만 후보로 나옵니다. 위성 임무 계획(태스킹) 상
  특정 위성이 그 지역/기간에 아예 촬영을 안 했다면 코드가 아니라 실제로 데이터가 없는 것이니
  `window_days`를 늘리거나 시간을 두고 재검색해보세요 (SLC 카탈로그 등록에는 촬영 후 지연이 있습니다).
