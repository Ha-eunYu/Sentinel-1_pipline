# 파이프라인 현황 창 (scene_dashboard)

회사 PC 한쪽에 띄워 두고 **지금 어디까지 됐는지**를 보는 작은 창.
[감시 도구](SCENE_MONITOR_KR.md)가 "새 게 올라왔다"를 알림 한 번으로 알려 준다면,
이 창은 그 다음 질문 — **CDSE에 뭐가 올라왔고, 그중 뭘 받았고, 뭐가 굽는 중이고,
뭐가 끝났나** — 에 답한다.

| 구성 | 경로 | 역할 |
| --- | --- | --- |
| 본체 | [scene_dashboard.py](../../s1/tools/monitor/scene_dashboard.py) | STAC 조회 + 로컬 스캔 + Tk 창 |
| 런처 | [scene_dashboard.ps1](../../scripts/scene_dashboard.ps1) | 콘솔 없이(`pythonw`) 띄우기 |
| 시도 경계 | `geojson/sido_simplified.geojson` | 위치 표시용(충남·전남 …). 326 KB |
| 경계 생성기 | [build_sido_geojson.py](../../s1/tools/monitor/build_sido_geojson.py) | 위 파일을 굽는 1회성 도구(geopandas 필요) |
| 촬영 계획 | [acquisition_plan.py](../../s1/tools/monitor/acquisition_plan.py) | ESA 계획 KML → 앞으로 찍을 것 ([ACQUISITION_PLAN_KR.md](ACQUISITION_PLAN_KR.md)) |
| 캐시 | `downloads/dashboard_cache.json` · `plan_cache.json` | 마지막 STAC·계획 결과. 창을 다시 띄우면 즉시 그린다 |

- **의존성 없음.** 표준 라이브러리와 tkinter뿐. 저장소 모듈은 `s1.core.paths` ·
  `s1.core.scene` · `monitor_new_scenes` 셋만 쓰는데 모두 순수 파이썬이라
  `s1_snappy` 같은 conda 환경 없이 뜬다.
- **상태를 저장하지 않는다.** 갱신할 때마다 파일 시스템과 STAC를 다시 읽는다.
  따로 진행상황 파일을 두면 그 파일이 언젠가 실제와 어긋난다.

---

## 1. 화면

```text
CDSE 08-19 08:26  ·  계획 08-19 08:26  ·  폴더 스캔 08:26:51   [✓항상 위] [새로고침]
최근 7일 15개 · 미수신 0  |  보유 174  |  대기 65 · 처리중 1 · 완료 103 · 제외 5

■ 촬영 — 예정 · 최근
  촬영(KST)         위성 씬    궤도             위치              한반도 상태     비고
  2026-08-26 06:24  S1C  -     rel134 하행(DESC) 함경남도·함경북도·강원  70% 예정     댐·보 42곳
  2026-08-21 06:14  S1C  -     rel61 하행(DESC)  경북·함경북도·경남     20% 예정     댐·보 29곳
  2026-08-19 18:30  S1D  -     rel127 상행(ASC)  전남·전북·경남        16% 예정     댐·보 16곳
  2026-08-14 06:31  S1C  D635  rel134 하행(DESC) 경북·충남·충북        85% 전처리중  1.12 GB
  2026-08-14 06:31  S1C  5ACA  rel134 하행(DESC) 강원·경기·강원도(북)   85% 완료     1.15 GB
  2026-08-08 18:22  S1C  B5F3  rel54 상행(ASC)   -                  0% 제외     0.46 GB

■ 전처리
  촬영(KST)         위성 씬    상태   비고
  2026-08-14 06:31  S1C  D635  처리중 13분 전 시작 · 0.25 GB 기록
  2026-07-31 18:40  S1D  CE22  대기   1.55 GB
  2026-08-02 18:23  S1D  524F  완료   2.48 GB · 14시간 5분 전
```

**시간축은 하나다.** 앞으로 찍을 것(ESA 계획)과 이미 찍힌 것(CDSE 카탈로그)을
한 표에 시간순으로 얹는다. 표를 나누면 "언제 뭐가 찍히나"를 두 군데서 읽어야
한다. 어디까지 왔는지는 `상태` 칸 하나가 말한다:
**예정 → 미수신 → 받는중 → 대기 → 전처리중 → 완료**(그리고 처리 대상이 아닌 **제외**).

⚠ **예정 줄과 카탈로그 줄은 알갱이가 다르다.** 계획 한 줄은 datatake(긴 띠)
하나이고, 그게 카탈로그에 오면 프레임 여러 장이 된다(rel134 한 패스 = 7줄).
그래서 예정 줄은 씬 칸이 `-`이고 색이 초록이다
([ACQUISITION_PLAN_KR.md](ACQUISITION_PLAN_KR.md)).

| 요소 | 규칙 |
| --- | --- |
| **열 이름** | 두 표가 같은 이름·같은 뜻·같은 순서로 시작한다: `촬영(KST)` → `위성` → `씬` → … 표마다 다른 것은 뒤쪽 칸뿐이다 |
| 촬영시각 | **연도까지** 적는다(`2026-08-14 06:31`). 전처리 표에는 작년 비교쌍(2025-07·08)이 섞여 올라오고, 하강궤도는 UTC→KST로 날짜가 하루 넘어간다 |
| 색 | 초록=예정 · 주황=아직 안 받음 · 파랑=진행 중 · 회색=끝난 것·제외 · 빨강=중단? |
| 씬 | `D635`(4hex) 한 칸, 위성은 `위성` 칸으로 분리 — 문서·명령에서 부르는 이름 그대로 |
| 궤도 | `rel134 하행(DESC)` — 한글과 영문 약어를 같이 적는다(외부 도구·파일명은 ASC/DESC를 쓴다). 계획 KML에는 상행/하행이 없어 **관측 시각으로 판정**한다(태양동기 궤도라 한반도에서 상행=KST 18시대, 하행=06시대) |
| 비고 | 카탈로그 줄=원본 크기, 예정 줄=드는 댐·보 개수(51곳 중) |
| 숫자 칸 | 한반도%는 오른쪽 정렬 |
| 더블클릭 | 그 줄의 **씬 파일명 전체**가 클립보드로 (배치 `--only`·삭제 명령에 붙여 넣기) |
| 머리글 클릭 | 그 열로 정렬. 같은 열을 계속 누르면 **내림차순 ▼ → 오름차순 ▲ → 기본**(아래) |
| 창 제목 | `S1 현황 · 처리중 1 · 대기 65` — 최소화해 둬도 작업표시줄에서 읽힌다 |
| 높이 배분 | '촬영'은 줄 수 고정, 남는 높이는 '전처리'가 가져간다 |

두 표 모두 보이는 줄보다 많이 담고 스크롤바가 붙는다. 조회창(`--days`) 밖의
보유분은 '촬영'에 나오지 않고 '전처리'의 대기·완료 목록에서 본다.

**맨 윗줄이 바뀌면 화면도 맨 위로 되돌린다.** Treeview는 내용을 지웠다 다시
채워도 스크롤 위치를 기억해서, 예정 줄이 뒤늦게 붙으면 새 윗줄이 화면 밖에
숨는다(2026-08-19 실측: 예정 6건 중 2건만 보였다). 윗줄이 그대로면 건드리지
않는다 — 20초마다 다시 그리는 화면이라 무조건 올리면 아래를 읽을 수 없다.

### 정렬

머리글을 누르면 그 열로 정렬하고, 갱신해도 유지된다. 같은 열을 다시 누르면
방향이 뒤집히고, **세 번째로 누르면 기본 순서로 돌아온다**(최근 촬영=최신이 위,
전처리=처리중→대기→완료). 되돌릴 자리를 남겨 둔 이유는, 정렬이 걸린 채로 잊으면
"최신이 위"라는 전제가 조용히 깨진 화면을 계속 보게 되기 때문이다.

- 정렬은 **화면에 찍힌 문자열이 아니라 원래 값**으로 한다. `1.12 GB`를 글자로
  세우면 9 GB가 10 GB보다 뒤로 간다.
- `상태` 열은 파이프라인 진행 순서(미수신→받는중→대기→전처리중→중단?→완료)다.
  오름차순으로 두면 **손 볼 것이 위로** 온다.
- 전처리 표의 `비고`는 줄마다 담는 값이 다르므로(경과·크기·완료시각) 정렬
  대상이 아니다 — 머리글을 눌러도 반응하지 않는다.

**시각은 전부 KST**다. 감시 로그(`new_scenes.log`)는 UTC라 하강궤도는 날짜가
하루 어긋나 보인다 — 같은 촬영이다([SCENE_MONITOR_KR.md](SCENE_MONITOR_KR.md) 5-4).

## 2. 상태를 어떻게 판정하나

| 단계 | 근거 |
| --- | --- |
| **예정** | ESA 촬영계획 KML에 있는 앞으로의 한반도 통과 |
| **미수신** | STAC에는 있는데 로컬에 zip이 없다 |
| **받는중** | `sentinel1_grd/*.part` — 다운로더가 이어받기용으로 남기는 임시 파일 |
| **대기** | zip은 있는데 산출물 tif가 없다 |
| **전처리중** | `%TEMP%/frostrtc_*` 등 **임시폴더**에 그 씬의 zip이 복사돼 있다 |
| **완료** | 산출물 tif가 있고 전처리중이 아니다 |
| **중단?** | 임시폴더는 있는데 `gpt.exe`가 하나도 없고 30분(`--stale-minutes`)이 지났다 |
| **제외** | zip은 있는데 **한반도 겹침이 `--min-overlap`(1%) 미만** — 처리 대상이 아니다 |

### 대기와 제외를 가른다 — 원본 zip의 footprint로

"왜 이건 아직 대기지?"의 답은 둘로 갈린다. **(a) 진짜 밀린 것**과 **(b) 애초에
한반도를 안 찍어 처리할 이유가 없는 것**이다. 둘을 안 가르면 중국·일본·동해
프레임이 영원히 "대기"로 남아 진짜 일감과 섞인다.

카탈로그 조회창(기본 7일) 밖의 씬은 STAC geometry를 다시 받아올 수 없으므로,
**손에 있는 zip 안의 `preview/map-overlay.kml`**을 읽어 겹침을 잰다(검색·다운로드
쪽과 같은 1% 기준 — [PREPROCESSING_SPEC_KR.md](PREPROCESSING_SPEC_KR.md) 4절).
zip을 푸는 게 아니라 KML 한 항목(수 KB)만 꺼내므로 씬당 수십 ms다. 결과는
`downloads/footprint_cache.json`에 남겨 두 번 재지 않는다(한 번에 40개씩).

실측 예(2026-08-18): `B5F3`(2026-08-08)은 겹침 **0.00%** — 남해 위 프레임이라
받아만 두고 처리하지 않는 것이 맞다. 반면 `D635`(2026-08-14)는 **84.91%**로
남한 커버가 가장 넓은 프레임인데 대기였다 — 이건 진짜 밀린 것이었다.

### ⚠ tif가 있다고 완료가 아니다

SNAP `gpt`는 출력 tif를 **처리하는 내내 쓴다.** 2026-08-18 실측에서 처리 중이던
`0868`은 이미 2.32 GB짜리 tif를 갖고 있었고, 갓 시작한 `8E47`은 0 바이트였다.
파일 존재만으로 완료를 세면 **굽는 중인 씬이 완료로 잡힌다.**

그래서 판정 순서가 **임시폴더 > tif**다. 배치 러너([batch_runner.py](../../s1/preprocess/batch_runner.py))가
씬마다 zip을 SSD 임시 하위폴더로 복사해 두고 끝나면 지우므로, 그 폴더가 곧
"지금 굽는 중"이라는 증거다. 접두사는 `frostrtc_`·`rtc_`·`gtc_`·`slcrtc_`·
`snapbatch_`(러너를 부르는 배치들이 정하는 값).

경과시간은 **임시폴더 생성시각**으로 잰다. 복사된 zip의 mtime을 보면 안 된다 —
`shutil.copy2`가 원본 시각을 그대로 물려줘 "20시간 전 시작"처럼 엉뚱하게 찍힌다.

### 씬 대조 키

**(관측 시작시각, 절대궤도)**. STAC id·zip·tif를 이 키로 잇는다. 씬 ID 끝
4hex는 제품 생성 해시라 같은 촬영도 재처리본마다 다르다
([PREPROCESSING_SPEC_KR.md](PREPROCESSING_SPEC_KR.md) 4절, ISSUES #16).

### "대기 65"가 뜻하는 것

**보유 zip 중 현행 정본 폴더(`rtc_grd_frost_vh/`)에 산출물이 없고, 한반도
겹침이 1% 이상인 것**이다. 겹침 미달은 위에서 `제외`로 빠진다.

그래도 "오늘 할 일감"과 같지는 않다 — 2025-07 비교용처럼 **일부러 안 구운 것**도
여기 들어간다. 다른 산출물 계열을 기준으로 보려면 `--out-dir`·`--out-suffix`를
바꾼다.

## 3. 대략적인 위치(충남·전남 …)

footprint 안에 격자점을 뿌려 **어느 시도에 몇 점이 들어가는지** 세고, 육지 표본
중 8% 이상인 시도를 큰 순서로 최대 3개 적는다. 대부분 바다인 프레임이 흔해
전체 표본 대비로 세면 이름이 다 잘려 나가므로 **육지 표본 기준**이다.

겹침%(한반도 교집합)와 시도 판정은 **같은 격자 한 번**으로 처리한다. 따로
돌리면 프레임마다 격자를 두 번 뿌리게 되고, 이 창은 그걸 수십 프레임에 반복한다.

경계 자료(`geojson/sido_simplified.geojson`, 28개):

| 구역 | 원본 |
| --- | --- |
| 남한 17개 시도 | `20260709_flood/ref/korea_emd_boundary.gpkg`(읍면동)을 `sidonm`으로 병합 |
| 북한 11개 도·시 | WFP COD-AB adm1 (`prk_adm_wfp_20190624_shp.zip`), 영문명 → 한글 |

500 m(0.005°)로 단순화하고 5 km²(0.0005°²)보다 작은 섬은 버렸다. "충남쯤"이
목적이라 그 정도면 충분하고, 파일이 326 KB로 떨어져 git에 넣고 매번 통째로
읽어도 부담이 없다. 제주·울릉도는 남는다.

원본이 갱신되면 다시 굽는다(연 1회 이하):

```bash
conda run -n gis_copy python -m s1.tools.monitor.build_sido_geojson
```

**검증**(2026-08-18): 하강궤도 rel134 한 패스가 남→북 순서로
`제주 → 전남·경남·전북 → 경북·충남·충북 → 강원·경기·강원도(북) →
강원도(북)·함경남도·평안남도 → 함경남도·양강도·함경북도 → 함경북도·양강도`로
찍혔다. 궤도 진행 방향과 일치한다.

## 4. 실행

```powershell
# 창 띄우기(콘솔 없음)
powershell -ExecutionPolicy Bypass -File scripts\scene_dashboard.ps1

# 조회 일수·주기·창 크기 지정
powershell -File scripts\scene_dashboard.ps1 -Days 7 -CdseMinutes 30 -Geometry "700x720+40+40"

# 창 없이 콘솔에 한 번만 (터미널·로그용)
powershell -File scripts\scene_dashboard.ps1 -Once
```

파이썬으로 직접:

```bash
python s1/tools/monitor/scene_dashboard.py                 # 창
python s1/tools/monitor/scene_dashboard.py --once --days 8 # 콘솔 한 번
python -m s1.tools.monitor.scene_dashboard                 # 패키지 방식
```

### 로그인하면 자동으로 뜨게

시작프로그램 폴더에 바로가기를 넣는 게 가장 간단하다(작업 스케줄러로 GUI를
띄우면 세션 문제로 안 보일 수 있다).

```powershell
$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$startup\S1 현황.lnk")
$lnk.TargetPath = "powershell.exe"
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
                 "-File `"f:\06_SAR_system\S1\scripts\scene_dashboard.ps1`""
$lnk.WorkingDirectory = "f:\06_SAR_system\S1"
$lnk.Save()
```

닫을 때는 창의 X. 살아 있는지 확인·강제 종료:

```powershell
Get-Process pythonw | Where-Object { $_.MainWindowTitle -like "S1 현황*" }
Get-Process pythonw | Where-Object { $_.MainWindowTitle -like "S1 현황*" } | Stop-Process
```

## 5. 파라미터

| 옵션 (.py / .ps1) | 기본 | 의미 |
| --- | --- | --- |
| `--days` / `-Days` | 7 | CDSE 조회 일수. 4일로는 표가 비는 날이 흔하다 |
| `--cdse-minutes` / `-CdseMinutes` | 15 | STAC 재조회 주기(분) |
| `--local-seconds` | 20 | 로컬 파일 스캔 주기(초) |
| `--out-dir` / `-OutDir` | `downloads/rtc_grd_frost_vh` | 전처리 산출물 폴더(정본) |
| `--out-suffix` | `_rtc_db_vh` | 산출물 접미사 |
| `--min-overlap` | 1.0 | 한반도 겹침 하한(%) — 중국·일본 프레임 제외 |
| `--step` | 0.05 | footprint 표본 격자 간격(도) |
| `--stale-minutes` | 30 | 이 시간을 넘긴 유휴 임시폴더는 `중단?` |
| `--geometry` / `-Geometry` | `700x720` | 창 크기(+위치) |
| `--scene-rows` / `--proc-rows` | 11 / 8 | 표에 보이는 줄 수(더 있으면 스크롤) |
| `--plan-days` | 10 | 촬영 계획을 며칠 앞까지 볼지 |
| `--plan-hours` | 6 | 촬영 계획 재조회 주기(시간). **0이면 계획 표를 끈다** |
| `--font` / `--font-size` | Malgun Gothic / 9 | |
| `--no-topmost` | (켜짐) | 다른 창 위 고정을 끈다 |
| `--once` / `-Once` | 꺼짐 | 창 대신 콘솔에 한 번 출력 |
| `-PythonCmd` (ps1) | 자동 탐색 | `pythonw` → miniconda/anaconda 순 |

STAC 조회는 프레임 수에 비례해 걸린다(2026-08-18 실측: 22프레임 23초, `--step
0.05`). 창이 멈추지 않도록 조회·스캔은 모두 작업 스레드에서 돌고 결과만 큐로
넘어온다. 조회 중에는 상단에 `조회 중…`이 뜬다.

## 6. 한계

1. **카탈로그 등재는 촬영보다 3~6시간 늦다.** 방금 지나간 궤도가 안 보이는 게
   정상이다([SCENE_MONITOR_KR.md](SCENE_MONITOR_KR.md) 5-3).
2. **`--days` 창 밖의 촬영은 '최근 촬영' 표에 없다.** 그 보유분은 '전처리' 표의
   대기·완료 목록과 상단 요약(보유·대기·완료)에서 본다.
3. **다중 모니터에서 `--geometry`의 위치가 무시될 수 있다.** 창을 원하는 곳에
   끌어다 놓고 쓰면 된다(위치를 기억하지 않는다).
4. **시도 경계는 500 m로 단순화**했다. 해안선 바로 앞 프레임에서 표본 몇 점이
   달라질 수 있지만 "충남쯤"이라는 용도에는 영향이 없다.
5. **`중단?`은 추정이다.** `gpt.exe` 없음 + 30분 경과로 판단하므로, 배치가 씬
   사이에서 zip을 복사하는 중이면 잠깐 그렇게 보일 수 있다. 실제로 죽었는지는
   배치 콘솔·`temp/logs/*.log`로 확인한다.
6. **GRD만 본다.** SLC 진행상황은 다루지 않는다(`sentinel1/`).
7. **'촬영 예정'은 계획이지 보장이 아니다.** ESA가 수시로 갱신하고 실제 촬영이
   빠지기도 한다 — 한계는 [ACQUISITION_PLAN_KR.md](ACQUISITION_PLAN_KR.md) 4절.

## 7. 세 도구의 자리

| | [monitor_new_scenes](SCENE_MONITOR_KR.md) | [acquisition_plan](ACQUISITION_PLAN_KR.md) | scene_dashboard |
| --- | --- | --- | --- |
| 시간축 | 방금 올라온 것 | **앞으로 찍을 것** | 지나간 것 + 예정 + 내 진행 |
| 출처 | CDSE STAC | ESA 계획 KML | 위 둘 + 이 PC 파일 |
| 언제 | 작업 스케줄러 1시간 간격 | 필요할 때 / 창이 6시간마다 | 상시 창 |
| 내보내는 것 | 풍선 알림·비프·flag | 콘솔·JSON | 화면 |

셋은 상태를 공유하지 않는다. 대시보드는 `monitor_state.json`을 읽지도 쓰지도
않으므로 창을 띄워 둬도 감시 알림에 영향이 없다. 계획 쪽은 결과 캐시
(`plan_cache.json`)만 주고받는다 — 창이 없을 때 CLI로 갱신해 둬도 창이 그걸
그대로 집어 든다.
