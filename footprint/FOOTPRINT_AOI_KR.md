# 위성영상 촬영 지역: bbox 대신 footprint로 판정 (2026-07)

Sentinel-1 프레임이 "어디를 찍었나"를 **bbox(외접 사각형)가 아니라
footprint(실제 촬영 폴리곤)** 로 판정하도록 파이프라인을 정리한 기록.
흩어져 있던 로직을 재사용 모듈 [footprint_aoi.py](footprint_aoi.py) 하나로
통합했다.

---

## 1. 왜 bbox가 틀리나

Sentinel-1 IW 프레임은 궤도 방위각만큼 **기울어진 평행사변형**이다. 이걸
경위도 축에 정렬된 bbox `[minLon, minLat, maxLon, maxLat]`로 감싸면, 프레임이
실제로 찍지 않은 **삼각형 여백**까지 촬영 지역에 포함된다.

```
     실제 footprint (기울어진 평행사변형)        bbox (축 정렬 사각형)
              ●────────●                        ┌───────────────┐
             /        /                         │ ● ─ ─ ─ ─ ● ← │ 여백(안 찍음)
            /        /                          │/          /   │
           /        /                    →      /          /    │
          ●────────●                          │/  ← 여백  /     │
                                              └●─────────●──────┘
```

그 삼각형 여백이 하필 관심 경계(한반도)에 걸치면, **실제로는 100% 바다이거나
중국·일본 전용인 프레임이 bbox 기준으로는 "한반도를 찍었다"** 고 오판된다.

`python footprint/footprint_aoi.py`로 이 오판을 재현할 수 있다(합성 예제):

```
bbox 오판 기하 데모 (경계=[0,1]^2, footprint=기울어진 마름모):
  bbox 가 경계와 겹치나?      : True   <- '찍었다'고 오판
  footprint 가 경계와 겹치나? : False  <- 실제로는 안 찍음
  => bbox_false_positive       : True
```

### 이게 실제로 낸 사고

이 bbox 오판은 문서에 발표됐던 홍수 침수 수치를 아티팩트로 만들었다. 자세한
경위는 [SCENE_FOOTPRINT_REAUDIT_KR.md](../SCENE_FOOTPRINT_REAUDIT_KR.md)에 있다.

- 7/8·7/10 남한 침수 수치(1.64 km²·69.06 km²)의 근거 프레임이 실제로는
  **한반도 육지 겹침 0%**(제주 남쪽·대마도~규슈 방향 먼바다)였다.
- 7/17 행(남한 97.38 km²)도 격리 재계산 결과 물 픽셀이 **전부 동해~일본
  방향 먼바다** — 세 경계 어디에도 0.0%.

근본 원인: 소형 프레임의 겹침 구간을 좌표 어림/bbox로만 판단하고 실제
footprint 폴리곤 교차를 안 했던 것.

---

## 2. 판정 방식 — 검색은 느슨하게, 판정은 footprint로

STAC 검색 자체는 여전히 느슨한 bbox/AOI로 한다(정밀 폴리곤으로 검색하면
경계에 걸친 정당한 프레임을 서버가 통째로 누락시킬 수 있어서다 — 실제로
`geojson/Korea.geojson`이 제주를 빼먹어 프레임 `93DD`가 검색에서 사라진 적이
있다). **정밀한 "한반도 촬영 여부" 판정은 검색 후 footprint로 따로** 한다.

```
STAC 검색(느슨한 bbox AOI)  →  후보 프레임들  →  각 프레임의 실제 footprint를
                                                 한반도 실경계와 교차 판정
                                                 (교집합 0% = 중국/일본/공해 → 제외)
```

경계 파일은 [geojson/Korea_Peninsula.geojson](geojson/Korea_Peninsula.geojson)
(NK+SK, 제주 포함, `unary_union`).

---

## 3. 코드 구성

핵심 로직은 [footprint_aoi.py](footprint_aoi.py) 한 곳에 모았고, 파이프라인의
각 지점은 이 모듈을 가져다 쓰는 얇은 어댑터만 둔다.

| 파일 | 역할 | footprint_aoi에서 쓰는 함수 |
|---|---|---|
| [footprint_aoi.py](footprint_aoi.py) | **공용 판정 로직 (단일 출처)** | — |
| [stac/search_s1.py](../stac/search_s1.py) | 다운로드 파이프라인의 자동 제외 필터 (`touches_korea`) | `footprint_intersects` |
| [verify_scene_footprint.py](verify_scene_footprint.py) | 처리된 래스터의 물 픽셀 사후 검증 | `load_exterior_rings`, `points_in_rings` |
| [export_frames_geojson.py](export_frames_geojson.py) | 실제 footprint를 QGIS용 GeoJSON으로 내보내기 | (STAC footprint 직접 사용, bbox는 fallback) |

### footprint_aoi.py — 두 계층

**(1) 프레임 단위** — shapely, STAC footprint 대조:

- `load_boundary_union(geojson)` — 경계를 하나의 shapely geometry로 union(캐시)
- `footprint_intersects(footprint, boundary)` — 겹치면 True. footprint가
  `None`(STAC이 geometry 미제공)이면 **판단 불가로 보고 안전하게 True**(프레임을
  실수로 버리지 않음)
- `footprint_overlap_ratio(footprint, boundary)` — 겹침 면적 비율(상대 비교용)
- `compare_bbox_vs_footprint(bbox, footprint, boundary)` — 같은 프레임을 bbox로
  판정할 때와 footprint로 판정할 때 차이를 수치로 반환(`bbox_false_positive`
  플래그 포함)

**(2) 픽셀 단위** — 순수 numpy, **shapely 불필요**:

- `load_exterior_rings(geojson)` — (Multi)Polygon 외곽 링을 `Nx2` 배열로
- `points_in_rings(lons, lats, rings)` — 벡터화 ray-casting point-in-polygon
- `fraction_inside(lons, lats, boundary)` — 점들 중 경계 내부 비율

> shapely는 프레임 단위 함수 **안에서만** 지연 import 한다. 그래서 shapely가
> 없는 환경(`s1_snappy`)에서도 픽셀 단위 검증은 그대로 동작한다.

---

## 4. 사용법

### 다운로드 파이프라인 (자동)

`stac/search_s1.py`의 `list_s1_items_for_date(..., exclude_non_korea=True)`가
검색 후보 중 footprint가 한반도와 0% 겹치는 프레임을 자동 제외하고, 제외된
씬 ID를 로그로 남긴다.

```
[footprint 제외] 한반도 교집합 0%(중국/일본 등) 3개: E067, 4C8A, E265
```

### 처리 결과 사후 검증

```bash
conda run -n s1_snappy python footprint/verify_scene_footprint.py --tag 20260716_o003704_3scene \
    --scenes <scene1>_rtc_db.tif <scene2>_rtc_db.tif <scene3>_rtc_db.tif
```

특정 씬만 격리 모자이크 → 수체(dB<-16) 지도 → 물 픽셀을
`Korea_Peninsula`/`South_Korea`/`NK` 경계와 point-in-polygon 대조해 "한반도
내부 몇 %"를 출력한다.

### QGIS 보고

```bash
conda run -n s1_pipeline python footprint/export_frames_geojson.py
```

`downloads/s1_frames_report.geojson`에 각 프레임의 **실제 footprint 폴리곤**을
`status`(downloaded/downloading/planned)와 함께 저장한다. STAC 조회 실패 시에만
manifest의 bbox 사각형으로 대체하고, 어느 쪽인지 `geometry_source` 필드로
구분한다.

### bbox 오판 근거 남기기

특정 프레임에서 bbox 판정이 왜 틀리는지 수치로 남기려면:

```python
from footprint import compare_bbox_vs_footprint
print(compare_bbox_vs_footprint(item.bbox, item.geometry))
# {'bbox_intersects': True, 'footprint_intersects': False,
#  'bbox_false_positive': True, ...}
```

---

## 5. 검증

- **자동 필터 ↔ 수동 재감사 일치**: `touches_korea` 자동 필터가
  SCENE_FOOTPRINT_REAUDIT 2절에서 손으로 찾아낸 비한반도 씬 목록을 그대로
  재현했다. 부수적으로 놓쳤던 정당한 한반도 프레임 2개(`93DD` 제주 인근
  5.27% 겹침, `7805` 궤도 008632 최북단 프레임)도 새로 발견됐다.
- **두 실행 환경 모두 통과**: `s1_pipeline`(shapely)에서 프레임 단위,
  `s1_snappy`(shapely 없음)에서 픽셀 단위가 각각 정상 동작함을 확인.

---

## 관련 문서

- [SCENE_FOOTPRINT_REAUDIT_KR.md](../SCENE_FOOTPRINT_REAUDIT_KR.md) — bbox 오판이
  낸 사고의 상세 감사 기록
- [FLOOD_TIMELINE_KR.md](../FLOOD_TIMELINE_KR.md) — 무효 확정이 반영된 침수 타임라인
- [FLOOD_NORTH_KOREA_KR.md](../FLOOD_NORTH_KOREA_KR.md) — 동일 패턴(baseline 커버리지
  아티팩트)의 최초 규명
