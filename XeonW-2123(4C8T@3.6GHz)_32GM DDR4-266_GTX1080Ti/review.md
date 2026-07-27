# 종합 검토 결과

추가로 알려주신 Dell 회신에 따라 장비 모델은 **Dell Precision 5820 Tower**로 확정됩니다. 따라서 기존 문서의 “Precision 5820으로 강력 추정”이라는 표현은 이제 **확정**으로 수정해야 합니다.

다만 제가 사용자의 PC에 원격 접속한 것은 아니므로, 아래 내용은 **업로드된 이메일·문서의 2026년 7월 실측 기록과 최근 제공하신 PowerShell 결과를 기준으로 한 설치 자원 검토**입니다. 지금 이 순간의 CPU 사용률, 온도, 여유 RAM 등은 별도 실시간 측정이 필요합니다.

---

## 1. 현재 워크스테이션 자원

| 항목          | 확인된 구성                                           | 평가                                                 |
| ----------- | ------------------------------------------------ | -------------------------------------------------- |
| 모델          | **Dell Precision 5820 Tower**                    | 확정                                                 |
| Service Tag | **(생략)**                                      | Dell 회신 확인                                         |
| CPU         | Intel **Xeon W-2123**, 4코어 8스레드, 3.60~3.90GHz    | Sentinel-1 RTC 씬당 처리속도의 주 병목                       |
| RAM         | **32GB = 16GB × 2**, DDR4-2666 ECC RDIMM         | 용량 부족, 4채널 중 2채널만 사용 중일 가능성이 높음                    |
| RAM 슬롯      | 총 8개 중 2개 사용, 6개 여유                              | 증설 여건 양호                                           |
| GPU         | NVIDIA **GTX 1080 Ti 11GB**                      | 현재 SNAP·sarsen RTC에는 거의 사용되지 않음                    |
| 시스템 SSD     | Samsung 870 SATA SSD 1TB                         | OS·입력·DEM 캐시용으로는 양호하나 NVMe보다 느림                    |
| 데이터 저장장치    | Seagate HDD 4TB × 3, D/E/F                       | 대용량 보관에는 적합, 대형 TIFF 반복 입출력에는 느림                   |
| 가상메모리       | 커밋 한도 약 72.9GB                                   | RAM 초과 시 디스크 스왑으로 처리시간 급증                          |
| WSL 설정      | 이전에 제공한 설정 기준 RAM 28GB, 8 logical CPU, swap 48GB | 물리 RAM을 늘려도 `.wslconfig`를 수정하지 않으면 WSL은 계속 28GB 제한 |

Xeon W-2123은 공식적으로 4개의 메모리 채널과 DDR4-2666을 지원합니다. Dell Precision 5820은 8개의 DIMM 슬롯을 제공하며, 현재 Skylake-W CPU 구성에서는 시스템 기준 최대 256GB가 안내되어 있습니다. ([Intel][1])

현재 문서에 기록된 사양과 실측값은 서로 대체로 일치합니다.

---

## 2. Dell 이메일의 정확한 의미

이메일 헤더상 Dell 발신 도메인의 SPF·DKIM·DMARC 검증이 통과되어 있어, 업로드된 이메일에는 뚜렷한 위조 정황이 없습니다. Dell은 Xeon W 장비에 **ECC Registered DIMM, 즉 RDIMM**을 사용해야 한다고 안내했습니다.  

### 이메일에 등장한 두 메모리는 서로 다른 용량입니다

| 부품번호                 | 실제 사양                                                | Dell 회신                                  |
| -------------------- | ---------------------------------------------------- | ---------------------------------------- |
| **HMA84GR7CJR4N-WM** | **32GB**, DDR4-2933, Dual Rank, ECC, Registered DIMM | 사용자가 “32기가가 맞는가”라고 문의했고 Dell이 **맞다고 확인** |
| **HMAA8GR7AJR4N-XN** | **64GB**, DDR4-3200, Dual Rank, ECC, Registered DIMM | 최초 메모리 사양 안내에 기재                         |

후속 이메일은 명확하게 다음 내용을 확인합니다.

> Vendor Part Number
> HMA84GR7CJR4N-WM 맞습니다.

즉 **HMA84GR7CJR4N-WM은 Dell이 확인한 32GB RDIMM**입니다.

첨부 이미지의 기술 속성에서도 HMA84 계열 대상은 `32,768 MB`, `2933 MHz`, `REGISTERED`, `ECC`, `DUAL RANK`로 표시되고, HMAA8 계열 대상은 `65,536 MB`, `3200 MHz`, `REGISTERED`, `ECC`, `DUAL RANK`로 표시됩니다.

현재 Xeon W-2123에서는 2933 또는 3200 MT/s 모듈을 장착하더라도 실제 동작 속도는 **2666 MT/s로 낮아집니다**. Dell도 Skylake-W에서 2933 RDIMM이 2666으로 동작한다고 명시합니다. 이는 고장이 아니라 정상적인 다운클럭입니다. ([Dell][2])

### 64GB DIMM은 다시 확인하는 것이 안전합니다

Dell 공식 메모리 매트릭스에서는 Skylake-W와 Cascade Lake-W의 지원 구성이 구분되며, **64GB 단일 DIMM 구성은 주로 Cascade Lake-W 쪽에 배치**되어 있습니다. 현재 CPU는 Skylake-W인 W-2123이므로, HMAA8GR7AJR4N-XN 64GB 모듈을 구매하려면 Dell에 다음처럼 다시 확인하는 편이 안전합니다.

> Precision 5820 Tower, Service Tag (생략), Xeon W-2123 구성에서
> HMAA8GR7AJR4N-XN 64GB RDIMM을 실제로 지원하는지 확인 요청

단순히 “Precision 5820에서 사용 가능”이 아니라 **W-2123과의 조합**을 확인해야 합니다. Dell 메모리 구성표는 용량별 DIMM 배치와 CPU 세대별 구성을 별도로 규정합니다. ([Dell][3])

---

## 3. 업로드된 문서에서 수정해야 하는 부분

### `Dell_메모리스펙_회신_요약.md`

이 문서에는 중요한 오류가 있습니다.

현재 문서에는 `HMAA8GR7AJR4N-XN`을 **16GB RDIMM**이라고 정리했지만, 실제 이메일 첨부자료상 이 부품은 **64GB RDIMM**입니다.

따라서 다음 문장은 수정되어야 합니다.

* 기존: `HMAA8GR7AJR4N-XN (16GB DDR4 ECC RDIMM)`
* 수정: `HMAA8GR7AJR4N-XN (64GB DDR4-3200 ECC RDIMM, 현재 W-2123 호환성 재확인 필요)`

그리고 Dell이 별도로 확인한 32GB 부품은 다음과 같이 추가해야 합니다.

* `HMA84GR7CJR4N-WM: 32GB DDR4-2933 ECC RDIMM, Dell 호환 확인`

### `RAM_증설_요청_근거.md`

RAM 부족의 실측 근거는 타당합니다. 씬 하나가 약 18.49GB의 Working Set을 사용하고, 시스템 여유 RAM이 3.7~5.2GB까지 감소했다면 32GB는 확실히 빠듯합니다.

다만 다음 표현은 과도합니다.

> RAM이 넉넉하면 씬 여러 개를 동시에 처리하여 코어 수만큼 단축

현재 SNAP 한 프로세스가 이미 8개 논리 스레드를 거의 모두 사용한다면, RAM을 늘려 두 개의 SNAP 프로세스를 동시에 실행하더라도 동일한 4개 물리코어를 나눠 사용합니다. 따라서 **RAM 증설만으로 배치가 1.3~1.6배 빨라진다고 보장할 수 없습니다.**

RAM 증설의 확실한 효과는 다음입니다.

* `MemoryError` 및 페이지파일 의존 감소
* sarsen 풀씬 처리 가능성 향상
* SNAP 캐시 확대
* SLC 처리 안정성
* Windows와 WSL의 동시 작업 여유
* 메모리 채널 확대 시 일부 메모리 대역폭 개선

배치 속도 증가는 실제 A/B 벤치마크 후에만 수치로 제시하는 것이 정확합니다.

### `HW_UPGRADE_SPEEDUP_KR.md`

전체적인 병목 진단은 적절합니다. CPU가 씬당 속도, RAM이 안정성과 처리 가능 크기를 좌우한다는 구분도 맞습니다.

하지만 다음 두 부분은 수정이 필요합니다.

1. `HMAA8GR7AJR4N-XN`을 16GB로 기록한 부분은 잘못되었습니다.
2. CPU 코어 수에 처리시간이 거의 선형적으로 반비례한다는 가정은 낙관적입니다.

SNAP 그래프에는 병렬화가 잘 되는 연산과 그렇지 않은 연산이 함께 들어가며, 메모리 대역폭·타일 캐시·DEM 접근·GeoTIFF 출력 등도 영향을 줍니다. 따라서 4코어에서 18코어로 교체한다고 항상 4.5배 빨라지는 것은 아닙니다.

보수적으로는 다음 정도로 표현하는 편이 안전합니다.

| CPU 변경        |  예상 처리량 개선 |
| ------------- | ---------: |
| 4코어 → 8코어     | 약 1.5~1.9배 |
| 4코어 → 10~14코어 |     약 2~3배 |
| 4코어 → 18코어    |   약 2.5~4배 |

정확한 값은 동일 씬·동일 그래프·동일 해상도로 측정해야 합니다.

### `업그레이드_판단_RAM_CPU_신규구매.md`

이 문서의 모델 상태는 다음처럼 수정하면 됩니다.

* 기존: `Precision 5820 Tower로 강력 추정`
* 수정: `Dell 기술지원 회신으로 Precision 5820 Tower 확정`

“정확한 Dell 모델 확인”이라는 다음 조치는 이미 완료되었습니다.

Precision 5820 공식 프로세서 목록에는 W-2145, W-2155, W-2175, W-2195뿐 아니라 Cascade Lake-W인 **W-2295 18코어 36스레드**도 포함됩니다. ([Dell][4])

그러나 Service Tag별 출고 구성에서는 전원공급장치와 냉각장치가 다를 수 있으므로, CPU만 구매해서 교체하면 안 됩니다.

---

## 4. 현재 실질적인 병목 순위

### 1위: CPU 코어 수

Xeon W-2123은 4코어 8스레드입니다. SNAP RTC가 8개 논리 스레드를 사용하고 처리량이 약 0.17~0.26 Mpx/s에서 유지된다면, 씬당 처리속도의 가장 큰 제한은 CPU입니다.

문서에 기록된 28~35분과 60~86분이 서로 모순되는 것은 아닙니다. 씬에 따라 출력 영역과 회전된 bounding box의 크기가 달라져 출력 화소가 4억 개 수준인 경우와 8억 개 수준인 경우가 있기 때문입니다. 처리시간은 압축 파일 크기보다 **실제 출력 화소수**에 더 강하게 비례합니다.

### 2위: RAM 용량과 메모리 채널

32GB는 현재 작업에서 최소한의 실행만 가능한 수준입니다.

현재 16GB 모듈 2개라면 Xeon W-2123의 4개 메모리 채널 중 2개만 사용 중일 가능성이 높습니다. 따라서 64GB를 **16GB × 4**로 구성하면 용량 증가뿐 아니라 네 개 채널을 모두 사용할 수 있어 메모리 대역폭 측면에서도 더 합리적입니다.

RAM 64GB는 “속도 업그레이드”보다는 **처리 실패와 스왑을 방지하는 안정성 업그레이드**로 보는 것이 정확합니다.

### 3위: F 드라이브 여유 공간

최근 제공하신 PowerShell 출력에서는 F 드라이브가 3.64TB 중 약 89.37GB만 남아 **98% 사용 중**이었습니다.

출력 하나가 2~3GB라면 단순 계산으로 약 30~40개 출력만 추가되어도 공간이 소진될 수 있습니다. 중간파일, 로그, 임시파일, 재처리본까지 포함하면 실제 여유는 더 적습니다.

현재는 CPU나 RAM 업그레이드보다 먼저 다음 조치가 필요합니다.

* 완료 산출물 NAS 이전
* 중복 RTC·Frost 결과 정리
* 압축 가능한 중간파일 압축
* 출력 경로를 여유 있는 D/E 또는 새 SSD로 변경
* 최소한 수백 GB 이상의 작업 여유 확보

### 4위: SATA SSD와 HDD 구조

Precision 5820은 SATA 드라이브뿐 아니라 FlexBay M.2/U.2 NVMe 또는 Dell Ultra-Speed PCIe 카드를 통한 M.2 NVMe 확장을 지원합니다.

새 NVMe SSD를 다음 용도로 사용하면 좋습니다.

* SNAP 임시 디렉터리
* DEM 캐시
* 압축 해제된 Sentinel-1 입력
* 처리 중간산출물
* 최종 출력 후 HDD/NAS 이동

다만 NVMe를 추가해도 CPU 중심 RTC 연산 자체가 몇 배 빨라지지는 않습니다. 주로 입출력 대기, 임시파일 처리와 운영 안정성이 개선됩니다.

### 5위: GPU

GTX 1080 Ti의 11GB VRAM은 여전히 딥러닝 실험용으로 활용 가치가 있습니다. 그러나 현재 문서의 SNAP·sarsen 실행 경로에서는 GPU 사용이 거의 없으므로, RTC 전처리 속도만을 위해 GPU를 교체하는 것은 우선순위가 낮습니다.

---

## 5. 권장 RAM 구성

### 비용을 최소화한 64GB 구성

**기존 16GB × 2와 동일한 16GB RDIMM 2개를 추가하여 16GB × 4 = 64GB**로 구성하는 방법이 가장 합리적입니다.

장점은 다음과 같습니다.

* 기존 RAM 재사용
* 4개의 메모리 채널 사용 가능
* 비용 최소
* SNAP·WSL 작업 여유 증가

현재 16GB 모듈의 정확한 부품번호는 업로드된 이메일에 나오지 않습니다. 구매 전에 아래 명령으로 확인해야 합니다.

```powershell
Get-CimInstance Win32_PhysicalMemory |
    Select-Object DeviceLocator, BankLabel, Manufacturer, PartNumber,
                  @{N='CapacityGB';E={[math]::Round($_.Capacity/1GB)}},
                  Speed, ConfiguredClockSpeed
```

동일 부품을 구하지 못하더라도 용량, RDIMM/ECC 여부, rank, 전압, 속도 규격을 최대한 맞추는 것이 좋습니다.

### 권장 128GB 구성

장기적으로는 **32GB × 4 = 128GB**가 가장 깔끔합니다.

Dell이 확인한 부품:

```text
SK hynix HMA84GR7CJR4N-WM
32GB DDR4-2933 ECC RDIMM
Dual Rank
```

현재 W-2123에서는 2666 MT/s로 동작합니다.

이 구성은 다음 장점이 있습니다.

* 네 개 메모리 채널 사용
* 1 DIMM per Channel 구성
* 4개 슬롯 추가 여유
* 8×16GB보다 간단한 구성
* 이후 CPU 업그레이드 시에도 재사용 가능성이 높음

기존 16GB × 2는 별도 보관하거나 다른 호환 장비에 사용할 수 있습니다.

### 피해야 할 구성

* 기존 16GB × 2에 32GB 모듈 한 개만 추가하는 64GB 구성
* 16GB와 32GB를 불균형하게 혼합한 96GB 구성
* ECC UDIMM과 ECC RDIMM 혼합
* Registered와 Unbuffered 혼합
* 임의 슬롯 장착
* 현재 W-2123에서 64GB 단일 DIMM을 Dell 재확인 없이 구매

---

## 6. CPU 업그레이드 판단

Precision 5820 플랫폼 자체는 W-2295까지 공식 프로세서 옵션으로 포함합니다. W-2295는 18코어 36스레드, 165W TDP입니다. ([Dell][4])

그러나 CPU 업그레이드 전 다음 세 가지가 반드시 확인되어야 합니다.

### 전원공급장치

Precision 5820은 425W 또는 950W 전원공급장치 구성으로 판매되었습니다.

GTX 1080 Ti가 장착된 상태에서 165W CPU로 바꾸려면 **950W PSU인지 확인하는 것이 사실상 필수**입니다. 425W라면 CPU만 교체하는 방안은 권장하기 어렵습니다.

### CPU 냉각장치

W-2123은 120W, W-2295는 165W이므로 고TDP CPU용 히트싱크와 송풍 구조가 필요합니다. 기존 저전력 CPU용 냉각장치를 그대로 사용해서는 안 됩니다.

### BIOS와 서비스 태그 구성

공식 모델 목록에 W-2295가 있어도, 구체적인 보드 리비전·BIOS·PSU·히트싱크 구성이 서비스 태그별로 다를 수 있습니다. Dell에 다음 질문을 보내는 것이 정확합니다.

> Precision 5820 Tower, Service Tag (생략)의 현재 메인보드, BIOS, PSU 및 히트싱크 구성에서 Xeon W-2295로 교체 가능한지 확인 부탁드립니다. 추가로 필요한 Dell 부품번호도 안내 부탁드립니다.

---

## 7. 최종 권고 순서

현재 상황에서는 다음 순서가 가장 합리적입니다.

**즉시 조치:** F 드라이브 공간 확보.
**1차 하드웨어:** 64GB를 원하면 기존과 같은 16GB RDIMM 2개 추가, 또는 장기적으로 32GB × 4 = 128GB 구성.
**2차 조치:** WSL 메모리 제한을 새 물리 RAM에 맞춰 수정.
**3차 성능 개선:** PSU·히트싱크·BIOS를 확인한 뒤 W-2295 등 고코어 CPU 검토.
**4차 저장 개선:** NVMe SSD를 임시작업·DEM·입력·출력 scratch 용도로 추가.
**후순위:** RTC만을 위한 GPU 교체.

핵심적으로, **RAM 64~128GB 증설은 처리 실패와 스왑을 막는 데 필요하고, 씬당 처리시간을 본질적으로 줄이는 것은 CPU 업그레이드**입니다. 다만 기존 문서에 적힌 “RAM만으로 배치 20시간이 13~16시간으로 단축된다”거나 “18코어면 반드시 17분으로 줄어든다”는 수치는 현재 실측만으로 확정할 수 없으므로, 공식 문서에서는 범위 또는 예상치로 낮춰 쓰는 것이 정확합니다.

[1]: https://www.intel.com/content/www/us/en/products/sku/125036/intel-xeon-w2123-processor-8-25m-cache-3-60-ghz/specifications.html?utm_source=chatgpt.com "Intel® Xeon® W-2123 Processor (8.25M Cache, 3.60 GHz)"
[2]: https://www.dell.com/support/manuals/en-us/oth-xlt5820/precision_5820_om_pub/memory-specifications?guid=guid-5ee14007-db24-4d37-aecb-34dea3370abb&lang=en-us "Dell Precision 5820 Tower Owner's Manual | Dell 대한민국"
[3]: https://www.dell.com/support/manuals/en-us/precision-5820-workstation/precision_5820_om_pub/memory-configuration?guid=guid-ce1561c8-88a9-45e3-bc3b-762cbb37e073&lang=en-us "Dell Precision 5820 Tower  Owner's Manual  | Dell Australia"
[4]: https://www.dell.com/support/manuals/en-us/precision-5820-workstation/precision_5820_om_pub/system-specifications?guid=guid-cc0fbc47-6600-410a-8bbf-1793e2767549&lang=en-us "Dell Precision 5820 Tower  Owner's Manual  | Dell Australia"
