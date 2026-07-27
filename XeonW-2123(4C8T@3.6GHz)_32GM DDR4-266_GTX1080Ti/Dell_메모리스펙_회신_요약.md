# Dell 기술지원 회신 요약 — 모델 확정 & 메모리(RAM) 호환 스펙

원본 이메일(.eml, base64)과 기술속성 이미지(TechnicalAttributes_1/2.png), 검토서
([review.md](review.md))를 종합한 요약본. **정정 반영(2026-07-27).**

| 항목 | 값 |
| --- | --- |
| **제품명** | **Dell Precision 5820 Tower** (Dell 회신으로 **확정**) |
| Service Tag | **(생략)** |
| Case Number | **(생략)** |
| 회신자 | Kangsan Kim(김강산), Dell Tech Support (080-854-0066) |

## Dell 확인 메모리 (⚠️ 부품번호 정정)

이메일·첨부에 **두 개의 서로 다른 용량** 부품이 등장한다. 앞선 요약에서 이를
`HMAA8GR7AJR4N-XN=16GB`로 잘못 적었으나 **실제는 아래와 같다**:

| 부품번호 | 실제 사양 | Dell 회신 |
| --- | --- | --- |
| **HMA84GR7CJR4N-WM** | **32GB** DDR4-2933, Dual Rank, ECC RDIMM | 사용자 "32GB 맞나?" 문의 → Dell **"맞습니다" 확인** |
| **HMAA8GR7AJR4N-XN** | **64GB** DDR4-3200, Dual Rank, ECC RDIMM | 최초 메모리 스펙 안내에 기재 |

첨부 이미지(TechnicalAttributes)의 기술속성:

- HMA84 계열: **Size 32,768 MB(=32GB), Speed 2933 MHz, Config REGISTERED, ECC,
  Class DUAL RANK, DDR4, 288-pin, 1.2V** (이미지 2로 확인).
- HMAA8 계열: 65,536 MB(=64GB), 3200 MHz, REGISTERED, ECC, DUAL RANK.

## 구매·장착 요점

- **필수 규격**: Xeon W → **ECC Registered DIMM(RDIMM)**. 일반/ECC **UDIMM 불가**,
  Registered/Unbuffered 혼합 불가. 기존 16GB도 ECC RDIMM.
- **Dell이 확정한 부품**: **HMA84GR7CJR4N-WM (32GB DDR4-2933 ECC RDIMM)**.
- **클럭**: 2933/3200 모듈이라도 W-2123(Skylake-W)에선 **2666 MT/s로 다운클럭 동작
  (정상)**.
- **64GB 단일 DIMM(HMAA8…-XN) 주의**: Dell 메모리 매트릭스상 64GB DIMM은 주로
  **Cascade Lake-W** 구성에 배치됨. 현재 CPU가 **Skylake-W(W-2123)** 이므로, 64GB
  모듈 구매 전 **"5820 / ST (생략) / W-2123 조합에서 HMAA8…-XN 64GB 지원 여부"** 를
  Dell에 재확인 권장.
- **증설 구성**(8슬롯 중 2슬롯 사용, 6슬롯 여유):
  - **64GB(권장·저비용)**: 기존과 같은 **16GB RDIMM 2개 추가 → 16GB×4** (4채널 모두
    사용 → 대역폭 이점). 단 현재 16GB 모듈의 정확한 부품번호는 이메일에 없으니
    `Get-CimInstance Win32_PhysicalMemory`로 PartNumber 확인 후 동일/호환 구매.
  - **128GB(장기 권장)**: **HMA84GR7CJR4N-WM 32GB × 4** (4채널, 1 DIMM/채널, 슬롯 4개
    여유, CPU 업그레이드 후에도 재사용).
- **피해야 할 구성**: 16GB×2 + 32GB×1(불균형), 16/32 혼합, RDIMM/UDIMM 혼합, 임의
  슬롯 장착, W-2123에서 64GB 단일 DIMM을 Dell 재확인 없이 구매.

> 상세 판단(왜 느린가·RAM/CPU/신규구매)은 [업그레이드_판단_RAM_CPU_신규구매.md](업그레이드_판단_RAM_CPU_신규구매.md),
> 속도 분석은 [HW_UPGRADE_SPEEDUP_KR.md](HW_UPGRADE_SPEEDUP_KR.md) 참고.
