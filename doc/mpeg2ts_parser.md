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
│   ├── ts_analyzer_gui.py   # [Main] GUI 진입점 및 메인 루프
│   ├── ts_parser_core.py    # [Core] TS 패킷 파싱 및 데이터 처리
│   ├── ts_scanner.py        # [Worker] 백그라운드 전체 스캔 및 통계
│   ├── ts_ui_manager.py     # [UI] 버튼, 메뉴, 마우스 이벤트 관리
│   ├── ts_models.py         # [Model] 데이터 구조체 정의 (참조용)
│   └── play_ts_opencv.py    # [Player] 단순 비디오 재생기 (Video Window)
└── doc/
    └── mpeg2ts_parser.md    # 프로젝트 문서
```

### 🧩 모듈별 상세 분석

#### 1. `ts_analyzer_gui.py` (Controller & View)
- **역할**: 프로그램의 메인 진입점이며, OpenCV 창을 생성하고 메인 루프를 실행합니다.
- **주요 기능**:
  - **화면 레이아웃**: 5분할 대시보드 (PAT, PMT, Detail, PES, Hex) 렌더링.
  - **이벤트 처리**: 키보드 단축키 및 마우스 클릭 이벤트를 처리하여 파서 상태 변경.
  - **재생 로직**: `_handle_playback` 메서드에서 재생/일시정지 및 **Smart PES Search** 로직 수행.
  - **연동**: `TSParser`, `TSScanner`, `UIManager` 인스턴스를 생성하고 조율.

#### 2. `ts_parser_core.py` (Core Logic)
- **역할**: TS 파일 입출력 및 바이트 단위 파싱을 담당하는 핵심 엔진입니다.
- **주요 기능**:
  - **Packet Parsing**: 188바이트 패킷 헤더(PID, PUSI, CC 등) 파싱.
  - **PSI Parsing**: PAT(Program Association Table), PMT(Program Map Table) 파싱 및 구조화.
  - **PES Parsing**: PES 헤더 파싱 및 PTS/DTS 타임스탬프 추출.
  - **Thread**: 백그라운드 스캔을 위한 스레딩 지원 (초기 구조 파악용).

#### 3. `ts_scanner.py` (Background Service)
- **역할**: GUI 동작에 영향을 주지 않고 별도 스레드에서 파일 전체를 정밀 스캔합니다.
- **주요 기능**:
  - **Full Scan**: 파일의 처음부터 끝까지 읽으며 PID별 패킷 카운트 누적.
  - **Reporting**: 분석이 완료되면 Markdown 형식의 리포트 파일 생성 (`output/` 폴더).
  - **State Share**: `TSParser` 객체를 공유하여 파싱 로직을 재사용하고 결과를 GUI에 전달.

#### 4. `ts_ui_manager.py` (UI Component)
- **역할**: OpenCV 화면 위에 그려지는 UI 요소(버튼, 메뉴 등)를 관리합니다.
- **주요 기능**:
  - **Widget Drawing**: Toolbar, Button, Dropdown Menu 그리기.
  - **Interaction**: 마우스 오버(Hover), 클릭(Click) 감지 및 콜백 처리.
  - **File Dialog**: Tkinter를 이용한 파일 열기 대화상자 호출.

---

## 3. 주요 기능 (Key Features)

### 📊 1. Multi-View Dashboard
OpenCV Canvas에 직접 드로잉하여 빠른 반응속도를 제공합니다.
- **Left Panel (PSI View)**:
  - **PAT View**: 탐지된 Program 목록 표시.
  - **PMT View**: 선택된 Program의 PID 목록 및 Stream Type(Video/Audio/Data) 표시.
- **Right Panel (Packet View)**:
  - **Detail View**: 현재 패킷의 헤더 플래그(TEI, PUSI, Scrambling, Adaptation) 상세 정보.
  - **PES View**: PES Packet Start 코드 감지, Stream ID, Length, PTS/DTS 정보 표시.
  - **Hex View**: 패킷의 Raw Data를 Hex/ASCII 덤프로 표시 (재생 중 자동 숨김 최적화).

### 🚀 2. Smart PES Navigation
2025-11-30 업데이트로 강화된 탐색 기능입니다.
- **Priority Search (우선순위 탐색)**:
  1. **PMT 선택 PID**: PMT 뷰에서 사용자가 선택한 PID를 최우선으로 추적합니다.
  2. **Current PID**: 선택된 PID가 없으면 현재 패킷의 PID를 기준으로 탐색합니다.
- **Precision Scanning (정밀 검사)**:
  - 고속 탐색(x50 배속) 중에도 `seek`를 사용하지 않고 **모든 패킷을 순차적으로 검사**합니다.
  - 이를 통해 드문드문 존재하는 `PES Start Code (PUSI=1)`를 놓치지 않고 정확히 찾아냅니다.
- **Interactive Controls**: PES 뷰의 `◀`, `▶` 아이콘을 클릭하여 이전/다음 Start 지점으로 즉시 이동.

### 🕵️ 3. Background Analysis (BScan)
- **Non-blocking**: 대용량 파일도 GUI 멈춤 없이 분석 가능.
- **Statistics**: 전체 파일의 PID별 점유율(%) 및 패킷 개수 집계.
- **Report**: 분석 결과는 텍스트 리포트로 자동 저장되어 추후 분석에 활용 가능.

---

## 4. 데이터 흐름 (Data Flow)

1. **초기화**: `AnalyzerGUI` 시작 -> `TSParser`가 파일 로드 -> `TSParser.quick_scan()`으로 앞부분 2만 패킷만 읽어 PAT/PMT 구조 파악.
2. **사용자 탐색**:
   - **Scroll/Button**: 사용자가 패킷 이동 요청 -> `TSParser.read_packet_at(index)`로 해당 위치 패킷 로드.
   - **Render**: 로드된 데이터를 `parse_header`, `parse_pes_header`로 분석하여 화면 갱신.
3. **심층 분석 (BScan)**:
   - 사용자가 **BScan** 버튼 클릭 -> `TSScanner` 스레드 시작.
   - 스레드가 `read(188)`을 반복하며 전체 파일 순회 -> `pid_counts` 업데이트 -> 완료 시 파일 저장.

## 5. 향후 계획 (To-Do)
- [ ] **PCR Analysis**: PCR(Program Clock Reference) PID 추출 및 Jitter/Interval 그래프 시각화.
- [ ] **Section Parsing**: PAT/PMT 외에 SDT, EIT, NIT 등 추가 SI 테이블 파싱.
- [ ] **Video Decode**: `play_ts_opencv.py`를 통합하여 I/P/B 프레임 타입 분석 및 썸네일 표시.
