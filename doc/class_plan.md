# MPEG2-TS Class Architecture & Models

## 1. 개요
이 문서는 MPEG2-TS 분석기의 데이터 모델링 및 객체 지향 구조를 설명합니다.
기존의 함수 위주 파싱 로직을 **데이터 모델(Model)** 클래스로 캡슐화하여, `ts_parser_core.py`와 `ts_analyzer_gui.py`에서 공통으로 사용합니다.

## 2. 파일 구조
```text
scripts/
├── ts_models.py          # [Implemented] TS 데이터 모델 클래스 (Packet, PSI, PES)
├── ts_parser_core.py     # [Core] 모델 클래스를 활용한 파싱 엔진
├── ts_analyzer_gui.py    # [View] 모델 데이터를 시각화 (Controller)
├── ts_ui_manager.py      # [View Helper] UI 그리기 및 이벤트 위임
├── ts_scanner.py         # [Worker] 백그라운드 스캔 스레드
└── ts_etr290_analyzer.py # [Analysis] ETR-290 규격 검증
```

## 3. 주요 클래스 구조

### A. `AnalyzerGUI` (in `ts_analyzer_gui.py`)
- **역할**: 애플리케이션의 메인 컨트롤러.
- **주요 메서드**:
    - `run()`: 메인 루프 실행. 초기 파일이 있으면 `_initialize_file()` 호출.
    - `_initialize_file()`: **[Refactored]** 파일 로드 후 파서 초기화, 스캔, 필터 리셋, 자동 선택(Auto Select)을 수행하는 통합 메서드.
    - `_open_file(path)`: 파일 다이얼로그 처리 후 `_initialize_file()` 호출.
    - `_mouse_cb(...)`: 마우스 이벤트 처리 및 `UIManager`로 위임.
    - `_draw_psi_view(...)`: **[New]** 좌측 상단에 PSI 테이블(PAT, CAT, NIT...) 및 Program 목록 표시.
    - `_draw_pmt_view(...)`: 좌측 하단에 선택된 Program의 PMT(Elementary Stream) 상세 표시.

### B. `TSParser` (in `ts_parser_core.py`)
- **역할**: 파일 I/O 및 패킷 파싱 핵심 로직.
- **주요 메서드**:
    - `read_packet_at(idx)`: 특정 인덱스의 패킷 읽기.
    - `_parse_pat(...)`: **[Fixed]** PAT 섹션 파싱 (Loop 조건 수정됨).
    - `_parse_pmt(...)`: PMT 섹션 파싱 및 스트림 정보 추출.
    - `parse_pes_header(...)`: PES 헤더 및 타임스탬프(PTS/DTS) 파싱.

### C. `TSPacket` (in `ts_models.py`)
- **역할**: 188바이트 TS 패킷의 헤더 파싱 및 Payload 추출.
- **속성**: `pid`, `pusi`, `tei`, `cc`, `adapt`, `payload`.

### D. PSI Models (in `ts_models.py`)
- **`PSISection`**: 테이블 섹션 공통 헤더.
- **`PATSection`**: Program Number -> PMT PID 매핑.
- **`PMTSection`**: Elementary Stream PID 및 Type 정보.

## 4. 데이터 흐름 (Data Flow)
1. **Init**: `AnalyzerGUI` 시작 -> `_initialize_file()` -> `TSParser` 생성 -> `quick_scan()` -> 첫 번째 Program 자동 선택.
2. **Event**: 사용자 클릭 -> `UIManager` or `_mouse_cb` -> 상태 변경 (`selected_pid`, `active_filters`).
3. **Render**: `run()` Loop -> `update_packet_view()` -> `TSParser.read_packet_at()` -> `_draw_*` 메서드가 화면 갱신.

## 5. 완료된 작업 (Completed)
- **Model Integration**: `TSPacket`, `PSISection` 등 모델 클래스 적용 완료.
- **UI Refactoring**: `UIManager` 분리 및 `_initialize_file` 통합 완료.
- **Bug Fixes**: PAT 파싱 루프 오류 수정, Program 0(NIT) 처리 추가.
- **Performance**: Back-tracking 탐색 제한 최적화.
- **PSI View**: GUI 좌측 상단을 PSI Information View로 업그레이드 (PSI Table List 표시).
- **Report**: BScan 리포트 PSI 트리 구조 개선.

## 6. 향후 계획: Unified PSI Tree View (Unified Window)
현재 분리된 `PSI View` (좌측 상단)와 `PMT View` (좌측 하단)를 **하나의 통합된 트리 뷰(Tree View)** 창으로 합치는 작업을 계획 중입니다.

### 목표
- **Single Window**: 좌측 패널 전체(높이 900px)를 하나의 트리 뷰로 사용.
- **Hierarchical Navigation**: 파일 탐색기처럼 폴더(노드)를 접고 펼 수 있는 구조.

### 트리 구조 (Draft)
```text
Root (TS File Name)
├── PSI Tables
│   ├── PAT (PID 0x0000)
│   │   ├── Program 0 (NIT) -> PMT PID 0x0010
│   │   │   └── Network Info Stream...
│   │   ├── Program 1 (Service A) -> PMT PID 0x0100
│   │   │   ├── Video Stream (PID 0x0101) [HEVC]
│   │   │   └── Audio Stream (PID 0x0102) [AAC]
│   │   └── Program 2...
│   ├── CAT (PID 0x0001)
│   ├── NIT (PID 0x0010)
│   └── SDT (PID 0x0011)
└── Statistics (Optional)
    └── ...
```

### 구현 과제
1.  **Node Class**: 트리 노드 상태(Expanded/Collapsed, Level, Parent/Child) 관리 클래스 도입.
2.  **Rendering**: `cv2`로 들여쓰기(Indentation) 및 `[+]`/`[-]` 아이콘 그리기.
3.  **Click Handling**: 노드 클릭(Select)과 확장/축소(Toggle) 이벤트 구분 처리.
4.  **Auto-Expand**: 초기 로딩 시 유효한 Program 노드 자동 확장.
