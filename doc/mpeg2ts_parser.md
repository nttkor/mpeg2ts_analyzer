# MPEG2-TS Parser Project Analysis

## 1. 개요 (Overview)
본 프로젝트는 **Python**과 **OpenCV**를 기반으로 한 **MPEG2-TS (Transport Stream) 분석기**입니다.  
방송/통신 분야에서 사용되는 TS 스트림의 구조를 시각적으로 분석하고, 개별 패킷 단위의 상세 정보를 제공합니다.  
Tektronix MTS430과 같은 전문 계측기의 UX를 지향하여 직관적인 **GUI**와 **고속 탐색** 기능을 제공합니다.

## 2. 시스템 아키텍처 (Architecture)

프로젝트는 **MVC (Model-View-Controller)** 패턴과 유사한 구조로 모듈화되어 있습니다.

### 📁 Directory Structure
```
mpeg2TS/
├── scripts/
│   ├── ts_analyzer_gui.py   # [Main] GUI 진입점 및 메인 루프 (Controller)
│   ├── ts_parser_core.py    # [Core] TS 패킷 파싱 및 데이터 처리 (Model)
│   ├── ts_scanner.py        # [Worker] 백그라운드 전체 스캔 및 통계
│   ├── ts_ui_manager.py     # [UI] 버튼, 메뉴, 마우스 이벤트 관리 (View Helper)
│   ├── ts_models.py         # [Model] 데이터 구조체 정의 (Packet, PSI, PES)
│   ├── zitter_measurement.py # [Analysis] PCR Jitter 분석 모듈
│   ├── ts_etr290_analyzer.py # [Analysis] ETR-290 Priority 1/2 체크
│   └── play_ts_opencv.py    # [Player] 단순 비디오 재생기
└── doc/
    ├── mpeg2ts_parser.md    # 프로젝트 문서 (Main)
    ├── ts_analyzer_gui.md   # GUI 매뉴얼
    └── class_plan.md        # 클래스 구조도
```

### 🧩 모듈별 상세 분석

#### 1. `ts_analyzer_gui.py` (Controller & View)
- **역할**: 프로그램의 메인 진입점. OpenCV 창 생성, 메인 루프 실행, 사용자 입력 처리.
- **개선사항 (2025-11-30)**:
  - **`_initialize_file`**: 파일 로드 및 초기화 로직 통합.
  - **Tkinter Interop**: 파일 다이얼로그와 OpenCV 메인 루프 간의 충돌 방지 처리.
  - **Smart Filtering**: Tree 선택(Exclusive)과 Toolbar 필터(Inclusive)의 동작 구분.

#### 2. `ts_parser_core.py` (Core Logic)
- **역할**: TS 파일 입출력 및 바이트 단위 파싱.
- **주요 기능**:
  - **PAT/PMT Parsing**: `_parse_pat`, `_parse_pmt` 메서드를 통해 PSI 테이블 구조 분석.
  - **Bug Fixes**: 
    - PAT 파싱 루프 조건 수정 (마지막 프로그램 누락 방지).
    - Program 0 (NIT) 정상 인식 처리.
  - **ETR-290 Support**: CRC32 계산 및 Table ID 검증 기능 내장.

#### 3. `ts_scanner.py` (Background Service)
- **역할**: GUI 동작에 영향을 주지 않고 별도 스레드에서 파일 전체를 정밀 스캔.
- **기능**: 전체 패킷 카운팅, PID별 점유율 계산, 리포트 생성.

---

## 3. 주요 기능 (Key Features)

### 📊 1. Multi-View Dashboard
- **PSI View**: PAT(Program 목록)와 PMT(Stream 구성)를 계층적으로 보여줍니다. Program 0(NIT)도 지원합니다.
- **Detail/Hex View**: 헤더 플래그, Adaptation Field, 188바이트 Hex Dump를 제공하며, 클릭 시 상호 하이라이트됩니다.

### 🔍 2. Advanced Filtering & Search
- **Smart Search**: 필터(Video/Audio/PCR 등)를 켜고 탐색하면, 해당 조건에 맞는 패킷을 고속으로 찾아냅니다.
- **Auto-Focus**: 파일을 열면 자동으로 첫 번째 유효한 방송 프로그램(Program != 0)을 찾아 PMT 정보를 보여줍니다.

### 🚀 3. PES Navigation
- **Back-tracking**: PES 헤더(Start Code)를 찾기 위해 역방향 탐색을 지원하며, 대용량 파일에서도 응답성을 유지하도록 탐색 깊이를 최적화했습니다.

---

## 4. 최신 업데이트 (Updates)
- **2025-11-30**:
  - **PAT Parsing Fix**: PAT 파싱 시 일부 프로그램이 누락되거나 Program 0가 무시되던 버그 수정.
  - **Refactoring**: `AnalyzerGUI`의 초기화 로직을 `_initialize_file`로 통합하여 코드 중복 제거.
  - **UX Improvement**: PAT/PMT 트리 선택과 툴바 필터 버튼 간의 동작 로직 정립 (Exclusive vs Inclusive).
  - **Stability**: 파일 열기 시 팝업 잔상 문제 해결 및 예외 처리 강화.

- **2025-12-01**:
  - **ETR-290**: Priority 1, 2 항목 정밀 에러 체크 및 통계 모듈 통합.
