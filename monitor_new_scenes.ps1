# 한반도 신규 Sentinel-1 촬영 감시 래퍼 (monitor_new_scenes.py 구동)
#
# 사용 예)
#   단발 실행(Task Scheduler용):  powershell -ExecutionPolicy Bypass -File monitor_new_scenes.ps1
#   반복 실행(전경, Ctrl+C 종료):  powershell -ExecutionPolicy Bypass -File monitor_new_scenes.ps1 -IntervalMinutes 60
#   SLC도 감시:                    ... -Collection sentinel-1-slc
#
# 새 씬이 발견되면 (1) 콘솔 출력 (2) 윈도우 풍선 알림 + 비프 (3) downloads\NEW_SCENES.flag 기록.
# 백그라운드 등록 방법은 SCENE_MONITOR_KR.md 참고.

param(
    [int]$IntervalMinutes = 0,          # 0 = 한 번만. >0 이면 그 간격(분)으로 무한 반복.
    [int]$Days = 4,
    [string]$Collection = "sentinel-1-grd",
    [string]$PythonCmd = "conda run -n s1_snappy python"
)

$ErrorActionPreference = "Continue"
$ProjectDir = "f:\06_SAR_system\S1"
$ScriptPy = Join-Path $ProjectDir "monitor_new_scenes.py"
$FlagFile = Join-Path $ProjectDir "downloads\NEW_SCENES.flag"

Add-Type -AssemblyName System.Windows.Forms | Out-Null
Add-Type -AssemblyName System.Drawing | Out-Null

function Show-Toast($title, $text) {
    try {
        $ni = New-Object System.Windows.Forms.NotifyIcon
        $ni.Icon = [System.Drawing.SystemIcons]::Information
        $ni.Visible = $true
        $ni.ShowBalloonTip(15000, $title, $text, [System.Windows.Forms.ToolTipIcon]::Info)
        [console]::beep(880, 400)
        Start-Sleep -Seconds 2
        $ni.Dispose()
    } catch { Write-Host "알림 표시 실패(무시): $_" }
}

function Invoke-Check {
    # $PythonCmd 를 토큰으로 나눠 호출(예: "conda run -n s1_snappy python")
    $parts = $PythonCmd.Split(" ")
    $exe = $parts[0]
    $preArgs = @()
    if ($parts.Count -gt 1) { $preArgs = $parts[1..($parts.Count - 1)] }

    $out = & $exe @preArgs $ScriptPy "--days" $Days "--collection" $Collection "--quiet" 2>&1
    $out | ForEach-Object { Write-Host $_ }

    $match = $out | Select-String -Pattern "NEW_SCENES=(-?\d+)" | Select-Object -Last 1
    $n = 0
    if ($match) { $n = [int]$match.Matches[0].Groups[1].Value }

    if ($n -gt 0) {
        $body = ($out | Where-Object { $_ -match "^\s*\+ " }) -join "`n"
        if (-not $body) { $body = "새 씬 $n 건 (자세한 내용은 new_scenes.log)" }
        Show-Toast "새 Sentinel-1 촬영 $n 건" $body
        Set-Content -Path $FlagFile -Value $body -Encoding utf8
    }
}

if ($IntervalMinutes -le 0) {
    Invoke-Check
} else {
    Write-Host "감시 시작: $IntervalMinutes 분 간격, $Collection (Ctrl+C 로 종료)"
    while ($true) {
        Invoke-Check
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}
