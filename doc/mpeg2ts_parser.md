# MPEG2-TS Analyzer Project Documentation

## 1. 프로젝트 개요
Harmonic CP9000 인코더로 생성된 HEVC 4K TS 스트림(`mama_uhd2.ts`)이 특정 디코더(NTT HC11000DS)에서 오디오 미출력 문제를 일으키는 원인을 분석하기 위한 프로젝트입니다.
방송 계측 장비인 **Tektronix MTS430**의 분석 스타일을 벤치마킹하여, 직관적인 GUI 환경에서 TS 패킷 구조를 정밀 진단할 수 있도록 개발되었습니다.

## 2. 시스템 구조 (Architecture)
초기 단일 스크립트에서 유지보수성과 확장성을 위해 **4개의 모듈**로 기능을 분리하였습니다.

### 📂 파일 구성
```text
scripts/
├── ts_analyzer_gui.py    # [Main] GUI 진입점 및 화면 출력 담당
├── ts_parser_core.py     # [Core] TS 패킷 파싱 로직 및 데이터 모델
├── ts_scanner.py         # [Worker] 백그라운드 전체 스캔 및 통계 수집
└── play_ts_opencv.py     # [Player] OpenCV 비디오 재생 전용 모듈
```

## 3. 모듈별 상세 기능

### ① `ts_analyzer_gui.py` (GUI Controller)
- **역할**: 사용자 인터페이스 및 전체 프로그램 제어.
- **라이브러리**: OpenCV (`cv2`).
- **주요 기능**:
    - **Tree View (좌측)**: PAT/PMT 구조를 계층적 트리로 시각화 (Program -> Video/Audio).
    - **Detail View (우측 상단)**: 현재 패킷의 헤더 정보(PID, PUSI, CC) 및 PID 속성 표시.
    - **Hex View (우측 하단)**: 188바이트 Raw Data를 16진수와 ASCII로 표시.
    - **Controls (상단)**: Play(`>`), Pause(`||`), Stop(`STOP`), Frame Step 이동.
    - **BScan 버튼**: 백그라운드 전수 검사 ON/OFF 토글.

### ② `ts_parser_core.py` (Parsing Engine)
- **역할**: TS 데이터 처리의 핵심 로직.
- **클래스**: `TSParser`
- **주요 기능**:
    - `read_packet_at(index)`: Random Access 지원 (Seek 기능).
    - `parse_header()`: TS 헤더 비트 필드 파싱.
    - `quick_scan()`: 파일 초기 로드 시 앞부분만 빠르게 읽어 구조 파악.
    - `programs`, `pid_counts` 등 분석 데이터 저장소 역할.

### ③ `ts_scanner.py` (Background Worker)
- **역할**: 파일 전체를 순회하며 통계를 내는 무거운 작업을 전담.
- **클래스**: `TSScanner`
- **주요 기능**:
    - 별도 스레드(`threading`)에서 동작하여 GUI 멈춤 방지.
    - 파일 끝까지 읽으며 전체 PID 개수 카운팅.
    - 발견되지 않았던 후반부의 PSI/SI 테이블 업데이트.

### ④ `play_ts_opencv.py` (Video Player)
- **역할**: 단순 비디오 재생 확인용.
- **주요 기능**: `cv2.VideoCapture`를 이용해 HEVC 영상을 디코딩하고 화면에 출력.

---

## 4. 사용 방법 (Usage)

### 실행
```bash
python scripts/ts_analyzer_gui.py
```

### 조작법
- **`>` / `||`**: 패킷 단위 자동 진행 (Play) / 일시정지 (Pause).
- **`<<` / `>>`**: 고속 탐색 (되감기 / 빨리감기).
- **`STOP`**: 처음 위치로 이동 및 정지.
- **`BScan`**: 백그라운드 전체 스캔 시작/중지 (전체 통계 필요 시 사용).
- **`Video Win`**: 별도의 비디오 재생 창 띄우기 (영상 확인용).
- **키보드 단축키**:
    - `Space`: 재생/일시정지 토글.
    - `,` (콤마): 이전 패킷으로 1칸 이동.
    - `.` (점): 다음 패킷으로 1칸 이동.
    - `p`: 비디오 플레이어 실행.
    - `q`: 프로그램 종료.

---

## 5. 분석 진행 상황
- **비디오**: HEVC 4K @ 59.94fps (PID 0x200) 정상 확인.
- **오디오**: PID 0x102 ~ 0x109 (8채널).
    - PES Header 파싱 결과: Start Code(`0x000001`) 정상.
    - MP2 Sync Word: `FFF` 패턴 확인 필요.
    - (현재 분석 중): 디코더 호환성 문제의 원인이 **PES 헤더 구조**인지 **스트림 설정(Descriptor)** 문제인지 확인 필요.
