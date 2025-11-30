# MPEG2-TS Analyzer Project Documentation

## 1. 프로젝트 개요
Harmonic CP9000 인코더로 생성된 HEVC 4K TS 스트림(`mama_uhd2.ts`)의 디코더 호환성 문제(NTT HC11000DS 오디오 미출력)를 분석하기 위한 프로젝트입니다.
방송 계측 장비인 **Tektronix MTS430**의 분석 스타일을 벤치마킹하여, 직관적인 GUI 환경에서 TS 패킷 구조를 정밀 진단할 수 있습니다.

- **GitHub Repository**: [https://github.com/nttkor/mpeg2ts_analyzer](https://github.com/nttkor/mpeg2ts_analyzer)

## 2. 시스템 구조 (Architecture)
유지보수성과 확장성을 위해 기능별로 **6개의 모듈**로 분리되었습니다.

### 📂 파일 구성
```text
scripts/
├── ts_analyzer_gui.py    # [Main Controller] GUI 진입점, 전체 조율
├── ts_ui_manager.py      # [View/Input] 툴바, 메뉴, 마우스 이벤트 처리
├── ts_parser_core.py     # [Core Engine] 파싱 로직 및 상태 관리
├── ts_models.py          # [Data Model] Packet, PAT, PMT, PES 클래스 정의
├── ts_scanner.py         # [Worker] 백그라운드 파일 스캔 및 리포트
└── play_ts_opencv.py     # [Player] OpenCV 비디오 재생 모듈
```

## 3. 모듈별 상세 기능

### ① `ts_analyzer_gui.py` (Controller)
- **역할**: 애플리케이션 수명 주기 관리, 파일 로드, 메인 뷰 그리기(Tree, Hex, Detail, PES View).
- **특징**: `UIManager`를 통해 사용자 입력을 받고, `TSParser` 데이터를 시각화합니다.

### ② `ts_ui_manager.py` (UI Manager)
- **역할**: 복잡한 GUI 요소를 별도로 관리.
- **기능**: Toolbar, Menu System(File/Recent), Mouse Interaction.

### ③ `ts_models.py` (Data Models) - **[New!]**
- **역할**: TS 데이터 구조의 객체 지향적 정의.
- **클래스**:
    - `TSPacket`: 188바이트 패킷 헤더 파싱.
    - `PSISection` (Base) -> `PATSection`, `PMTSection`.
    - `PESHeader`: PES 구조(PTS/DTS, StreamID) 분석.

### ④ `ts_parser_core.py` (Parsing Engine)
- **역할**: 파일을 읽고 `ts_models`를 활용하여 데이터를 추출.
- **기능**: Random Access(`read_packet_at`), 퀵 스캔.

### ⑤ `ts_scanner.py` (Background Scanner)
- **역할**: 파일 전체 통계 수집.
- **기능**: 백그라운드 스레드 동작, PID 점유율 분석, Markdown 리포트 생성.

---

## 4. 주요 기능 (Key Features)

1. **PES / Audio Deep Analysis**
    - **Single/Multi Packet 구분**: PES 패킷이 단독인지 분할되었는지 판별.
    - **Audio Sync Check**: 오디오 스트림 내의 Sync Word(`0xFFF`) 패턴 자동 검색.
    - **PTS/DTS**: 타임스탬프 파싱 및 초(s) 단위 표시.

2. **Smart Navigation**
    - **PID Filtering**: 특정 PID를 선택하면 해당 패킷 단위로 건너뛰며 탐색 가능.
    - **BScan**: 백그라운드에서 파일 전체를 스캔하여 놓친 PID나 프로그램 정보를 찾아냄.

3. **User-Friendly GUI**
    - **Menu System**: File Open, Recent Files, Exit 지원.
    - **Hex View**: 실시간 바이너리 덤프.
    - **Tree View**: 직관적인 프로그램/스트림 계층 구조 확인.

---

## 5. 사용 방법 (Usage)
```bash
python scripts/ts_analyzer_gui.py
```
- **File > Open**: 분석할 TS 파일 선택.
- **BScan**: 전체 파일 구조 분석.
- **Tree View**: 프로그램 및 PID 선택 (마우스 클릭).
- **PES View**: 선택된 PID의 상세 헤더 및 오디오 정보 확인.
