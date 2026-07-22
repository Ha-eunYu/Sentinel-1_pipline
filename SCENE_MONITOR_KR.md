# 신규 Sentinel-1 촬영 자동 감시 (한반도)

새 Sentinel-1 촬영이 Copernicus 카탈로그에 올라오면 자동으로 알려주는 도구.
비가 계속 오는 상황에서 최신 SAR 관측이 언제 들어오는지 사람이 계속 STAC를
들여다보지 않아도 되게 한다.

- 조회 스크립트: [monitor_new_scenes.py](monitor_new_scenes.py) — 인증 불필요,
  표준 라이브러리만 사용(STAC `/v1/search` 공개 API).
- 래퍼: [monitor_new_scenes.ps1](monitor_new_scenes.ps1) — 새 씬 발견 시
  **윈도우 풍선 알림 + 비프 + `downloads\NEW_SCENES.flag` 기록**.
- 로그: `downloads/new_scenes.log`, 상태: `downloads/monitor_state.json`.

## 1. 동작 방식

1. 최근 N일(기본 4일) 범위로 한반도 bbox(124–131°E, 32–40°N)의
   `sentinel-1-grd` 씬을 STAC에서 조회.
2. 상태파일(`monitor_state.json`)의 "이미 본 씬 ID"와 비교해 **새 씬만** 추림.
3. 새 씬이 있으면 콘솔·로그·알림. 없으면 조용히 넘어감.
4. **첫 실행은 현재 카탈로그를 baseline으로만 등록하고 알리지 않는다**(과거
   씬으로 도배 방지). 이후부터 진짜 신규만 알린다.

이미 baseline 등록을 마쳤다(2026-07-22 기준 최근 4일 12개 씬 등록). 즉 지금부터
새로 올라오는 7/21·7/22 이후 관측이 잡히면 알림이 뜬다.

## 2. 수동 실행

```powershell
# 단발 확인
conda run -n s1_snappy python monitor_new_scenes.py --days 4

# SLC까지 보고 싶으면
conda run -n s1_snappy python monitor_new_scenes.py --collection sentinel-1-slc

# 래퍼로 실행(알림 포함), 60분 간격 반복(전경, Ctrl+C 종료)
powershell -ExecutionPolicy Bypass -File monitor_new_scenes.ps1 -IntervalMinutes 60
```

## 3. 윈도우 백그라운드로 돌리기

세 가지 방법. **작업 스케줄러(방법 A)를 권장**한다 — 로그아웃/재부팅 후에도
살아있고, 콘솔 창을 띄우지 않는다.

### A. 작업 스케줄러 (권장, 주기 실행)

관리자 PowerShell에서 아래를 실행하면 **1시간마다** 단발 체크가 등록된다:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"f:\06_SAR_system\S1\monitor_new_scenes.ps1`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "S1_new_scene_monitor" `
    -Action $action -Trigger $trigger -Description "한반도 신규 Sentinel-1 촬영 감시"
```

관리·삭제:

```powershell
Start-ScheduledTask -TaskName "S1_new_scene_monitor"     # 즉시 한 번 실행
Get-ScheduledTaskInfo -TaskName "S1_new_scene_monitor"    # 마지막 실행 결과
Unregister-ScheduledTask -TaskName "S1_new_scene_monitor" -Confirm:$false  # 제거
```

> 참고: 로그인 세션이 없을 때도 풍선 알림을 확실히 받으려면 알림보다
> `downloads\new_scenes.log`·`NEW_SCENES.flag`를 확인하는 편이 안전하다
> (세션 0에서 실행되면 데스크톱 풍선이 안 보일 수 있음). 작업 스케줄러의
> "사용자가 로그온했을 때만 실행" 옵션을 켜면 알림도 보인다.

### B. 숨김 프로세스로 상주 (반복 루프)

콘솔 창 없이 백그라운드에서 60분 간격 루프를 상주시킨다:

```powershell
Start-Process powershell -WindowStyle Hidden -ArgumentList `
    "-NoProfile -ExecutionPolicy Bypass -File `"f:\06_SAR_system\S1\monitor_new_scenes.ps1`" -IntervalMinutes 60"
```

중지(해당 프로세스 종료):

```powershell
Get-CimInstance Win32_Process -Filter "name='powershell.exe'" |
    Where-Object { $_.CommandLine -match 'monitor_new_scenes' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### C. PowerShell 백그라운드 잡 (현재 세션 한정)

```powershell
Start-Job -Name s1mon -ScriptBlock {
    powershell -ExecutionPolicy Bypass -File "f:\06_SAR_system\S1\monitor_new_scenes.ps1" -IntervalMinutes 60
}
Receive-Job -Name s1mon -Keep    # 출력 확인
Stop-Job -Name s1mon; Remove-Job -Name s1mon
```

세션을 닫으면 잡도 사라지므로 임시 확인용. 지속 감시는 A 또는 B.

## 4. 새 씬이 잡히면

`new_scenes.log`에 씬 ID·관측시각(UTC)이 남는다. 예:

```text
[2026-07-23 06:40:00Z] 신규 sentinel-1-grd 2개 발견:
  + S1C_..._008xxx_..._COG  (2026-07-22T21:30:00Z)
```

이후 다운로드·RTC 처리는 기존 파이프라인으로 이어가면 된다
([README_KR.md](README_KR.md), [GTC_RTC_PROCESSING_LOG_KR.md](GTC_RTC_PROCESSING_LOG_KR.md)).

## 5. 파라미터

| 옵션(.py / .ps1) | 기본 | 의미 |
| --- | --- | --- |
| `--days` / `-Days` | 4 | 조회할 최근 일수 |
| `--collection` / `-Collection` | sentinel-1-grd | `sentinel-1-slc`로 변경 가능 |
| `--bbox` (py) | 124 32 131 40 | 한반도 lon/lat 범위 |
| `-IntervalMinutes` (ps1) | 0 | 0=단발, >0=그 간격(분) 반복 |
| `--state` / `--log` (py) | downloads/ | 상태·로그 파일 경로 |
