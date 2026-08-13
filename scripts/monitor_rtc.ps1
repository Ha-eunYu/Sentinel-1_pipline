# RTC 진행상황 모니터링 (1초마다 갱신)
$rtc_dir = "f:\06_SAR_system\S1\downloads\rtc_grd"
$current_file = ""
$last_size = 0

while ($true) {
    # 가장 최근 파일 찾기
    $latest = Get-ChildItem "$rtc_dir\*.tif" -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if ($latest) {
        $size_mb = [math]::Round($latest.Length / 1MB, 1)
        $size_gb = [math]::Round($latest.Length / 1GB, 2)

        if ($latest.Name -ne $current_file) {
            $current_file = $latest.Name
            $last_size = $latest.Length
            Write-Host "=== 새 파일 시작 ===" -ForegroundColor Cyan
        }

        $size_change = $latest.Length - $last_size
        $last_size = $latest.Length

        # 초당 쓰기 속도 계산
        $speed_kbps = if ($size_change -gt 0) { [math]::Round($size_change / 1024, 0) } else { 0 }

        $time_str = (Get-Date -Format "HH:mm:ss")
        Write-Host "$time_str | $($current_file.Substring(0, [math]::Min(60, $current_file.Length))) | ${size_gb}GB (${speed_kbps}KB/s)" -ForegroundColor Green
    }

    Start-Sleep -Seconds 10
}
# 그냥 터미널에 복붙
# while ($true) { ls "f:\06_SAR_system\S1\downloads\rtc_grd\" -File | sort LastWriteTime -Desc | select -First 1 | % { "$((Get-Date).ToString('HH:mm:ss')) | $($_.Name) | $([math]::Round($_.Length/1GB, 2))GB" }; sleep 2 }
