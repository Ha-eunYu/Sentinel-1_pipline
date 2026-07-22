# GTC 산출물(*_gtc_db.tif) 아카이브 이동
#
# GTC는 육안 비교 전용(수체 탐지에 미사용, RTC_VS_GTC_KR.md 참고)이라, 작업
# 폴더 downloads/rtc_grd/ 에서 RTC 산출물과 섞여 있던 것을 별도 폴더
# downloads/gtc/ 로 분리 보관한다. 같은 볼륨(F:) 내 이동이라 즉시 완료된다.
#
# ⚠️ 실행 시점: batch_grd_gtc.py 배치가 끝난 뒤 실행할 것. 배치가 도는 중이면
#    현재 쓰는 중인 tif는 윈도우 파일 잠금으로 이동이 실패하고 그대로 남는다
#    (스크립트는 이를 감지해 건너뛴다). 배치가 새 GTC를 계속 만들므로, 완전히
#    정리하려면 배치 종료 후 한 번 실행하는 것이 깔끔하다. 재실행 안전(idempotent).
#
# 사용:
#   powershell -ExecutionPolicy Bypass -File archive_gtc.ps1              # 이동 실행
#   powershell -ExecutionPolicy Bypass -File archive_gtc.ps1 -WhatIf     # 무엇이 이동될지만 표시
#   powershell -ExecutionPolicy Bypass -File archive_gtc.ps1 -IncludeExcluded  # excluded_china_japan의 GTC도 이동

param(
    [switch]$WhatIf,           # 실제 이동 없이 대상만 출력
    [switch]$IncludeExcluded   # downloads/excluded_china_japan 의 GTC도 이동(기본은 rtc_grd만)
)

$ErrorActionPreference = "Continue"
$ProjectDir = "f:\06_SAR_system\S1"
$SrcDir = Join-Path $ProjectDir "downloads\rtc_grd"
$DstDir = Join-Path $ProjectDir "downloads\gtc"
$ExclSrc = Join-Path $ProjectDir "downloads\excluded_china_japan"
$ExclDst = Join-Path $DstDir "excluded_china_japan"

function Move-GtcFrom($src, $dst) {
    if (-not (Test-Path $src)) { return }

    # *_gtc_db.tif 및 사이드카(.aux.xml 등) 포함
    $files = Get-ChildItem -Path $src -Filter "*_gtc_db.tif*" -File -ErrorAction SilentlyContinue
    if (-not $WhatIf -and $files.Count -gt 0 -and -not (Test-Path $dst)) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
    }
    $moved = 0; $skipped = 0
    foreach ($f in $files) {
        $target = Join-Path $dst $f.Name
        if ($WhatIf) {
            Write-Host "[WhatIf] $($f.Name)  ->  $dst"
            continue
        }
        try {
            Move-Item -LiteralPath $f.FullName -Destination $target -Force -ErrorAction Stop
            $moved++
        } catch {
            # 배치가 쓰는 중이면 파일 잠금으로 여기로 온다 -> 건너뜀
            Write-Host "건너뜀(사용 중이거나 오류): $($f.Name)"
            $skipped++
        }
    }
    Write-Host "$src -> $dst : 이동 $moved, 건너뜀 $skipped"
}

Move-GtcFrom $SrcDir $DstDir
if ($IncludeExcluded) {
    Move-GtcFrom $ExclSrc $ExclDst
} else {
    Write-Host "참고: excluded_china_japan 의 GTC는 감사용 rtc/gtc 짝을 유지하려 그대로 둠 (-IncludeExcluded 로 함께 이동 가능)."
}
