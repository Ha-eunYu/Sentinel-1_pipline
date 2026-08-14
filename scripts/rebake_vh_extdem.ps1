<#
.SYNOPSIS
  이미 만들어진 VH RTC 산출물을 external DEM 기준으로 다시 굽는다.

.DESCRIPTION
  7·8월 VH 산출물 상당수가 SNAP 자동 캐시 COP30(또는 유역 clip DEM)으로
  처리돼 있다. 자동 DEM은 하구 수역을 결측으로 만들고(ISSUES_KR #2), 유역
  clip DEM은 범위가 좁아 제주·남해안이 빠진다. 남한 전역을 한 기준으로
  비교하려면 `korea_full_cop30.tif` 하나로 통일해야 한다.

  배치 러너는 **산출물이 있으면 건너뛴다**. 그래서 다시 구우려면 기존 파일을
  먼저 지워야 한다. 이 스크립트가 그 삭제와 재실행을 한 번에 한다.

  ⚠ 이 파일은 UTF-8 with BOM으로 저장할 것 (ISSUES_KR #11).

.PARAMETER Month
  대상 촬영월 접두사. 예: 202507, 202607

.PARAMETER Scenes
  쉼표로 구분한 씬 ID(4자리). 예: "6D9F,38C3"

.PARAMETER WaitFor
  이 PID들이 끝난 뒤에 시작한다(현재 도는 배치와 겹치지 않게).

.EXAMPLE
  # 지울 목록만 확인
  powershell -File scripts/rebake_vh_extdem.ps1 -Month 202507 -Scenes "6D9F,38C3" -DryRun

  # 지금 도는 배치(PID 7312, 8216)가 끝나면 이어서 재처리
  powershell -File scripts/rebake_vh_extdem.ps1 -Month 202607 `
      -Scenes "2DA8,AC28,C278" -WaitFor 7312,8216
#>
param(
    [Parameter(Mandatory = $true)][string]$Month,
    [Parameter(Mandatory = $true)][string]$Scenes,
    # 쉼표 구분 문자열로 받는다. powershell -File 로 부르면 인자가 전부 문자열로
    # 넘어와 [int[]] 로는 "1,2,3" 변환이 실패한다.
    [string]$WaitFor = "",
    [string]$Dem = "downloads/dem_basin/korea_full_cop30.tif",
    [string]$OutDir = "downloads/rtc_grd_frost_vh",
    [string]$GptCache = "7G",
    [string]$CondaEnv = "s1_snappy",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch { }

# 1) 앞선 배치가 끝날 때까지 대기 (gpt 는 RAM 을 많이 써 동시 실행이 위험)
$waitIds = @()
if ($WaitFor) {
    $waitIds = $WaitFor.Split(",") | ForEach-Object { $_.Trim() } |
               Where-Object { $_ } | ForEach-Object { [int]$_ }
}
# Wait-Process 의 -Timeout 은 최대 32767초(약 9시간)라 하루를 넘기는 배치에
# 못 쓴다. 60초 간격 폴링으로 기다린다.
foreach ($procId in $waitIds) {
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        "PID $procId 종료 대기... $(Get-Date -Format 'MM-dd HH:mm')"
        while (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            Start-Sleep -Seconds 60
        }
        "PID $procId 종료 확인 $(Get-Date -Format 'MM-dd HH:mm')"
    }
}

# 2) 기존 산출물 삭제 (배치가 '이미 처리됨'으로 건너뛰지 않도록)
$ids = $Scenes.Split(",") | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ }
$targets = @()
foreach ($sceneId in $ids) {
    # 씬 ID 뒤에 밑줄을 강제하지 않는다. 입력이 `..._6D9F.SAFE.zip` 이면 산출물이
    # `..._6D9F.SAFE_rtc_db_vh.tif` 라서 `_6D9F_` 패턴에 걸리지 않는다. 그러면
    # 삭제가 빠지고 배치가 "이미 처리됨"으로 건너뛴다(2026-08-14 실제 사고).
    $targets += Get-ChildItem (Join-Path $root $OutDir) -Filter "*_${Month}*_${sceneId}*_vh.tif" -ErrorAction SilentlyContinue
}
$targets = $targets | Sort-Object FullName -Unique
"삭제 대상 $($targets.Count)개 (씬 $($ids.Count)개 요청)"
foreach ($t in $targets) { "  - $($t.Name)  $([math]::Round($t.Length/1GB,2)) GB" }

$missing = $ids | Where-Object { $sid = $_; -not ($targets | Where-Object { $_.Name -match "_$sid" }) }
if ($missing) { "기존 산출물 없음(신규 처리됨): $($missing -join ', ')" }

if ($DryRun) { "[dry-run] 삭제·재처리는 하지 않는다."; return }

foreach ($t in $targets) { Remove-Item $t.FullName -Force }

# 3) 재처리
"재처리 시작 $(Get-Date -Format 'MM-dd HH:mm')  월=$Month  씬=$($ids -join ',')"
& conda run -n $CondaEnv python -m s1.tools.preprocess.batch_grd_rtc_frost `
    --month $Month --pol VH --out-dir $OutDir --out-tag _vh `
    --dem $Dem --gpt-c $GptCache --oldest-first --only ($ids -join ",")
