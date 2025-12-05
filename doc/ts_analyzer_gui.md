# TS Analyzer GUI (`ts_analyzer_gui.py`)

## 개요
`AnalyzerGUI` 클래스는 OpenCV를 사용하여 TS 스트림 분석 결과를 시각화하고 사용자와 상호작용합니다.
Tektronix MTS430과 같은 전문 계측기의 UX를 지향합니다.

## 화면 구성

### 1. Toolbar (상단)
- **File**: 파일 열기 / 종료. (최근 파일 목록 지원)
- **Filters**: `PAT`, `PMT`, `Video`, `Audio`, `PCR`, `PTS`, `DTS` 패킷만 필터링하여 볼 수 있는 토글 버튼.
- **BScan**: 전체 파일 스캔 (Background Scan) 제어.
- **Playback Controls**: `<<`, `>>`, `Play/Pause`, `Stop`.
- **Ext Play**: 외부 플레이어(`play_ts_opencv.py`) 실행.

### 2. PSI / PMT View (좌측)
- **PSI Information (상단)**: TS 스트림 내의 주요 PSI 테이블 구조를 트리 형태로 표시합니다.
  - **PSI Tables**: `PAT`, `CAT`, `NIT`, `SDT`, `EIT`, `TDT` 등 감지된 테이블 목록.
  - **PAT**: 하위에 Program 목록 표시. Program 클릭 시 해당 PMT로 이동.
  - **Interaction**: 테이블 항목 클릭 시 해당 PID 선택(Raw View), Program 클릭 시 PMT View 연동.
- **PMT View (하단)**: 선택된 Program의 상세 구조(Elementary Streams)를 표시합니다.
  - **PID 항목** 클릭: 해당 PID를 단독으로 선택합니다. 이때 툴바의 **Global Filter는 모두 해제**되어(Exclusive Mode), 오직 선택한 PID만 분석합니다.
- **Auto Selection**: 파일 로드 시, **NIT(Program 0)를 제외한 첫 번째 유효한 Program**을 자동으로 찾아 선택하고 PMT 정보를 보여줍니다.

### 3. Detail View (우측 상단)
- 현재 패킷의 TS Header 상세 정보 표시.
- **Flags**: TEI, PUSI, Priority, Scrambling Control.
- **Adaptation**: Adaptation Field Control, Continuity Counter.
- **Type**: Stream Type (Video, Audio, etc.)
- **ETR-290 Check**: PAT/PMT 등 테이블 섹션의 CRC32, Table ID 유효성을 실시간으로 검증하여 Pass/Fail/Incomplete 상태를 표시합니다.

### 4. PES View (우측 중단)
- **PES Header Analysis**:
  - `PUSI=1`인 경우 PES 헤더를 파싱하여 Stream ID, Length, PTS, DTS 표시.
  - 오디오/비디오 스트림 종류 자동 식별.
- **Smart Navigation (Jump)**:
  - `◀`, `▶` (Packet), `⏪`, `⏩` (PES Start) 버튼 제공.
  - **Back-tracking Optimization**: 대용량 파일(1GB+)에서도 UI 멈춤 없이 PES Start를 찾을 수 있도록 탐색 범위(Limit)가 최적화되었습니다.
  - **Filter Search Mode**: 툴바 필터가 켜져 있거나 특정 PID가 선택된 경우, **고속 재생(x50)**을 통해 조건에 맞는 패킷을 자동으로 찾아냅니다.
- **Continuation Info**:
  - Multi-packet PES인 경우, 시퀀스 번호 및 누적 바이트 수 표시.

### 5. Hex View (우측 하단)
- 현재 패킷(188바이트)의 Hex Dump 및 ASCII 표시.
- **Interactive Highlight**: 상단 Detail View 등에서 특정 필드를 클릭하면, 해당 바이트 영역이 Hex View에서 하이라이트됩니다.
- **Performance**: 재생 중에는 렌더링을 생략하여 성능을 확보합니다.

## 내부 로직 및 최신 변경 사항 (Updates)

### 2025-11-30 업데이트
1.  **Selection & Filtering Behavior (UI UX 개선)**:
    *   **Exclusive Selection (Tree)**: 좌측 트리에서 특정 PID를 클릭하면, "그 PID만 보겠다"는 의도로 간주하여 툴바의 Global Filter(Video, Audio 등)를 모두 끕니다.
    *   **Inclusive Filtering (Toolbar)**: 툴바의 `Video` 버튼 등을 누르면, 해당 타입의 모든 패킷을 볼 수 있도록 필터가 활성화됩니다.
    *   **Auto Focus**: 프로그램 선택 시 PMT PID 자동 선택, Video 필터 클릭 시 첫 번째 Video PID 자동 선택 등 편의성 강화.

2.  **Robust File Loading**:
    *   **`_initialize_file` 메서드 도입**: 파일 로드, 파서 초기화, 빠른 스캔, 자동 선택 로직을 하나의 메서드로 통합하여 일관성을 확보했습니다.
    *   **Tkinter Dialog Fix**: 파일 열기 시 메인 루프(OpenCV)가 멈추거나 다이얼로그 잔상이 남는 문제를 해결 (`root.update()`, `withdraw()` 활용).
    *   **Program 0 (NIT) Handling**: PAT 파싱 시 Program 0가 누락되던 버그를 수정하고, 초기 로딩 시에는 가급적 실제 방송 프로그램(Prog != 0)을 우선 보여주도록 개선했습니다.

3.  **Parsing Engine Fixes**:
    *   **PAT Loop Bug**: PAT 섹션 파싱 시 `while` 루프 조건 오류로 인해 일부 프로그램이 누락되던 문제를 수정했습니다.
    *   **CRC32/Table Check**: ETR-290 기준에 맞춘 CRC32 검증 및 Table ID 확인 로직이 추가되었습니다.

## 단축키
- **Space**: Play / Pause
- **ESC** / **q**: 종료
- **p**: 외부 플레이어 실행
- **<**, **>**: 이전/다음 패킷 이동 (Comma/Period)
