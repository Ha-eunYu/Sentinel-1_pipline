# 신규 Sentinel-1 촬영 자동 감시 (한반도)

새 Sentinel-1 촬영이 Copernicus 카탈로그에 올라오면 알려주는 도구. 비가 오는
동안 최신 SAR 관측이 언제 들어오는지 사람이 STAC를 계속 들여다보지 않아도 되게
한다.

| 구성 | 경로 | 역할 |
| --- | --- | --- |
| 조회 스크립트 | [monitor_new_scenes.py](../../s1/tools/monitor/monitor_new_scenes.py) | STAC 조회 → 신규 판정 → 로그·상태 갱신 |
| PowerShell 래퍼 | [monitor_new_scenes.ps1](../../scripts/monitor_new_scenes.ps1) | 풍선 알림 + 비프 + `NEW_SCENES.flag` |
| 상태 | `downloads/monitor_state.json` | 이미 본 씬 ID 목록 |
| 로그 | `downloads/new_scenes.log` | 발견 이력(UTF-8, append) |
| 플래그 | `downloads/NEW_SCENES.flag` | 마지막 알림 내용(덮어씀) |

> 알림 다음이 궁금하면 — 받았나·굽는 중인가·끝났나 — 상시 현황 창을 띄운다:
> [SCENE_DASHBOARD_KR.md](SCENE_DASHBOARD_KR.md).

- **인증이 필요 없다.** STAC `/v1/search`는 공개 API라 `.env` 없이도 돈다.
- **의존성이 없다.** `urllib`·`json` 등 **표준 라이브러리만** 쓴다. shapely·numpy는
  물론 이 저장소의 다른 모듈(`s1.core.paths` 등)도 import하지 않으므로, 파일
  하나만 있으면 아무 파이썬으로나 돈다(경계 GeoJSON만 있으면 된다).
- 그래서 conda 환경이 없어도, 작업 스케줄러의 빈약한 PATH에서도 실행된다.

---

## 1. 동작 원리

```text
1) STAC 조회       최근 N일(기본 4일), bbox, sentinel-1-grd
2) footprint 필터  한반도 교집합 < --min-overlap(기본 1%) 프레임 제외
3) 신규 판정       monitor_state.json 의 seen_ids 와 차집합
4) 알림            새 씬이 있으면 콘솔·로그·풍선알림·flag
5) 상태 갱신       seen_ids = 기존 ∪ 이번 조회분 (조회창을 벗어난 과거 ID도 유지)
6) 종료코드 대신   마지막 줄에 NEW_SCENES=<n> 출력 → 래퍼가 이 값으로 알림 판단
```

### footprint 필터 — bbox만으로는 중국·일본이 섞인다

Sentinel-1 IW 프레임은 궤도 방위각만큼 기울어진 **평행사변형**이라, 검색 상자에
걸리는 것과 한반도를 찍은 것은 다르다. STAC이 주는 실제 footprint(`geometry`)를
`geojson/Korea_Peninsula.geojson`과 대조해 겹침 비율을 재고 1% 미만은 버린다
(검색·다운로드 쪽과 같은 기준 — [PREPROCESSING_SPEC_KR.md](PREPROCESSING_SPEC_KR.md) 4절).

**shapely 없이 어떻게 재나 — 격자 표본.** 면적 교집합을 정확히 구하려면 폴리곤
클리핑을 구현해야 하는데, 감시에는 그만한 정밀도가 필요 없다. footprint 안에
`--step`(기본 0.04° ≈ 4 km) 간격 격자점을 뿌리고 **그중 몇 %가 경계 안인지**
센다. 경계 폴리곤(링 1,766개·꼭짓점 9,711개)은 1°격자 색인으로 후보 링을 좁혀
바다 위 점은 즉시 탈락시킨다.

shapely 정답과 대조한 결과(2026-08-18, 21씬):

| 격자 간격 | 최대 오차 | 1% 판정 불일치 | 21씬 소요 |
| --- | ---: | ---: | ---: |
| `--step 0.04` (기본) | **0.26 %p** | **0건** | 약 25초 |
| `--step 0.02` | 0.13 %p | 0건 | 약 90초 |

기본값으로 충분하다. 예: `D635` shapely 84.87% ↔ 격자 84.91%,
`8B48` 0.39% ↔ 0.33%(둘 다 1% 미만으로 제외).

**첫 실행은 알리지 않는다.** 현재 카탈로그에 있는 씬을 전부 "이미 본 것"으로
baseline 등록만 한다. 과거 씬으로 도배되는 것을 막기 위해서다. 그 다음 실행부터
진짜 신규만 잡힌다.

`monitor_state.json` 구조:

```json
{
  "seen_ids": ["S1C_IW_GRDH_1SDV_2026...._COG", "..."],
  "initialized": true,
  "last_check": "2026-08-18 00:01:52Z"
}
```

> **상태파일을 지우면 다시 baseline 초기화부터 시작한다.** 알림이 계속 중복으로
> 뜨면 상태파일이 갱신되지 않는(권한·경로) 문제일 가능성이 높다.

## 2. 수동 실행

의존성이 없으므로 **아무 파이썬으로나, 어느 디렉터리에서나** 돈다. 파일 경로로
직접 부르는 것이 가장 간단하다(2026-08-13 재구성으로 `s1/tools/monitor/`에 있다).

```bash
# 단발 확인 (conda 불필요)
python s1/tools/monitor/monitor_new_scenes.py --days 4

# 패키지 방식으로도 된다 (저장소 루트에서)
python -m s1.tools.monitor.monitor_new_scenes --days 4

# SLC 도 감시 — 상태파일을 따로 줄 것(5-6 참고)
python s1/tools/monitor/monitor_new_scenes.py --collection sentinel-1-slc \
    --state downloads/monitor_state_slc.json --log downloads/new_scenes_slc.log

# 상태를 건드리지 않고 시험만 (임시 상태파일로)
python s1/tools/monitor/monitor_new_scenes.py \
    --state temp/mon_test.json --log temp/mon_test.log

# 옛 동작(bbox만, footprint 필터 없음)으로 비교해 보고 싶을 때
python s1/tools/monitor/monitor_new_scenes.py --no-filter
```

래퍼(알림 포함):

```powershell
# 단발
powershell -ExecutionPolicy Bypass -File scripts\monitor_new_scenes.ps1 -Days 4
# 60분 간격 반복(전경, Ctrl+C 종료)
powershell -ExecutionPolicy Bypass -File scripts\monitor_new_scenes.ps1 -IntervalMinutes 60
```

## 3. 윈도우 백그라운드로 돌리기

세 가지. **작업 스케줄러(A)를 권장**한다 — 로그아웃·재부팅 후에도 살아있고
콘솔 창을 띄우지 않는다.

### A. 작업 스케줄러 (권장)

관리자 PowerShell에서 **1시간마다** 단발 체크 등록:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
               "-File `"f:\06_SAR_system\S1\scripts\monitor_new_scenes.ps1`"") `
    -WorkingDirectory "f:\06_SAR_system\S1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "S1_new_scene_monitor" `
    -Action $action -Trigger $trigger -Description "한반도 신규 Sentinel-1 촬영 감시"
```

```powershell
Start-ScheduledTask   -TaskName "S1_new_scene_monitor"   # 즉시 한 번
Get-ScheduledTaskInfo -TaskName "S1_new_scene_monitor"   # 마지막 실행 결과
Unregister-ScheduledTask -TaskName "S1_new_scene_monitor" -Confirm:$false
```

> **알림이 안 보일 수 있다.** 세션 0(로그인 없이)에서 실행되면 데스크톱 풍선이
> 뜨지 않는다. "사용자가 로그온했을 때만 실행"을 켜거나, 알림 대신
> `downloads/new_scenes.log`·`NEW_SCENES.flag`를 확인한다.

### B. 숨김 프로세스로 상주

```powershell
Start-Process powershell -WindowStyle Hidden -ArgumentList `
    "-NoProfile -ExecutionPolicy Bypass -File `"f:\06_SAR_system\S1\scripts\monitor_new_scenes.ps1`" -IntervalMinutes 60"
```

중지:

```powershell
Get-CimInstance Win32_Process -Filter "name='powershell.exe'" |
    Where-Object { $_.CommandLine -match 'monitor_new_scenes' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### C. PowerShell 잡 (현재 세션 한정)

```powershell
Start-Job -Name s1mon -ScriptBlock {
    powershell -ExecutionPolicy Bypass -File "f:\06_SAR_system\S1\scripts\monitor_new_scenes.ps1" -IntervalMinutes 60
}
Receive-Job -Name s1mon -Keep
Stop-Job -Name s1mon; Remove-Job -Name s1mon
```

세션을 닫으면 사라진다. 지속 감시는 A 또는 B.

## 4. 파라미터

| 옵션 (.py / .ps1) | 기본 | 의미 |
| --- | --- | --- |
| `--days` / `-Days` | 4 | 조회할 최근 일수 |
| `--collection` / `-Collection` | `sentinel-1-grd` | `sentinel-1-slc` 가능 |
| `--bbox` (py) | `123.5 32 131.5 43.5` | lon_min lat_min lon_max lat_max. **북한 최북단 43.0°N 포함** |
| `--boundary` (py) | `geojson/Korea_Peninsula.geojson` | 겹침 판정 경계. 파일이 없으면 필터를 끄고 진행 |
| `--min-overlap` (py) | 1.0 | 한반도 교집합 하한(%). 미만이면 제외 |
| `--step` (py) | 0.04 | 겹침 표본 격자 간격(도). 작을수록 정밀·느림 |
| `--no-filter` (py) | 꺼짐 | footprint 필터를 끄고 bbox 결과를 그대로(옛 동작) |
| `--state` / `--log` (py) | `downloads/` | 상태·로그 경로 |
| `--quiet` (py) | 꺼짐 | 신규 없을 때 조용히(래퍼가 사용) |
| `-IntervalMinutes` (ps1) | 0 | 0=단발, >0=그 간격(분) 반복 |
| `-PythonCmd` (ps1) | (자동 탐색) | `python` → `py` → miniconda/anaconda → `conda run` 순으로 찾는다 |

**조회 주기는 `--days`보다 짧게.** 기본 4일이면 하루 몇 번만 돌려도 놓치지
않는다. 반대로 며칠 쉬었다 돌리면 `--days`를 늘려야 그 사이 관측이 잡힌다.

---

## 5. ⚠ 한계 — 알고 쓰지 않으면 틀린 알림을 받는다

### 5-1. ✅ 중국·일본 오탐 — 해결됨 (2026-08-18)

예전에는 **bbox 사각형만 쓰고 footprint 교차를 보지 않아** 규슈·산둥 프레임이
"신규 한반도 촬영"으로 알림이 떴다. 그날 실행에서 **알림 3건이 전부 오탐**이었다.

| 씬 | bounds | 한반도 교집합 | 실제 위치 |
| --- | --- | ---: | --- |
| `D753` (08-17) | 120.9~124.1E, 36.1~38.2N | **0.00%** | 중국 산둥·서해 |
| `BC85` (08-15) | 129.7~132.9E, 33.2~35.8N | **0.00%** | 일본 규슈 |
| `97D9` (08-15) | 130.2~133.2E, 31.7~33.6N | **0.00%** | 일본 규슈 남부 |

이제 footprint 겹침 1% 필터가 들어가 셋 다 걸러진다. 제외된 프레임은 실행
로그에 `[footprint 제외] ...(0.0%)` 로 남으므로, 필터가 과하게 자르는지도
눈으로 확인할 수 있다.

### 5-2. ✅ 북한 북부 누락 — 해결됨 (2026-08-18)

기본 bbox 북쪽 한계가 **40.0°N**이라 북한 북부(40~43°N)를 통째로 놓치고 있었다.
한반도 전체가 대상이 되면서 **`123.5 32.0 131.5 43.5`로 넓혔다.** 넓힌 만큼
들어오는 중국 동북부·러시아 연해주 프레임은 5-1의 footprint 필터가 걷어낸다.

### 5-3. 카탈로그 등재 지연 3~6시간

촬영 직후에는 안 잡힌다. 2026-07-13 21:40Z 촬영이 약 4시간 뒤에 등재됐다.
**"안 뜬다 = 촬영 안 됐다"가 아니다.** 촬영 계획 자체를 보려면 ESA 계획 KML을
확인한다(README "촬영 계획 확인법").

### 5-4. 시각은 전부 UTC — 하강궤도는 KST로 날짜가 하루 넘어간다

로그의 `2026-08-13T21:31Z`는 **KST 8/14 06:31**이다. 환산표는
[ORBIT_CALENDAR_202607_08_KR.md](ORBIT_CALENDAR_202607_08_KR.md) 1-1절.

### 5-5. 콘솔 한글이 깨진다 (로그는 멀쩡하다)

PowerShell 5.1 콘솔 코드페이지 문제라 `신규 → �떊洹`처럼 보인다. **파일
(`new_scenes.log`)은 UTF-8로 정상**이므로 로그를 보면 된다(ISSUES #11).

### 5-6. GRD/SLC를 따로 감시해야 한다

`--collection`이 한 번에 하나다. 둘 다 보려면 **상태파일도 따로** 준다.

```bash
python -m s1.tools.monitor.monitor_new_scenes --collection sentinel-1-slc \
    --state downloads/monitor_state_slc.json --log downloads/new_scenes_slc.log
```

같은 상태파일을 공유하면 서로의 ID를 "이미 본 것"으로 덮어써 알림을 놓친다.

---

## 6. 새 씬이 잡히면

`new_scenes.log`에 씬 ID와 관측시각(UTC)이 남는다.

```text
[2026-08-18 00:01:52Z] 신규 sentinel-1-grd 3개 발견:
  + S1D_IW_GRDH_1SDV_20260817T094741_..._D753_COG  (2026-08-17T09:47:41Z)
```

이어지는 절차:

1. **한반도를 실제로 찍었는지 확인**(5-1 때문에 필수) — 다운로드 도구가
   footprint로 다시 거르므로 그냥 아래를 돌리면 된다.
2. 수집: `python -m s1.tools.download.download_korea_missing 202608`
3. 전처리: [PREPROCESSING_SPEC_KR.md](PREPROCESSING_SPEC_KR.md)의 확정 파라미터로
   `batch_grd_rtc_frost --dem downloads/dem_basin/korea_peninsula_cop30.tif`

## 7. 현재 상태 (2026-08-18)

| 항목 | 상태 |
| --- | --- |
| 래퍼 경로 버그 | ✅ 수정 — 재구성 이후 저장소 루트의 없는 파일을 부르고 있었다 |
| 중국·일본 오탐 | ✅ 해결 — footprint 겹침 1% 필터 |
| 북한 북부 누락 | ✅ 해결 — bbox 43.5°N 까지 |
| 의존성 | ✅ 표준 라이브러리만 — `s1.core.paths`·shapely·numpy 모두 제거 |
| 인터프리터 | ✅ 자동 탐색 — conda 없이도 실행 |
| 알림 내용 | ✅ UTC·KST·상대궤도·한반도 겹침% 표시 |
| **작업 스케줄러 등록** | ✅ **완료(2026-08-18)** — `S1_new_scene_monitor`, 1시간 간격. 마지막 실행 결과 0 |

### 2026-08-18에 고친 것

- **래퍼가 없는 파일을 부르고 있었다.** 2026-08-13 패키지 재구성으로 스크립트가
  `s1/tools/monitor/`로 옮겨졌는데 `.ps1`은 저장소 루트를 가리키고 있었다.
  **그 사이 감시는 한 번도 동작하지 않았다**(상태파일이 2026-07-22 이후 갱신 없음).
- **의존성을 없앴다.** 원래 설계 의도가 "표준 라이브러리만"이었는데
  `s1.core.paths`를 import하고 있어 이미 깨져 있었다. 파일 위치로 저장소 루트를
  찾도록 바꿔 되살렸고, footprint 판정도 shapely 대신 **순수 파이썬
  ray-casting + 1°격자 색인**으로 넣었다. shapely 정답 대비 오차 0.26 %p,
  1% 판정 불일치 0건(21씬).
- `--min-overlap` · `--step` · `--boundary` · `--no-filter` 옵션 신설.
- 인터프리터 자동 탐색(`python` → `py` → miniconda/anaconda → `conda run`).
  작업 스케줄러 세션에는 PATH가 빈약해 `python`이 없을 수 있다.

### 다음

- **상시 현황 창** — 감시는 "새 게 올라왔다"를 알림 한 번으로 알려 줄 뿐이라,
  그 뒤 다운로드·전처리가 어디까지 갔는지는 알 수 없다. 그 자리를
  [SCENE_DASHBOARD_KR.md](SCENE_DASHBOARD_KR.md)의 현황 창이 채운다
  (CDSE 최신 촬영 + 위치·궤도 + 이 PC의 다운로드/대기/처리중/완료).
