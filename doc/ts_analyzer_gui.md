# AnalyzerGUI Documentation

## 1. 개요
**AnalyzerGUI** (`scripts/ts_analyzer_gui.py`)는 MPEG2-TS 분석기의 **메인 진입점(Entry Point)**이자 **컨트롤러(Controller)**입니다.
사용자 인터페이스(`UIManager`), 파싱 엔진(`TSParser`), 백그라운드 스캐너(`TSScanner`)를 조율하여 분석 기능을 제공합니다.

## 2. 주요 역할 (Responsibilities)
- **Application Lifecycle**: 프로그램 시작, 메인 루프 실행, 종료 처리 (OpenCV 윈도우 관리).
- **File Loading**: TS 파일 로드 및 각 모듈 초기화 (`load_file`).
- **Data Visualization**: 파싱된 데이터(PAT/PMT, Hex Dump, Header Info)를 화면에 그리는 로직 호출.
    - *Note: 툴바와 메뉴 등 공통 UI 요소는 `UIManager`에 위임.*
- **Playback Control**: 패킷 단위 탐색, 재생/일시정지 로직, PID 필터링 탐색 구현.

## 3. 화면 구성 및 기능

### Tree View (좌측)
- **PAT (Program Association Table)**: 스트림 내의 프로그램 목록을 트리 형태로 표시.
- **PMT (Program Map Table)**: 선택된 프로그램의 Video/Audio 스트림 구성 요소를 표시.
- **인터랙션**: 마우스 오버 시 하이라이트, 클릭 시 해당 Program/PID 선택.

### Detail View (우측 상단)
- **Packet Info**: 현재 패킷 인덱스, PID, CC(Continuity Counter).
- **Header Flags**: TEI(Error), PUSI(Start), Prio, Scrambling Control, Adaptation Field 상태.
- **PID Description**: 선택된 PID의 스트림 타입(예: "Video (H.265)", "Audio (MPEG-1)") 표시.

### PES / Section Analysis (우측 중단) - **[New!]**
선택된 PID가 Elementary Stream(비디오/오디오)인 경우 PES 헤더를 정밀 분석합니다.
- **TS Header Summary**: PUSI, CC, Scram, Adapt 정보를 요약 표시.
- **PES Start / Continuation**:
    - `[PES Start]`: 새로운 PES 패킷의 시작.
    - `[PES Continuation]`: 이전 패킷에서 이어지는 데이터.
- **PES Header Info**:
    - **Stream ID**: Video/Audio/Private Stream 식별.
    - **PES Length**: 패킷 길이 및 `Single Packet`(단독) vs `Multi-Packet`(분할) 여부 판별.
    - **PTS/DTS**: Presentation/Decoding Time Stamp (초 단위 변환 표시).
- **Audio Analysis**:
    - 오디오 스트림의 경우 Payload 내에서 **Sync Word** (`0xFFF...`) 패턴을 검색하여 표시.
    - 분할된 패킷(Multi-Packet)의 예상 소요 패킷 수 추정.

### Hex View (우측 하단)
- **Binary Dump**: 현재 패킷의 188바이트 데이터를 16진수와 ASCII로 실시간 표시.
- **BScan Overlay**: 백그라운드 스캔 실행 시, 이 영역이 **Scan Status View**로 전환되어 진행률(Progress Bar)을 표시.

## 4. 핵심 메서드

### `run()`
- OpenCV 윈도우 생성 및 메인 루프 실행. `draw_layout()` 호출.
- 키보드 입력 및 윈도우 닫힘 감지.

### `load_file(path)`
- 파일 열기 및 모듈 초기화. `quick_scan()` 수행.

### `_step_packet(step)`
- **PID Filtering Seek**: 특정 PID가 선택된 상태라면, 해당 PID가 나올 때까지 패킷을 건너뛰며 탐색.

## 5. 모듈 의존성
- **TSParser**: TS 패킷 파싱 및 데이터 접근.
- **TSScanner**: 백그라운드 전수 검사.
- **UIManager**: 툴바, 메뉴, 마우스 입력 처리 위임.
