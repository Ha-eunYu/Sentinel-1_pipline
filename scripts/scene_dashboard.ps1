# 한반도 Sentinel-1 파이프라인 현황 창 (scene_dashboard.py 구동)
#
# 사용 예)
#   그냥 띄우기:            powershell -ExecutionPolicy Bypass -File scene_dashboard.ps1
#   창 위치·크기 지정:      ... -Geometry "600x760+40+40"
#   콘솔에 한 번만 찍기:    ... -Once
#   조회 일수·주기 조정:    ... -Days 7 -CdseMinutes 30
#
# 창은 pythonw.exe 로 띄워 **검은 콘솔이 같이 뜨지 않게** 한다. 대시보드는
# 표준 라이브러리만 쓰므로 conda 환경이 없어도 된다(SCENE_DASHBOARD_KR.md).
#
# ⚠ 이 파일은 UTF-8 with BOM 으로 저장할 것 (ISSUES_KR #11).

param(
    [switch]$Once,                      # 창 대신 콘솔 출력 한 번
    [int]$Days = 7,                     # CDSE 조회 일수
    [int]$CdseMinutes = 15,             # CDSE 조회 주기(분)
    [string]$Geometry = "640x760",      # 창 크기(+위치)
    [string]$OutDir = "",               # 전처리 산출물 폴더(기본: 현행 정본 VH)
    [string]$PythonCmd = ""             # 비우면 아래에서 자동 탐색
)

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$ScriptPy = Join-Path $ProjectDir "s1\tools\monitor\scene_dashboard.py"

# 창을 띄울 때는 pythonw(콘솔 없음), --once 일 때는 python(출력이 보여야 한다).
# 작업 스케줄러·시작프로그램 세션은 PATH 가 빈약해 python 이 없을 수 있으므로
# monitor_new_scenes.ps1 과 같은 순서로 찾아 본다.
function Resolve-Python([string]$exe) {
    if (Get-Command $exe -ErrorAction SilentlyContinue) { return $exe }
    foreach ($c in @("$env:USERPROFILE\miniconda3\$exe.exe",
                     "$env:USERPROFILE\anaconda3\$exe.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python312\$exe.exe")) {
        if (Test-Path $c) { return $c }
    }
    return ""
}

if (-not $PythonCmd) {
    $want = if ($Once) { "python" } else { "pythonw" }
    $PythonCmd = Resolve-Python $want
    # pythonw 가 없으면 python 으로 떨어진다(콘솔 창이 하나 같이 뜬다).
    if (-not $PythonCmd) { $PythonCmd = Resolve-Python "python" }
    if (-not $PythonCmd) {
        Write-Host "파이썬을 찾지 못했습니다. -PythonCmd 로 경로를 직접 주세요."
        exit 1
    }
}

$argsList = @($ScriptPy, "--days", $Days, "--cdse-minutes", $CdseMinutes,
              "--geometry", $Geometry)
if ($OutDir) { $argsList += @("--out-dir", $OutDir) }
if ($Once)   { $argsList += "--once" }

if ($Once) {
    # 콘솔 한글이 깨지지 않게(ISSUES_KR #11). 파이썬 쪽도 stdout 을 UTF-8 로 연다.
    $env:PYTHONIOENCODING = "utf-8"
    chcp 65001 > $null
    & $PythonCmd @argsList
} else {
    Start-Process -FilePath $PythonCmd -ArgumentList $argsList `
        -WorkingDirectory $ProjectDir -WindowStyle Hidden
    Write-Host "현황 창을 띄웠습니다: $PythonCmd $($argsList -join ' ')"
}
