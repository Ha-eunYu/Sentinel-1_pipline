<#
.SYNOPSIS
  docs/worklog/ISSUES_KR.md 의 미해결 이슈를 GitHub 이슈로 등록한다.

.DESCRIPTION
  본문은 temp/issues/*.md 에 미리 써 둔 것을 쓴다. 라벨이 없으면 만든 뒤
  붙인다. 이미 같은 제목의 열린 이슈가 있으면 건너뛴다(중복 등록 방지).

  전제: GitHub CLI 설치 + 인증
      winget install --id GitHub.cli
      gh auth login          # 저장소 접근 권한 필요 (private repo)

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

# 라벨: 없으면 만든다. (색은 GitHub 기본 팔레트에서 임의 선택)
$labels = @{
    "snap"        = @{ color = "1d76db"; desc = "SNAP/gpt 전처리 관련" }
    "data-quality"= @{ color = "d93f0b"; desc = "입력 자료·경계·판정 품질" }
    "analysis"    = @{ color = "0e8a16"; desc = "수체·가뭄 분석 방법론" }
    "tooling"     = @{ color = "fbca04"; desc = "실행 환경·자동화" }
    "blocked"     = @{ color = "b60205"; desc = "선행 작업이 끝나야 진행 가능" }
}

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
       title = "연도 간 관측 범위 2배 차이 — 공통 footprint 마스크 없이는 면적 비교 불가"
       labels = @("analysis", "blocked") },
    @{ file = "09_wet_soil_overestimation.md"
       title = "26년 7/14 두 궤도가 젖은 토양으로 과대추정 (+39% / +17%)"
       labels = @("analysis", "data-quality") }
)

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI(gh)가 없습니다. 'winget install --id GitHub.cli' 후 'gh auth login'."
}

if (-not $DryRun) {
    foreach ($name in $labels.Keys) {
        $l = $labels[$name]
        gh label create $name --repo $Repo --color $l.color --description $l.desc 2>$null
    }
}

$existing = @()
try {
    $existing = (gh issue list --repo $Repo --state all --limit 200 --json title |
                 ConvertFrom-Json).title
} catch { }

foreach ($i in $issues) {
    $body = Join-Path $root "temp/issues/$($i.file)"
    if (-not (Test-Path $body)) { Write-Warning "본문 없음: $body"; continue }
    if ($existing -contains $i.title) { "건너뜀(이미 있음): $($i.title)"; continue }

    if ($DryRun) {
        "[dry-run] $($i.title)  [$($i.labels -join ', ')]  <- temp/issues/$($i.file)"
        continue
    }
    $args = @("issue", "create", "--repo", $Repo, "--title", $i.title, "--body-file", $body)
    foreach ($lb in $i.labels) { $args += @("--label", $lb) }
    & gh @args
}
