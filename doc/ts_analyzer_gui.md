# TS Analyzer GUI (`ts_analyzer_gui.py`)

## 개요
`AnalyzerGUI` 클래스는 OpenCV를 사용하여 TS 스트림 분석 결과를 시각화하고 사용자와 상호작용합니다.
Tektronix MTS430과 같은 전문 계측기의 UX를 지향합니다.

## 화면 구성

### 1. Toolbar (상단)
- **File**: 파일 열기 / 종료.
- **BScan**: 전체 파일 스캔 (Background Scan) 제어.
- **Playback Controls**: `<<`, `>>`, `Play/Pause`, `Stop`.
- **Video Win**: 외부 플레이어(play_ts_opencv.py) 실행.

### 2. PAT / PMT View (좌측)
- **PAT**: Program Association Table 정보 표시. Program 번호 클릭 시 해당 PMT로 이동.
- **PMT**: Program Map Table 정보 표시. Stream Type 및 PID 표시.
- **Interaction**: PID를 클릭하면 해당 PID가 `Selected PID`로 설정되어 필터링 및 하이라이트됨.

### 3. Detail View (우측 상단)
- 현재 패킷의 TS Header 상세 정보 표시.
- **Flags**: TEI, PUSI, Priority, Scrambling Control.
- **Adaptation**: Adaptation Field Control, Continuity Counter.
- **Type**: Stream Type (Video, Audio, etc.)

### 4. PES View (우측 중단)
- **PES Header Analysis**:
  - `PUSI=1`인 경우 PES 헤더를 파싱하여 Stream ID, Length, PTS, DTS 표시.
  - 오디오/비디오 스트림 종류 자동 식별.
- **Smart Navigation (Jump)**:
  - `◀`, `▶` 버튼을 클릭하여 이전/다음 PES Start 패킷으로 **고속 탐색**.
  - 현재 보고 있는 스트림(PID)을 자동으로 추적하여 탐색.
  - 탐색 중에는 `x50` 배속으로 재생되며, Start 패킷 발견 시 자동 정지.
- **Continuation Info**:
  - Multi-packet PES인 경우, 부모 PES Start 패킷의 위치(Sequence) 및 진행률(%) 표시.

### 5. Hex View (우측 하단)
- 현재 패킷(188바이트)의 Hex Dump 및 ASCII 표시.
- **최적화**: 재생/탐색 중(`Playing` 상태)일 때는 렌더링을 생략하여 성능을 확보합니다.

## 내부 로직

### Playback & Navigation
- **`_handle_playback`**: 메인 루프에서 호출되며, 재생 속도(`speed`)에 따라 패킷 인덱스를 조절합니다.
  - **PES Search Mode**: 탐색 모드일 때는 단순히 인덱스를 건너뛰지 않고, 이동 경로상의 모든 패킷을 검사하여 `PID`와 `PUSI` 조건을 만족하는지 확인합니다. 이를 통해 고속 이동 중에도 정확한 패킷에서 멈출 수 있습니다.

### Rendering
- **`UIManager`**: 버튼, 메뉴 등 공통 UI 요소의 그리기와 이벤트 처리를 담당합니다.
- **`update_packet_view`**: 현재 인덱스의 패킷을 읽고(`parser.read_packet_at`), 각 뷰(`_draw_*`)를 갱신합니다.

## 단축키
- **Space**: Play / Pause
- **ESC**: 종료
