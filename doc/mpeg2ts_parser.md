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
    ├── mpeg2ts_parser.md    # 프로젝트 문서 (Main)
    └── pcr_info.md          # PCR 기술 문서
```

### 🧩 모듈별 상세 분석

#### 1. `ts_analyzer_gui.py` (Controller & View)
- **역할**: 프로그램의 메인 진입점이며, OpenCV 창을 생성하고 메인 루프를 실행합니다.
- **주요 기능**:
  - **화면 레이아웃**: 5분할 대시보드 (PAT, PMT, Detail, PES, Hex) 렌더링.
  - **이벤트 처리**: 키보드/마우스 이벤트 처리, 필터 토글, 네비게이션 제어.
  - **Smart Search Engine**: 단순 Seek가 아닌, 재생(Playback) 기반의 고속 필터링 검색 엔진 탑재.
  - **연동**: `TSParser`, `TSScanner`, `UIManager` 인스턴스를 생성하고 조율.

#### 2. `ts_parser_core.py` (Core Logic)
- **역할**: TS 파일 입출력 및 바이트 단위 파싱을 담당하는 핵심 엔진입니다.
- **주요 기능**:
  - **Packet Parsing**: 188바이트 패킷 헤더(PID, PUSI, CC 등) 파싱.
  - **Deep Analysis**: ISO/IEC 13818-1 표준에 의거한 Adaptation Field, PCR, ES Info 파싱.
  - **PES Parsing**: PES 헤더, PTS/DTS 타임스탬프, Stream ID 추출.

#### 3. `ts_scanner.py` (Background Service)
- **역할**: GUI 동작에 영향을 주지 않고 별도 스레드에서 파일 전체를 정밀 스캔합니다.
- **주요 기능**:
  - **Full Scan**: 파일의 처음부터 끝까지 읽으며 PID별 패킷 카운트 누적.
  - **Reporting**: 분석이 완료되면 Markdown 형식의 리포트 파일 생성 (`output/` 폴더).

#### 4. `ts_ui_manager.py` (UI Component)
- **역할**: OpenCV 화면 위에 그려지는 UI 요소(버튼, 메뉴, 툴바)를 관리합니다.
- **주요 기능**:
  - **Interactive Toolbar**: Play/Pause 상태 표시, 필터 버튼(Video/Audio/PCR 등) 상태 관리.
  - **Interaction**: 마우스 오버/클릭 이벤트 처리 및 시각적 피드백 제공.

---

## 3. 주요 기능 (Key Features)

### 📊 1. Multi-View Dashboard
OpenCV Canvas에 직접 드로잉하여 빠른 반응속도를 제공합니다.
- **Left Panel (PSI View)**:
  - **PAT View**: 탐지된 Program 목록 표시.
  - **PMT View**: 선택된 Program의 PID 목록 및 Stream Type(Video/Audio/Data) 표시.
- **Right Panel (Packet View)**:
  - **Detail View**: 
    - **ISO 13818-1 Full Spec**: 헤더 플래그, Adaptation Field(Discontinuity, Random Access 등), Private Data 표시.
    - **PCR Display**: Raw Value(42bit)와 초 단위 시간(Seconds)을 한 줄에 통합 표시.
  - **PES View**: 
    - **Navigation**: 이전/다음 PES Start 패킷으로 이동하는 `<` `>` 버튼 제공 (항상 표시).
    - **Info**: Sequence Number, 누적 길이, PTS/DTS(초 단위 환산 포함) 표시.
    - **Layout**: Audio Sync 및 Sequence 정보를 컴팩트하게 배치하여 가독성 확보.
  - **Hex View**: 패킷의 Raw Data를 Hex/ASCII 덤프로 표시 (재생 중 자동 숨김 최적화).

### 🔍 2. Advanced Filtering & Search
2025-11-30 업데이트로 강화된 검색 시스템입니다.
- **Filter Toolbar**:
  - **Toggle Buttons**: `Video`, `Audio`, `PCR`, `PTS`, `DTS` 필터 버튼 제공.
  - **OR Logic**: 여러 필터 동시 선택 시 "OR" 조건으로 동작 (예: Video 또는 PCR 패킷 검색).
  - **Visual Feedback**: 활성화된 필터는 Highlight 처리.
- **Play-while-Filtering (Smart Search)**:
  - **Playback Search**: 필터 활성화 후 탐색 시, 고속 재생(x50) 모드로 전환하여 파일을 스캔.
  - **Auto-Stop**: 필터 조건에 맞는 패킷(예: Video 패킷)을 발견하면 즉시 재생을 멈추고 해당 패킷 표시.
  - **Stream Type Awareness**: ISO 13818-1 Stream Type ID(0x1B, 0x0F 등)를 기반으로 정확한 Video/Audio 패킷 식별.

### 🚀 3. PES Navigation System
- **Video/Audio Support**: Video(무제한 길이 처리) 및 Audio 스트림 모두에 대해 이전/다음 PES 패킷 탐색 지원.
- **Stability**: 초기 PID 선택 시 버튼 반응성 개선 및 검색 중지 로직 최적화.
- **Optimized IO**: 검색 중 파일 I/O 배칭 처리를 통해 UI 응답성 유지.

### 🕵️ 4. Background Analysis (BScan)
- **Non-blocking**: 대용량 파일도 GUI 멈춤 없이 분석 가능.
- **Statistics**: 전체 파일의 PID별 점유율(%) 및 패킷 개수 집계.
- **Report**: 분석 결과는 텍스트 리포트로 자동 저장되어 추후 분석에 활용 가능.

---

## 4. 데이터 흐름 (Data Flow)

1. **초기화**: `AnalyzerGUI` 시작 -> `TSParser`가 파일 로드 -> `quick_scan()`으로 초기 구조 파악.
2. **사용자 탐색 (Manual)**:
   - **Scroll/Button**: 이동 요청 -> `read_packet_at(index)` -> 화면 갱신.
3. **필터 탐색 (Smart Search)**:
   - **Filter On -> Next**: `_handle_playback` 루프 진입 -> 필터 조건 검사(`check_packet_filter`) -> 매칭 시 `playing=False`.
4. **심층 분석 (BScan)**:
   - **BScan Click**: `TSScanner` 스레드 시작 -> 전체 파일 순회 -> `pid_counts` 업데이트.

## 5. 향후 계획 (To-Do)
- [ ] **Section Parsing**: PAT/PMT 외에 SDT, EIT, NIT 등 추가 SI 테이블 파싱.
- [ ] **Video Decode**: `play_ts_opencv.py`를 통합하여 I/P/B 프레임 타입 분석 및 썸네일 표시.
- [ ] **Jitter Analysis**: PCR 간격 및 Jitter 분석 그래프 추가.
