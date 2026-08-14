<#
.SYNOPSIS
  docs/worklog/ISSUES_KR.md 의 미해결 이슈를 GitHub 이슈로 등록한다.

.DESCRIPTION
  본문은 temp/issues/*.md 에 미리 써 둔 것을 쓴다. 이미 같은 제목의 이슈가
  있으면 건너뛴다(중복 등록 방지).

  ⚠ 한글 인코딩 규약 (ISSUES_KR #11)
  1. 이 파일은 **UTF-8 with BOM**으로 저장한다. BOM이 없으면 Windows
     PowerShell 5.1이 시스템 ANSI(CP949)로 읽어 한글이 깨지고 파서가 죽는다.
  2. **한글을 네이티브 명령의 인자로 넘기지 않는다.** PS 5.1은 네이티브 인자를
     콘솔 코드페이지로 인코딩해 넘기므로 gh 로 가는 도중 한글이 깨진다.
     그래서 제목·본문·라벨을 **UTF-8 JSON 파일**로 쓰고
     `gh api --input <파일>` 로 넘긴다. 인자에는 ASCII만 남는다.
  3. 콘솔 입출력도 UTF-8로 맞춰 gh 응답(한글 제목)이 깨지지 않게 한다.

  전제: GitHub CLI 설치 + 인증
      winget install --id GitHub.cli
      gh auth login
      # 또는 저장소 1개짜리 fine-grained PAT (Issues: Read and write):
      #   $env:GH_TOKEN = "github_pat_..."

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/create_issues.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File scripts/create_issues.ps1
#>
param(
    [switch]$DryRun,
    [string]$Repo = "Ha-eunYu/Sentinel-1_pipline"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# --- 인코딩 고정 (위 규약 3) -------------------------------------------------
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch { Write-Warning "콘솔 인코딩을 UTF-8로 바꾸지 못했습니다: $_" }

# (본문 파일, 제목, 라벨들)
$issues = @(
    @{ file = "01_snap_vrt_dem.md"
       title = "SNAP external DEM에 VRT를 주면 No product reader found"
       labels = @("snap") },
    @{ file = "02_snap_cop30_estuary_void.md"
       title = "SNAP 자동 캐시 COP30이 하구 수역을 결측 처리 (영산강 20.2% 손실)"
       labels = @("snap", "data-quality") },
    @{ file = "04_powershell_stderr.md"
       title = "PowerShell이 gpt의 stderr를 오류로 감싸 성공한 실행이 실패로 보임"
       labels = @("tooling") },
    @{ file = "06_gdal_data_warning.md"
       title = "GDAL_DATA 미설정 경고가 로그를 오염시킴"
       labels = @("tooling") },
    @{ file = "07_south_korea_polygon.md"
       title = "South_Korea.geojson이 부산·강릉·여수·해남·완도·제주를 제외 — 궤도 선별 재검증 필요"
       labels = @("data-quality") },
    @{ file = "08_common_footprint_mask.md"
       title = "연도 간 관측 범위 차이 — 공통 footprint 마스크 없이는 면적 비교 불가"
       labels = @("analysis", "blocked") },
    @{ file = "09_wet_soil_overestimation.md"
       title = "26년 7/14 두 궤도가 젖은 토양으로 과대추정 (+39% / +17%)"
       labels = @("analysis", "data-quality") },
    @{ file = "11_powershell_korean_encoding.md"
       title = "PowerShell 한글 인코딩 — .ps1 BOM과 네이티브 인자 코드페이지"
       labels = @("tooling") },
    @{ file = "12_relative_orbit_offset.md"
       title = "절대궤도 175배수 산술로 상대궤도를 판단해 25/26년 짝을 잘못 지음 (S1C 오프셋 변경)"
       labels = @("data-quality", "analysis") }
)

# gh 찾기. 설치 직후 열려 있던 셸은 PATH가 갱신되지 않아 Get-Command 로는 못
# 찾는다. 표준 설치 경로도 함께 뒤진다.
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    $gh = @(
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $gh) {
    throw "GitHub CLI(gh)가 없습니다. 'winget install --id GitHub.cli' 후 'gh auth login'."
}

# --- 중복 방지 -------------------------------------------------------------
# 1차: 본문 파일 -> 이슈 번호 매핑(data/github_issues.json). 제목을 고쳐도
#      같은 이슈로 인식한다. 실제로 제목만 다듬었다가 #6/#8 중복을 만든 적이 있다.
# 2차: 그래도 없으면 제목 일치로 한 번 더 거른다.
$mapPath = Join-Path $root "data/github_issues.json"
$map = @{}
if (Test-Path $mapPath) {
    $obj = Get-Content $mapPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $obj.PSObject.Properties) {
        if ($p.Name -notlike "_*") { $map[$p.Name] = $p.Value }
    }
}

$existing = @()
try {
    $json = & $gh api "repos/$Repo/issues?state=all&per_page=100" 2>$null | Out-String
    if ($json) { $existing = ($json | ConvertFrom-Json).title }
} catch { Write-Warning "기존 이슈 목록을 못 읽었습니다(제목 검사 생략): $_" }

$payloadDir = Join-Path $root "temp/issue_payloads"
if (-not (Test-Path $payloadDir)) { New-Item -ItemType Directory -Path $payloadDir | Out-Null }

foreach ($i in $issues) {
    $bodyPath = Join-Path $root "temp/issues/$($i.file)"
    if (-not (Test-Path $bodyPath)) { Write-Warning "본문 없음: $bodyPath"; continue }
    if ($map.ContainsKey($i.file)) {
        "건너뜀(#$($map[$i.file]) 로 등록됨): $($i.file)"
        continue
    }
    if ($existing -contains $i.title) { "건너뜀(같은 제목 존재): $($i.title)"; continue }

    # 제목·본문·라벨을 UTF-8 JSON으로 (위 규약 2 — 한글이 인자로 가지 않는다)
    $payload = @{
        title  = $i.title
        body   = [System.IO.File]::ReadAllText($bodyPath, [System.Text.Encoding]::UTF8)
        labels = $i.labels
    } | ConvertTo-Json -Depth 5
    $payloadPath = Join-Path $payloadDir ($i.file -replace '\.md$', '.json')
    # BOM 없는 UTF-8 — JSON에 BOM이 붙으면 서버가 파싱에 실패한다.
    [System.IO.File]::WriteAllText($payloadPath, $payload,
        (New-Object System.Text.UTF8Encoding($false)))

    if ($DryRun) {
        "[dry-run] $($i.title)  [$($i.labels -join ', ')]  <- temp/issues/$($i.file)"
        continue
    }
    $res = & $gh api --method POST "repos/$Repo/issues" --input $payloadPath | Out-String
    $num = ($res | ConvertFrom-Json).number
    "등록 #$num  $($i.title)"

    # 매핑을 즉시 저장한다(중간에 끊겨도 다음 실행이 중복을 만들지 않게).
    $map[$i.file] = $num
    $out = [ordered]@{
        "_comment" = "본문 파일 -> GitHub 이슈 번호 매핑. create_issues.ps1 이 읽고 쓴다."
        "_repo"    = $Repo
    }
    foreach ($k in ($map.Keys | Sort-Object)) { $out[$k] = $map[$k] }
    [System.IO.File]::WriteAllText($mapPath, ($out | ConvertTo-Json -Depth 3),
        (New-Object System.Text.UTF8Encoding($false)))
}
