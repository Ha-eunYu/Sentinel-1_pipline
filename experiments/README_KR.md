# experiments/ — 실험·벤치마크 산출물

`downloads/`는 **파이프라인 정규 산출물**만 둔다. 한 번 답을 얻고 나면 다시
만들지 않는 **실험·비교 산출물**은 여기로 뺀다(2026-08-17 분리).

정규 산출물과 섞여 있으면 "이건 지워도 되나"를 매번 다시 판단해야 하고, 실제로
용량 정리 때마다 그 판단에 시간이 들었다.

| 폴더 | 용량 | 무엇을 실험했나 | 결론이 어디 있나 |
| --- | ---: | --- | --- |
| `dem_cop30_vs_ngii/` | 4.6 GB | 같은 씬을 COP30 / COP30 보정판 / NGII 하이브리드 DEM으로 각각 RTC | [TERRAIN_AUX_DATA_KR.md](../docs/pipeline/TERRAIN_AUX_DATA_KR.md) |
| `dem_compare/` | 1.9 GB | `754B` 씬 + DEM 정사영상·autoc 변형 비교 | 〃 |
| `bench_snap/` | 1.0 GB | 같은 씬(`754B`)을 **SNAP**으로 RTC | [RTC_SARSEN_KR.md](../rtc_sarsen_benchmark/RTC_SARSEN_KR.md) |
| `bench_sarsen/` | 0.1 GB | 같은 씬을 **sarsen**(SNAP 없이)으로 RTC — 위와 1:1 대조 | 〃 |
| `otsu_on_gtc/` | 0.3 GB | GTC(지형 평탄화 없음)로 Otsu 수체 판별 → RTC와 비교 | [RTC_VS_GTC_KR.md](../docs/pipeline/RTC_VS_GTC_KR.md) |
| `dem_clip_test/` | 0.2 GB | DEM clip 범위 실험 | — |

## 정리 기준

- **결론이 문서에 반영됐으면 래스터는 지워도 된다.** 위 표의 "결론이 어디
  있나"가 비어 있는 것만 확인 후 정리한다.
- 재현이 필요하면 원본 zip이 있는 한 다시 만들 수 있다. 어떤 씬이었는지는
  파일명에 남아 있다(대부분 `754B`, `38C3`, `74BD`).
- 이 폴더는 git에 올리지 않는다(`.gitignore`). 이 README만 추적한다.
