# SNAPPY(esa_snappy) 가이드 — esa-snappy-master 레퍼런스 포함

이 문서는 SNAP의 Python 인터페이스인 **snappy / esa_snappy**를 설명하고, 프로젝트에 포함된
[esa-snappy-master/](esa-snappy-master/) 참고 저장소(공식 [senbox-org/esa-snappy](https://github.com/senbox-org/esa-snappy)의
사본)의 모든 내용을 레퍼런스로 정리한 것입니다. 이 프로젝트의 전처리 스크립트
[prepro.py](prepro.py)와 [prepro_gpt.py](prepro_gpt.py)가 각각 어떤 방식을 쓰는지도 함께 설명합니다.

---

## 1. snappy란 무엇인가

**snappy**는 ESA SNAP(Sentinel Application Platform)의 기능을 Python에서 쓸 수 있게 해주는
인터페이스입니다. SNAP 자체는 Java로 구현되어 있어서, Python에서 SNAP을 쓰려면
Java-Python 다리(bridge)가 필요합니다. 이름과 구조는 SNAP 버전에 따라 변해왔습니다:

| SNAP 버전 | 패키지 이름 | 설명 | 참고 문서 |
| --- | --- | --- | --- |
| ≤ 9 | `snappy` | snap-engine 내부 모듈. Python 2.7~3.6만 지원 | [Configure Python … (snappy) interface (SNAP versions <= 9).md](<esa-snappy-master/Configure Python to use the SNAP-Python (snappy) interface (SNAP versions -= 9).md>) |
| 10~11 | `esa_snappy` | 독립 SNAP 플러그인으로 분리 (이 저장소가 그 소스). SNAP 11에서는 Plugin Manager로 수동 설치 필요 | [Configure Python … (esa_snappy) interface (SNAP version 10+).md](<esa-snappy-master/Configure Python to use the SNAP-Python (esa_snappy) interface (SNAP version 10+).md>) |
| 12+ | `esa_snappy` (+ SNAPISTA 통합) | PyPI(`pip install esa-snappy`)로 배포, Python 3.9~3.13 지원. Terradue의 SNAPISTA가 패키지 안에 통합됨 | [Installation and configuration … (SNAP version 12+).md](<esa-snappy-master/Installation and configuration of the SNAP-Python (esa_snappy) interface (SNAP version 12+).md>) |

이 프로젝트는 **SNAP 12+ 방식**(PyPI `esa-snappy` 1.1.2 + `snappy-conf` 연동)을 사용합니다.
설치 절차는 [environment_snappy.yml](environment_snappy.yml) 상단 주석 참고.

---

## 2. 아키텍처: 3개의 구성 요소

[SNAP 12+ 설치 문서](<esa-snappy-master/Installation and configuration of the SNAP-Python (esa_snappy) interface (SNAP version 12+).md>)에
따르면 esa_snappy 인터페이스는 세 부분으로 이루어져 있습니다:

1. **SNAP 쪽 Java 모듈** — SNAP-Python 연동 설정을 담당하는 SNAP 플러그인.
   소스: [src/main/java/eu/esa/snap/](esa-snappy-master/src/main/java/eu/esa/snap/) (아래 6.3절)
2. **jpy (Java-Python bridge)** — Python에서 JVM을 호출하고 그 반대도 가능하게 하는 양방향 다리.
   [jpy 프로젝트](https://github.com/jpy-consortium/jpy)가 별도로 개발하며, 빌드된 wheel들이
   [src/main/resources/lib/](esa-snappy-master/src/main/resources/lib/)에 파이썬 버전별(cp37~cp313)·플랫폼별로 동봉됨
3. **Python 패키지 `esa_snappy`** — 다시 두 부분으로 나뉨:
   - jpy 초기화/설정 담당 (기존 snappy에 해당) — [esa_snappy/\_\_init\_\_.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/__init__.py)
   - **SNAPISTA** (SNAP 12 신규): gpt 그래프 실행 지원 — [esa_snappy/snapista/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/)

---

## 3. 두 가지 사용 방식 (이 프로젝트에서 실제로 겪은 차이)

[How to use the SNAP API from Python.md](<esa-snappy-master/How to use the SNAP API from Python.md>)가
설명하는 공식 사용법은 크게 두 갈래입니다.

### 방식 A: GPF 직접 호출 — [prepro.py](prepro.py)가 쓰는 방식

Python 프로세스 안에 SNAP JVM을 띄우고 `GPF.createProduct('연산자이름', 파라미터HashMap, 입력프로덕트)`로
SNAP 연산자를 하나씩 호출합니다 (문서의 "Option A"). 커스텀 numpy 연산이 필요하면
`readPixels()`/`writePixels()`로 밴드를 배열로 읽고 쓸 수 있습니다 (문서의 "Option B").

```python
from esa_snappy import GPF, HashMap, ProductIO

p = ProductIO.readProduct("input.zip")
params = HashMap()
params.put("orbitType", "Sentinel Precise (Auto Download)")
out = GPF.createProduct("Apply-Orbit-File", params, p)
ProductIO.writeProduct(out, "out_path", "GeoTIFF")
```

**한계 (이 프로젝트에서 실제 발생):** 이 방식으로 띄운 SNAP 엔진은 NetBeans 모듈 시스템이
완전히 초기화되지 않아 **DEM 자동 다운로드가 동작하지 않습니다.** Terrain-Flattening /
Terrain-Correction 실행 시 `The DEM 'Copernicus 30m Global DEM (Auto Download)' is not supported`
에러가 나고, 이 에러가 타일 계산 스레드에서 발생하기 때문에 Python 예외로 전파되지 않고
**깨진 GeoTIFF가 조용히 생성**됩니다. 또한 jpy가 Python `int`를 Java `Long`으로 넘기는 문제로
숫자 파라미터는 문자열로 넣어야 합니다 (`params.put("polyDegree", "3")`).

### 방식 B: SNAPISTA로 그래프 조립 → gpt 실행 — [prepro_gpt.py](prepro_gpt.py)가 쓰는 방식

SNAP 12+에 통합된 SNAPISTA([esa_snappy/snapista/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/))로
처리 체인을 **그래프 XML로 조립**한 뒤, SNAP 공식 커맨드라인 처리기 **gpt.exe를 서브프로세스로 실행**합니다.

```python
from esa_snappy.snapista import Graph, Operator

g = Graph()                                   # 내부적으로 PATH에서 gpt.exe를 찾음
g.add_node(Operator("Read", file="input.zip"), node_id="Read")
g.add_node(Operator("Apply-Orbit-File"), node_id="Orbit", source="Read")
g.run()                                       # 그래프를 임시 XML로 저장 후 gpt 실행
```

- [snapista/graph.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/graph.py) —
  `Graph` 클래스. `add_node()`로 XML 노드 추가, `view()`로 그래프 출력, `save_graph()`로 XML 저장,
  `run()`이 gpt를 호출. `list_operators()` / `describe_operators()`로 SNAP 연산자 목록·설명 조회 가능
- [snapista/operator.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/operator.py) —
  `Operator` 클래스. 연산자 이름과 파라미터를 담는 객체. `describe()`로 해당 연산자의 파라미터 문서 출력
- [snapista/operatorparams.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/operatorparams.py) —
  SNAP 레지스트리에서 연산자의 기본 파라미터 값들을 읽어와 dict로 제공
- [snapista/graph_io.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/graph_io.py) —
  `read_file(uri)`: 로컬/URL의 기존 그래프 XML을 읽어 `Graph` 객체로 변환 (SNAP Desktop
  Graph Builder에서 만든 XML 재사용 가능)
- [snapista/target_band.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/target_band.py),
  [target_band_descriptors.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/target_band_descriptors.py) —
  BandMaths 연산자용 타깃 밴드 정의 헬퍼
- [snapista/binning/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/binning/) —
  Binning 연산자(주로 해색/광학 L3 합성)용 헬퍼. `BinningVariable(s)`, `BinningBand`,
  `BinningOutputBands`, `Aggregators` 클래스를 제공하며 집계자 종류는 AVG /
  AVG_OUTLIER / MIN_MAX / ON_MAX_SET / PERCENTILE / SUM
  ([binning/\_\_init\_\_.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/binning/__init__.py) 참고)
- [snapista/demo/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/demo/) —
  실행 가능한 주피터 노트북 데모 2개:
  [snapista-demo-bandmaths.ipynb](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/demo/snapista-demo-bandmaths.ipynb),
  [snapista-demo-binning.ipynb](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/demo/snapista-demo-binning.ipynb)
  (입력용 Sentinel-3 OLCI 샘플 데이터는 [demo/data/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/demo/data/))

**장점:** gpt는 SNAP Desktop의 Graph Builder와 동일한 공식 실행 경로라서 DEM/궤도 파일
자동 다운로드 등 모든 모듈이 정상 동작합니다. 무거운 체인(SLC 전처리 등)에 권장되는 방식입니다.

> 요약: 방식 A는 "Python 안에서 SNAP을 실행", 방식 B는 "Python으로 그래프를 설계하고
> 실행은 gpt에 위임". 이 프로젝트는 DEM 문제 때문에 방식 B로 전환했습니다.

---

## 4. 설치와 설정 (SNAP 12+ 기준)

출처: [Installation and configuration … (SNAP version 12+).md](<esa-snappy-master/Installation and configuration of the SNAP-Python (esa_snappy) interface (SNAP version 12+).md>)

1. Python 3.9~3.13 준비 (Anaconda/Miniconda **권장**, python.org도 가능, 시스템 파이썬은 비권장)
2. `pip install esa-snappy` — PyPI에서 파이썬 패키지 설치
   (이 프로젝트: [environment_snappy.yml](environment_snappy.yml)의 pip 섹션에 포함)
3. SNAP 설치 폴더 `bin`에서 `snappy-conf <python.exe 경로>` 실행 — jpy 바이너리를 풀고
   설정 파일을 생성해 SNAP과 연결
   (이 프로젝트: `"C:\Program Files\snap\bin\snappy-conf.bat" F:\envs\s1_snappy\python.exe` 실행함)
4. 확인: `python -c "import esa_snappy"` 가 에러 없이 통과하면 성공
   (SNAP의 INFO/SLF4J 경고 메시지는 정상)

추가 팁 (같은 문서):

- **메모리 설정**: `site-packages/esa_snappy/esa_snappy.ini`의 `java_max_mem`을 시스템 RAM의
  70~80%로 설정 권장 (이 환경: `F:\envs\s1_snappy\Lib\site-packages\esa_snappy\esa_snappy.ini`에 22G로 설정됨)
- **다른 파이썬으로 변경**: pip install + snappy-conf를 그 파이썬으로 다시 실행하면 됨
- **트러블슈팅**: `esa_snappy` 설치 폴더의 `snappyutil.log`,
  SNAP 로그 `<홈>\.snap\var\log\messages.log`, [SNAP 포럼](https://forum.step.esa.int/) 확인
- `snappy-conf`가 끝나고 프롬프트로 안 돌아오면 CTRL+C 후 abort 질문에 'n'

설정 스크립트 원본(참고용):

- Windows: [src/main/bin/win64/esa_snappy_conf.bat](esa-snappy-master/src/main/bin/win64/esa_snappy_conf.bat)
  ([구버전](esa-snappy-master/src/main/bin/win64/esa_snappy_conf_old.bat))
- Linux: [src/main/bin/linux/esa_snappy_conf.bash](esa-snappy-master/src/main/bin/linux/esa_snappy_conf.bash)
  ([구버전](esa-snappy-master/src/main/bin/linux/esa_snappy_conf_old.bash))
- 실제 설정 작업을 수행하는 파이썬 스크립트:
  [esa_snappy/snappyutil.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snappyutil.py)

---

## 5. API 사용법 핵심 정리

출처: [How to use the SNAP API from Python.md](<esa-snappy-master/How to use the SNAP API from Python.md>)

- SNAP의 공식 API 문서는 [SNAP Java API 문서](http://step.esa.int/main/developers/)이며,
  Python에서도 그대로 적용됩니다 (메서드 이름·시그니처 동일)
- **읽기/쓰기**: `ProductIO.readProduct(경로)` / `ProductIO.writeProduct(제품, 경로, 포맷)`
- **Java 객체 다루기**: `p.getBandNames()` 같은 반환값이 Java 배열이면 `list(...)`로,
  Java String류면 `str(...)`로 변환
- **임의의 Java 클래스 import**: `esa_snappy.jpy.get_type('org.esa.snap....')`
  — 자주 쓰는 클래스(`Product`, `Band`, `GPF`, `ProductIO`, `HashMap`, `File` 등)는
  `esa_snappy`가 이미 임포트해 둠 (문서 하단에 전체 목록 있음)
- **진행률 표시**: `PrintWriterProgressMonitor`를 만들어 `GPF.writeProduct(...)`에 넘기면
  커맨드라인에 진행률 출력 가능
- **성능**: 대량 쓰기는 `ProductIO.writeProduct`보다 `GPF.writeProduct`가 빠름

---

## 6. esa-snappy-master 폴더 전체 레퍼런스

### 6.1 루트 문서

| 파일 | 내용 |
| --- | --- |
| [README.md](esa-snappy-master/README.md) | 저장소 소개. esa_snappy의 목적(SNAP Java API 사용 + Python 연산자 플러그인 개발)과 공식 위키 링크 모음 |
| [Installation and configuration … (SNAP version 12+).md](<esa-snappy-master/Installation and configuration of the SNAP-Python (esa_snappy) interface (SNAP version 12+).md>) | **현재 기준 문서.** SNAP 12+ 설치/설정/테스트/트러블슈팅. SNAPISTA 통합 설명 포함 |
| [Configure Python … (esa_snappy) interface (SNAP version 10+).md](<esa-snappy-master/Configure Python to use the SNAP-Python (esa_snappy) interface (SNAP version 10+).md>) | SNAP 10~11용 설정 문서. SNAP 11에서 Plugin Manager로 수동 설치해야 했던 제약 설명 |
| [Configure Python … (snappy) interface (SNAP versions <= 9).md](<esa-snappy-master/Configure Python to use the SNAP-Python (snappy) interface (SNAP versions -= 9).md>) | 구버전(≤9) `snappy` 설정 문서 (역사 참고용) |
| [How to use the SNAP API from Python.md](<esa-snappy-master/How to use the SNAP API from Python.md>) | **API 사용법 본문.** 읽기/쓰기, GPF 연산자 호출, numpy 커스텀 연산, jpy 클래스 import 목록 |
| [PY01_Sentinel1Processing_snappy.pdf](esa-snappy-master/PY01_Sentinel1Processing_snappy.pdf) | 튜토리얼 PDF **"SENTINEL-1 PROCESSING USING SNAPPY"** (PDF 본문에서 제목 확인) — 이 프로젝트(S1 SLC 전처리)와 가장 직접 관련된 실습 자료 |
| [preprints201911.0393.v1.pdf](esa-snappy-master/preprints201911.0393.v1.pdf) | 학술 프리프린트 (Mandal, Vaka, Bhogapurapu, Vanama, Kumar, Rao, Bhattacharya — IIT Bombay Microwave Remote Sensing Lab, 2019). SNAP에서의 **Sentinel-1 SLC 전처리 워크플로**를 다루는 논문으로, snappy 기반 S1 처리의 배경 문헌 |
| [LICENSE.txt](esa-snappy-master/LICENSE.txt) | GPL v3 라이선스 전문 |
| [pom.xml](esa-snappy-master/pom.xml) | Maven 빌드 설정. 모듈 정보(`eu.esa.snap:esa-snappy`, NBM 패키징)와 SNAP 의존성(ceres-core, snap-core, snap-gpf 등) 정의 |
| [.gitlab-ci.yml](esa-snappy-master/.gitlab-ci.yml) | GitLab CI 파이프라인 설정 (빌드 자동화) |
| [.gitignore](esa-snappy-master/.gitignore) | git 제외 목록 |

### 6.2 Python 패키지 소스 — [src/main/resources/esa_snappy/](esa-snappy-master/src/main/resources/esa_snappy/)

PyPI에 올라가는 `esa-snappy` 패키지의 원본입니다. 우리 환경의
`F:\envs\s1_snappy\Lib\site-packages\esa_snappy`에 설치된 것과 같은 코드입니다.

| 경로 | 내용 |
| --- | --- |
| [pyproject.toml](esa-snappy-master/src/main/resources/esa_snappy/pyproject.toml) | 패키지 메타데이터/빌드 설정 |
| [README.md](esa-snappy-master/src/main/resources/esa_snappy/README.md) | PyPI 패키지 설명 |
| [howto_package_for_pypi.txt](esa-snappy-master/src/main/resources/esa_snappy/howto_package_for_pypi.txt) | 개발자용: PyPI 배포 절차 메모 |
| [esa_snappy/\_\_init\_\_.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/__init__.py) | **패키지 심장부.** `esa_snappy.ini` 읽기 → SNAP 설치 폴더에서 jar 수집 → JVM 생성 → 자주 쓰는 Java 클래스(Product, GPF, ProductIO 등) 사전 import → SNAP Engine 시작 |
| [esa_snappy/snappyutil.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snappyutil.py) | `snappy-conf`가 실행하는 설정 스크립트. 동작: ① `lib/`에서 현재 OS·파이썬 버전에 맞는 jpy wheel을 찾아 압축 해제 ② `jpyutil`을 불러 Java/Python 양쪽 설정 파일(`jpyconfig.properties`, `jpyconfig.py`) 생성 ③ `import esa_snappy`와 `import snapista`가 되는지 자가 검증(실패 시 에러코드 30/40). 옵션: `--snap_home`, `--java_home`, `--jvm_max_mem`(기본 3G), `--req_arch`, `--force` 등 |
| [esa_snappy/snapista/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/snapista/) | **SNAPISTA** — 3절(방식 B)에서 파일별로 상세 설명 |
| [esa_snappy/examples/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/) | 예제 스크립트 8개 (아래 6.2.1) |
| [esa_snappy/tests/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/tests/) | unittest 기반 패키지 자체 테스트. 셋 다 `testdata/MER_FRS_L1B_SUBSET.dim`을 입력으로 사용: [test_snappy_product.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/tests/test_snappy_product.py)(Product 읽기/밴드/지오코딩 API), [test_snappy_mem.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/tests/test_snappy_mem.py)(메모리 사용), [test_snappy_perf.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/tests/test_snappy_perf.py)(픽셀 읽기 성능) |
| [esa_snappy/testdata/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/testdata/) | 예제/테스트 입력용 MERIS L1b 샘플 프로덕트(`MER_FRS_L1B_SUBSET.dim` + `.data` 폴더, BEAM-DIMAP 포맷) |

#### 6.2.1 예제 스크립트 — [examples/](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/)

실행법: `python snappy_ndvi.py ../testdata/MER_FRS_L1B_SUBSET.dim`

| 예제 | 내용 (코드 확인 기준) |
| --- | --- |
| [snappy_ndvi.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_ndvi.py) | MERIS L1b의 `radiance_7`/`radiance_10` 밴드를 **한 줄(row)씩** `readPixels()`로 numpy 배열에 읽어 NDVI를 계산하고 `writePixels()`로 새 프로덕트에 기록. `FlagCoding`으로 NDVI_LOW/HIGH 플래그 밴드 정의, `ProductUtils.copyGeoCoding()`으로 좌표계 복사, BEAM-DIMAP으로 출력. "커스텀 numpy 연산"의 기본형 |
| [snappy_ndvi_with_masks.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_ndvi_with_masks.py) | 위와 같되 `readValidMask()`로 유효 픽셀 마스크를 읽어 numpy **masked array**로 계산하고, 무효 픽셀은 NaN으로 채움 (`setNoDataValue(nan)` + `setNoDataValueUsed(True)`) |
| [snappy_bmaths.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_bmaths.py) | `BandMathsOp$BandDescriptor` 배열에 밴드 수식(예: NDVI 식)을 담아 `GPF.createProduct('BandMaths', ...)` 호출 — [prepro.py](prepro.py)의 `linear_to_db()`가 정확히 이 패턴 |
| [snappy_subset.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_subset.py) | `jpy.get_type('...SubsetOp')`으로 연산자 클래스를 직접 가져와 WKT POLYGON으로 `setGeoRegion()` — AOI 공간 서브셋. 연산자를 GPF 대신 **Java 객체로 직접 다루는** 예시이기도 함 |
| [snappy_geo_roi.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_geo_roi.py) | WKT 기하 → `PlainFeatureFactory`/`SimpleFeatureBuilder`로 피처 생성 → `FeatureUtils.clipFeatureCollectionToProductBounds()`로 씬 경계에 클리핑 → `VectorDataNode`로 프로덕트에 추가. 벡터 ROI/마스크 그룹 다루기 |
| [snappy_flh.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_flh.py) | MERIS L2 물 프로덕트의 `reflec_5/7/9` 3개 밴드와 각 밴드의 **분광 파장**(`getSpectralWavelength()`)을 이용해 FLH(형광선 높이)를 계산, GeoTIFF로 출력. 다중 밴드 조합 연산 예시 |
| [snappy_write_image.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_write_image.py) | `Resample` 연산자로 1000×1000 리사이즈 후, `ColorPaletteDef`/`ImageInfo`/`ImageManager`로 컬러 팔레트를 입혀 JAI `filestore`로 PNG 렌더링. 시각화(퀵룩) 생성용 |
| [snappy_reader_writer_formats.py](esa-snappy-master/src/main/resources/esa_snappy/esa_snappy/examples/snappy_reader_writer_formats.py) | `ProductIOPlugInManager`에서 설치된 SNAP의 읽기/쓰기 플러그인 전체를 나열 — `ProductIO.writeProduct()`에 넣을 포맷 이름("GeoTIFF", "BEAM-DIMAP" 등) 확인용 |

### 6.3 Java 모듈 소스 — [src/main/java/eu/esa/snap/](esa-snappy-master/src/main/java/eu/esa/snap/)

SNAP 안에 설치되는 플러그인 쪽 코드입니다. 파이썬 사용자가 직접 만질 일은 없지만,
연동이 내부적으로 어떻게 동작하는지 이해할 때 참고합니다.

| 파일 | 역할 |
| --- | --- |
| [snappy/PyBridge.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/PyBridge.java) | **핵심.** Java-Python 다리 수립 담당. 클래스 주석에 따르면: `snappyutil.py`를 적절한 인자로 실행 → snappyutil이 jpy 도구/바이너리를 선택·해제하고 `jpyutil.properties`·`jpyconfig.py` 설정 파일 생성 → jpy의 `PyLib` 클래스가 이 설정을 읽어 **내장 Python 인터프리터를 기동** |
| [snappy/Configurator.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/Configurator.java) / [ConfigurationReport.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/ConfigurationReport.java) | snappy-conf 설정 로직과 결과 보고 |
| [snappy/EsaSnappyArgsProcessor.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/EsaSnappyArgsProcessor.java) | `snappy-conf` 커맨드라인 인자 파싱 |
| [main/EsaSnappyConfigurator.java](esa-snappy-master/src/main/java/eu/esa/snap/main/EsaSnappyConfigurator.java) | 설정 진입점(main) |
| [snappy/SnappyConstants.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/SnappyConstants.java) | 상수 정의 |
| [snappy/gpf/PyOperator.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/gpf/PyOperator.java), [PyOperatorSpi.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/gpf/PyOperatorSpi.java), [PyOperatorDelegate.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/gpf/PyOperatorDelegate.java) | **Python으로 SNAP 연산자 플러그인을 만들 때** 그 파이썬 코드를 SNAP GPF에 연결해주는 어댑터 (gpt/Desktop에서 파이썬 연산자를 노드로 실행 가능하게 함) |
| [snappy/desktop/](esa-snappy-master/src/main/java/eu/esa/snap/snappy/desktop/) | SNAP Desktop의 Tools > Options에 나오는 esa_snappy 설정 UI 패널 |
| [package-info.java](esa-snappy-master/src/main/java/eu/esa/snap/snappy/package-info.java) ([gpf](esa-snappy-master/src/main/java/eu/esa/snap/snappy/gpf/package-info.java)) | 패키지 문서 주석 |

기타 리소스:

- [src/main/resources/lib/](esa-snappy-master/src/main/resources/lib/) — jpy 1.0.0 wheel 30여 개
  (cp37~cp313 × win/linux/mac). `snappy-conf`가 파이썬 버전에 맞는 것을 골라 설치
- [src/main/resources/layer.xml](esa-snappy-master/src/main/resources/layer.xml), [src/main/nbm/manifest.mf](esa-snappy-master/src/main/nbm/manifest.mf) — NetBeans 모듈(NBM) 등록 정보
- [src/main/resources/META-INF/services/org.esa.snap.core.gpf.OperatorSpi](esa-snappy-master/src/main/resources/META-INF/services/org.esa.snap.core.gpf.OperatorSpi) — PyOperator를 SNAP 연산자 레지스트리에 등록
- [src/main/resources/eu/esa/snap/snappy/get_site_packages_dir.py](esa-snappy-master/src/main/resources/eu/esa/snap/snappy/get_site_packages_dir.py) — 설정 과정에서 파이썬의 site-packages 위치를 알아내는 헬퍼
- [src/main/resources/eu/esa/snap/snappy/desktop/](esa-snappy-master/src/main/resources/eu/esa/snap/snappy/desktop/) — 설정 UI 아이콘(png)

### 6.4 테스트 — [src/test/](esa-snappy-master/src/test/)

| 경로 | 내용 |
| --- | --- |
| [java/eu/esa/snap/snappy/PyBridgeTest.java](esa-snappy-master/src/test/java/eu/esa/snap/snappy/PyBridgeTest.java) 외 | Java 모듈 단위 테스트 (설정, 인자 처리, PyOperator) |
| [resources/snappy_ndvi_op/](esa-snappy-master/src/test/resources/snappy_ndvi_op/) | **Python 연산자 플러그인의 완전한 예시.** [ndvi_op.py](esa-snappy-master/src/test/resources/snappy_ndvi_op/ndvi_op.py): `NdviOp` 클래스가 `initialize(context)`에서 `context.getSourceProduct()`/`getParameter()`로 입력·파라미터를 받아 타깃 프로덕트 구성. [ndvi_op-info.xml](esa-snappy-master/src/test/resources/snappy_ndvi_op/ndvi_op-info.xml): 연산자 이름/별칭(`py_ndvi_op`), `operatorClass`(= PyOperator), 소스 프로덕트, 파라미터(이름·타입·기본값·설명)를 선언 — **이 XML로 SNAP Desktop GUI와 gpt 커맨드라인 도움말이 자동 생성됨**. Python으로 SNAP 연산자를 만들 때 이 구조를 그대로 따라하면 됨 |
| [resources/snappy_dummy_op/](esa-snappy-master/src/test/resources/snappy_dummy_op/) | 최소 구성의 더미 연산자 + [그래프 XML에서 파이썬 연산자를 노드로 쓰는 예시](esa-snappy-master/src/test/resources/snappy_dummy_op/dummy_py_op_graph.xml) |

---

## 7. 이 프로젝트에서의 적용 요약

| 항목 | 내용 |
| --- | --- |
| conda 환경 | `s1_snappy` ([environment_snappy.yml](environment_snappy.yml)) — Python 3.11 + esa-snappy 1.1.2 |
| SNAP 연동 | `C:\Program Files\snap\bin\snappy-conf.bat F:\envs\s1_snappy\python.exe` 실행 완료 |
| [prepro.py](prepro.py) | 방식 A(GPF 직접 호출). Split→Merge 포함 전체 체인 구현. **DEM 자동 다운로드 불가 문제로 Terrain 단계에서 산출물이 깨짐** — 학습/참고용으로 유지 |
| [prepro_gpt.py](prepro_gpt.py) | 방식 B(SNAPISTA→gpt). 현재 사용하는 실행 경로. gpt에서는 TOPSAR-Deburst가 서브스와스 3개를 한 번에 병합하므로 Split/Merge 불필요 |
| 알려진 함정 | ① 방식 A에서 DEM "not supported" — gpt로 우회 ② 숫자 파라미터는 문자열로 전달 ③ 에러가 나도 깨진 GeoTIFF가 생길 수 있으니 산출물을 rasterio 등으로 열어 검증할 것 |
