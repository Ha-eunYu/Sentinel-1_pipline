# 이슈 트래킹

파이프라인을 돌리다 반복적으로 부딪힌 문제와 그 상태를 모아둔다. 한 번 겪고
로그와 함께 사라지면 다음에 같은 시간을 쓰게 되는 것들이다.

- **상태**: 🔴 미해결 / 🟡 우회 중 / 🟢 해결
- 코드에 이미 반영된 회피책은 "조치"에 어느 파일인지 적는다.
- 새 이슈는 맨 아래에 번호를 이어 붙인다.

관련: [TODO_KR.md](TODO_KR.md)(할 일) · [PROGRESS_KR.md](PROGRESS_KR.md)(진행상황) ·
[WORKLOG_20260814_KR.md](WORKLOG_20260814_KR.md)(최근 작업일지)

## GitHub 이슈 번호 대조

**이 문서의 번호와 GitHub 이슈 번호는 다르다.** 헷갈리지 않도록 대조표를 둔다
(등록 2026-08-14, 매핑 원본은 `data/github_issues.json`).

| 이 문서 | GitHub | 제목 |
| --- | --- | --- |
| #1 | [#1] | SNAP external DEM에 VRT |
| #2 | [#2] | COP30 하구 결측 |
| #3 | — | EGM 이중 적용 (해결, 등록 안 함) |
| #4 | [#3] | PowerShell stderr 오탐 |
| #5 | — | 궤도번호 앞 0 유실 (해결, 등록 안 함) |
| #6 | [#4] | GDAL_DATA 경고 |
| #7 | [#5] | South_Korea.geojson 해안·도서 제외 |
| #8 | [#8] | 연도 간 관측 범위 차이 |
| #9 | [#7] | 7/14 젖은 토양 과대추정 |
| #10 | — | 로그가 루트에 쌓임 (해결, 등록 안 함) |
| #11 | [#9] | PowerShell 한글 인코딩 |
| #12 | [#10] | 상대궤도 오프셋 오판 |
| #13 | (등록 대기) | external DEM 범위 혼재 |
| #14 | (등록 대기) | PowerShell `-File` 인자·`Wait-Process` 한도 |

> ✅ **GitHub #6은 #8의 중복이라 닫았다**(2026-08-14). 제목을 정정하면서 문구가
> 바뀌어(“2배 차이” 삭제) 중복 검사가 빗나갔다. 재발 방지로
> [create_issues.ps1](../../scripts/create_issues.ps1)이 이제 **본문 파일 →
> 이슈 번호 매핑**(`data/github_issues.json`)으로 중복을 거른다 — 제목을 고쳐도
> 같은 이슈로 인식한다.

---

## #1 🟡 SNAP external DEM에 VRT를 주면 읽지 못한다

**증상**

```text
No product reader found for downloads/dem/cop30_korea.vrt
```

`_void_a.log` · `_void_b.log`(2026-08-03 void 패치 실행)에서 씬마다 반복 발생.
SNAP `Terrain-Flattening`/`Terrain-Correction`의 `externalDEMFile`에 GDAL VRT를
주면 리더를 찾지 못하고 그래프가 실패한다.

**조치** — DEM을 **GeoTIFF로 구워서** 넘긴다.
[make_basin_dem.py](../../s1/tools/dem/make_basin_dem.py)가 COP30 타일을 유역·임의
범위로 잘라 GeoTIFF로 만들고,
[batch_grd_rtc_frost.py](../../s1/tools/preprocess/batch_grd_rtc_frost.py)의 `--dem`
도움말에 "VRT는 안 된다"를 명시해 두었다.

**남은 것** — 근본 해결(SNAP이 VRT를 읽게 하는 방법)은 확인하지 않았다. 현재는
GeoTIFF 우회로 충분하다.

## #2 🟡 SNAP 자동 캐시 COP30이 하구 수역을 결측으로 만든다

**증상**: `demName="Copernicus 30m Global DEM"`(SNAP 자동 다운로드)으로 RTC를
돌리면 하구 수역이 무효로 해석돼 결측이 생긴다. **영산강 제약면적의 20.2%**가
그렇게 날아갔다(2026-08-03 실측).

**조치** — 같은 COP30 값이라도 **GeoTIFF로 구워 external DEM으로 물리면 결측
0.00%**다. 하구가 포함된 유역은 `--dem`을 반드시 주고 처리한다
([rtc_basin_extdem.py](../../s1/tools/preprocess/rtc_basin_extdem.py) 모듈 주석).

## #3 🟢 external DEM에 EGM 보정을 이중 적용하면 약 25 m 어긋난다

COP30은 이미 타원체고라 `--dem-egm`을 주면 지오이드 보정이 두 번 걸린다.
NGII처럼 **정표고 DEM일 때만** 켤 것. `--dem-egm` 도움말에 경고를 넣었다.

## #4 🟡 PowerShell에서 네이티브 stderr가 "실패"로 보인다

**증상**: SNAP gpt는 정상 실행 중에도 stderr로 SLF4J·INFO를 뿜는다.
PowerShell이 이걸 ErrorRecord로 감싸 로그에 `NativeCommandError`가 남고,
`$?`가 `$false`가 되어 **성공한 실행이 실패로 보인다**.

```text
conda : SLF4J: Failed to load class "org.slf4j.impl.StaticLoggerBinder".
    + FullyQualifiedErrorId : NativeCommandError
```

**조치** — 성공 여부는 stderr가 아니라 **배치 러너가 찍는 요약행**으로 판단한다
(`배치 완료: 성공 N / 건너뜀 N / 실패 N`). 로그 감시 필터를 만들 때도 이
요약행과 `실패:` 라인을 봐야 한다. 네이티브 명령에 `2>&1`을 붙이지 말 것.

## #5 🟢 셸이 궤도번호 앞의 0을 떨군다

`--orbits 008632,...`를 따옴표 없이 넘기면 PowerShell이 숫자 배열로 해석해
`8632`로 전달한다. 6자리 매칭이 전부 실패해 "처리할 그룹이 없습니다"로 즉시
종료했다(2026-07-30).

**조치** — 인자를 따옴표로 묶고,
[scene.py](../../s1/core/scene.py)의 `normalize_orbit()`이 `zfill(6)`으로 정규화한다.

## #6 🟡 GDAL_DATA 미설정 경고

```text
Warning 3: Cannot find gdalvrt.xsd (GDAL_DATA is not defined)
```

`_ext_ys*.err` 등에서 반복. VRT 생성·읽기는 정상 동작하므로 **무해**하지만
로그를 시끄럽게 한다. 필요하면 환경변수 `GDAL_DATA`를 conda 환경의
`share/gdal`로 지정한다.

## #7 🔴 `geojson/South_Korea.geojson`이 해안·도서를 제외한다

좌표로 실측했다(2026-08-13). 이 폴리곤은 **꼭짓점 13개짜리 단일 폴리곤**이고,
남해안·동해안·서남해 도서·제주가 통째로 빠진 내륙 덩어리다.

| 도시 | South_Korea.geojson | Korea_Peninsula.geojson |
| --- | --- | --- |
| 서울·대전·대구 | 내부 | 내부 |
| 부산·울산·포항 | **제외** | 내부 |
| 강릉 | **제외** | 내부 |
| 여수·해남·완도·목포 | **제외** | 내부 |
| 제주 | **제외** | 내부 |

폴리곤 범위 `lon 126.259~129.280 / lat 34.690~38.837`.
(비교: Korea_Peninsula는 링 1,766개·꼭짓점 9,711개의 실제 해안선)
[download_south_korea_month.py](../../s1/tools/download/download_south_korea_month.py)
주석도 같은 문제를 지적하고 대권역 shp를 쓰고 있다.

**영향** — 26년·25년 7월 남한 궤도 선별
([PROCESS_202507_202607_KR.md](../pipeline/PROCESS_202507_202607_KR.md) 1절)이
이 폴리곤을 썼다. 기록된 남한 커버율이 해안·도서만큼 과소평가돼 있고,
"남한 0%"로 제외한 궤도 중 제주·해남을 실제로 찍은 것이 섞여 있을 수 있다.

**해야 할 것** — 대권역 shp(`s1.core.paths.BASIN_SHP`) 기준으로 커버율을 다시
재고, 선별 결과가 바뀌면 문서를 갱신한다.

## #8 🔴 연도 간 관측 범위가 달라 면적 비교가 성립하지 않는다

같은 상대궤도라도 그날 찍힌 **프레임 수가 달라 관측 범위가 다르다**. 26년에만
관측된 구역은 25년엔 "물 없음"이 아니라 "모름"인데, 면적 합계에는 0으로 들어간다.

**해야 할 것** — **(대권역 × 상대궤도)를 비교 단위**로 삼고, 양쪽 다 유효화소인
픽셀만 남기는 교집합 마스크를 씌운 뒤 집계한다. 한강처럼 한 궤도가 다 못 덮는
대권역은 궤도별 부분면적으로 나눠 각각 비교하고, 합산보다 **궤도별 변화율**을
주 지표로 둔다([DROUGHT_KR.md](../drought/DROUGHT_KR.md) 3절).

> 2026-08-14 정정: 예전에 이 이슈의 사례로 들었던 "2025-07-18 o003280 ↔ 2026
> 계열 A(유효화소 8.79억 vs 17.85억)"는 **애초에 같은 상대궤도가 아니었다**
> (#12). 문제 자체는 유효하지만 사례는 폐기한다.

## #12 🟢 절대궤도 175배수 산술로 상대궤도를 판단해 짝을 잘못 지었다

**증상** — "절대궤도 차이가 175의 배수면 같은 상대궤도"라는 규칙으로
`2025-07-18 o003280 ↔ 2026 o008355/8530/8705`를 같은 궤도로 판단했다.
STAC 메타데이터로 확인하니 각각 **rel 134**와 **rel 32**로 서로 다른 궤도였다.

**원인** — 그 규칙은 **같은 위성·같은 시기**에만 성립한다. 위성별
`(절대궤도−상대궤도) mod 175` 오프셋이 다르고(S1A 72, S1D 41), **S1C는
2025년 171 → 2026년 98로 오프셋이 바뀌었다**(최종 궤도 위치 확보 전후).

**조치** — 상대궤도는 STAC `sat:relative_orbit`으로 확인한다.
[relative_orbit_survey.py](../../s1/tools/audit/relative_orbit_survey.py)로
5개년 인벤토리를 만들고 [RELATIVE_ORBITS_KR.md](../pipeline/RELATIVE_ORBITS_KR.md)
에 정리했다. 잘못된 짝을 쓴 문서(DROUGHT_KR 2-3절)에 정정 표시를 달았다.

## #9 🔴 26년 7/14 두 궤도가 젖은 토양으로 과대추정된다

`o003668`(−11.45 dB) · `o003675`(−11.85 dB)는 다른 날(−13~−15 dB)보다 임계값이
2~3 dB 높고 분리도 η도 0.51/0.57로 낮다. 면적이 Refined Lee 대비 +39% / +17%로
뛰었다. 태풍 직후 젖은 토양이 넓게 어두워지며 이봉 구조가 무너진 것으로 보인다.

**조치** — 검증 전 사용 금지로 표시
([WATER_AREA_KR.md](../water/WATER_AREA_KR.md)). 25년 7/19 fallback 궤도도 동일.

## #10 🟡 실행 로그가 저장소 루트에 쌓인다

배치를 돌릴 때마다 `_vh2025.log` 같은 로그·에러 파일이 루트에 남았다
(2026-08-13 기준 64개, 442 KB). git에는 안 올라가지만(`*.log`/`*.err` 무시)
루트를 어지럽힌다.

**조치** — `temp/logs/`로 옮기고 그 폴더를 통째로 무시하도록 했다. 앞으로
배치 로그는 이 폴더에 쓴다.

```powershell
conda run -n s1_snappy python -m s1.tools.preprocess.batch_grd_rtc_frost --month 202608 `
    *> temp/logs/_rtc_202608.log
```

## #11 🟢 BOM 없는 .ps1은 한글이 깨져 파서 오류를 낸다

**증상**

```text
식 또는 문에서 예기치 않은 'data-quality"= @{ color = "d93f0b"; desc = "?낅젰' 토큰입니다.
해시 리터럴이 완전하지 않습니다.
```

`scripts/create_issues.ps1`을 UTF-8(BOM 없음)로 저장했더니 실행이 안 됐다.
**Windows PowerShell 5.1은 BOM이 없는 `.ps1`을 시스템 ANSI(CP949)로 읽는다.**
한글 주석·문자열이 깨지면서 따옴표 짝이 무너져 구문 자체가 망가진다.

**조치** — 저장소의 `.ps1`을 전부 **UTF-8 with BOM**으로 다시 저장했다
(`archive_gtc.ps1`, `create_issues.ps1`, `monitor_new_scenes.ps1`).
`create_issues.ps1` 헤더에 경고를 넣었다.

> 편집기가 BOM을 떨구는 일이 있으니, 한글이 든 `.ps1`을 고친 뒤에는
> `Get-Content -Encoding Byte`로 앞 3바이트가 `EF BB BF`인지 확인하거나
> 파서로 검사한다:
>
> ```powershell
> $e = $null
> [System.Management.Automation.Language.Parser]::ParseFile('scripts/x.ps1', [ref]$null, [ref]$e)
> $e.Count   # 0 이어야 정상
> ```

### 증상 2 — 한글을 네이티브 명령 인자로 넘기면 깨진다

`gh issue create --title "한글 제목"` 처럼 넘기면 PS 5.1이 네이티브 명령 인자를
**콘솔 코드페이지로 인코딩**해 전달한다. UTF-8을 기대하는 프로그램(gh·git·curl)
에서 글자가 깨진다. 본문 파일은 UTF-8이라 멀쩡한데 **제목만 깨지는** 형태로
나타나 원인을 찾기 어렵다.

### 규약 (한글이 든 스크립트를 쓸 때마다 확인)

1. **`.ps1`은 UTF-8 with BOM.** 편집기가 BOM을 떨굴 수 있으니 수정 후 파서로 검사.
2. **한글을 네이티브 명령 인자로 넘기지 않는다 — 파일로 넘긴다.**
   - GitHub: `gh api --method POST repos/O/R/issues --input payload.json`
     (제목·본문·라벨을 UTF-8 JSON에. **JSON에는 BOM 금지** — 서버 파싱 실패)
   - git: `git commit -F message.txt`
   - 부득이하면 스크립트 앞에서 콘솔을 UTF-8로 고정:
     `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + `chcp 65001`
3. **PowerShell로 파일 쓸 때** `Set-Content`/`Add-Content`는 기본이 시스템 ANSI다.
   다른 도구가 읽을 파일은 `-Encoding utf8`을 명시하거나
   `[System.IO.File]::WriteAllText(path, text, New-Object System.Text.UTF8Encoding($false))`
   로 BOM 유무까지 지정한다.
4. **파이썬으로 `.ps1`을 생성·수정하면** `encoding="utf-8-sig"`로 쓴다(BOM 포함).

**조치** — [create_issues.ps1](../../scripts/create_issues.ps1)을
`gh api --input <UTF-8 JSON>` 방식으로 재작성해 **한글이 인자로 가지 않게** 했다.
콘솔 인코딩도 스크립트 앞에서 UTF-8로 고정한다.

## #13 🟡 external DEM 범위가 산출물마다 달랐다

### 증상

`--dem` 옵션 도입(2026-08-10) 이후의 VH 산출물이 **서로 다른 external DEM**으로
구워져 있었다. 로그를 대조해 확인한 8월분:

| DEM | 처리된 씬 | 범위 | 제주 |
| --- | --- | --- | --- |
| `korea_full_cop30.tif` | D0A4·E160·3EEB(25-08-06), 9A11·C40B(25-08-12), 3B05·B10F(26-08-02) | 125.0~131.0E, 32.9~39.9N | ✅ |
| `korea_cop30.tif` | 2B35·9FBB·9F4F(25-08-11), EF16·FC19(26-08-07) | 125.4~129.9E, **33.8**~38.7N | ❌ |
| `han_cop30.tif` | 17B9(26-08-02) | 125.7~129.9E, 35.6~39.2N | ❌ 부산·목포도 빠짐 |

**DEM 밖 영역은 RTC 산출물에서 무효(결측)로 남는다.** 유역 단위 작업에는 유역
clip DEM이 빠르고 합리적이지만, 그 산출물을 **남한 전역 비교에 섞어 쓰면**
어떤 씬은 제주가 없고 어떤 씬은 있는 상태가 된다. 면적 비교가 조용히 깨진다.

**조치** — 남한 전역 비교용 산출물은 **`korea_full_cop30.tif` 하나로 통일**한다
(2026-08-14 결정). 이것만 남한 전역 + 제주 + 울릉을 덮는다. 재처리 도구는
[rebake_vh_extdem.ps1](../../scripts/rebake_vh_extdem.ps1) — 배치 러너가
산출물이 있으면 건너뛰므로 **삭제 후 재실행**한다.

**남은 것** — 산출물에 어떤 DEM을 썼는지 파일 자체에 기록이 없다. 지금은
실행 로그(`temp/logs/*.log`의 `DEM:` 줄)를 뒤져야 안다. GeoTIFF 메타데이터나
사이드카에 DEM 이름을 남기는 것을 검토할 것.

## #14 🟢 PowerShell `-File` 인자와 `Wait-Process` 한도

### 증상 1 — `-File`로 부르면 배열 파라미터가 깨진다

```text
Cannot convert value "32368,7312,31800,8216" to type "System.Int32[]"
```

`powershell -File script.ps1 -WaitFor 32368,7312`처럼 부르면 인자가 **전부
문자열**로 넘어온다. `[int[]]` 파라미터는 쉼표 문자열을 배열로 변환하지 못한다.
(`-Command`로 부르면 PowerShell이 파싱하므로 동작한다 — 호출 방식에 따라
결과가 달라져 헷갈린다.)

**조치** — 스크립트 파라미터를 `[string]`으로 받고 내부에서 `.Split(",")` 한다.

### 증상 2 — `Wait-Process -Timeout`은 9시간을 못 넘긴다

```text
The 86400 argument is greater than the maximum allowed range of 32767
```

`-Timeout`은 초 단위 `Int16` 범위(최대 32767초 ≈ 9.1시간)다. RTC 배치는
하루를 넘기기도 한다.

**조치** — 폴링 루프로 대기한다.

```powershell
while (Get-Process -Id $procId -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 60 }
```
