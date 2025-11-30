# MPEG2-TS Analyzer Project

## 개요
**MPEG2-TS Analyzer**는 방송용 TS(Transport Stream) 파일을 정밀 분석하기 위한 도구입니다.
기존의 단순 재생/덤프 도구와 달리, 전문 계측 장비(예: Tektronix MTS430) 스타일의 GUI를 제공하여 스트림의 계층 구조(PAT/PMT)와 패킷 단위 데이터를 시각적으로 분석할 수 있습니다.

## 목표
NTT HC11000DS 디코더 호환성 분석을 위해, Harmonic CP9000 인코더로 생성된 스트림의 내부 구조(오디오 PES, Sync Word, Descriptor 등)를 정밀 진단하는 것을 목표로 합니다.

---

## 프로젝트 구조
코드는 기능별로 모듈화되어 있습니다.

### 1. `scripts/ts_parser_core.py` (Core Logic)
- **역할**: TS 파싱 엔진. GUI와 독립적으로 동작하며 순수 데이터 분석을 담당합니다.
- **주요 클래스**: `TSParser`
    - **PSI 파싱**: PAT(PID 0) 및 PMT를 자동으로 탐지하고 파싱하여 `programs` 딕셔너리에 구조화합니다.
    - **패킷 읽기**: `read_packet_at(index)`를 통해 특정 위치의 패킷(188 bytes)을 랜덤 액세스(Seek) 할 수 있습니다.
    - **백그라운드 스캔**: 별도 스레드에서 전체 파일을 스캔하며 PID 통계를 수집합니다.

### 2. `scripts/ts_analyzer_gui.py` (GUI)
- **역할**: OpenCV 기반의 분석 대시보드. 사용자 입력을 처리하고 데이터를 시각화합니다.
- **주요 클래스**: `AnalyzerGUI`
    - **Layout**:
        - **Left (Tree View)**: Program -> PMT -> Component(Video/Audio) 계층 구조 표시.
        - **Right Top (Detail View)**: 현재 선택된 패킷의 헤더 정보 및 PID 상세 정보 표시.
        - **Right Bottom (Hex View)**: 현재 패킷의 188바이트 바이너리 데이터(Hex/ASCII) 표시.
        - **Bottom (Controls)**: Play/Pause, Seek, Packet Step 이동 버튼.
    - **Interaction**: 마우스 클릭 이벤트 처리 (버튼, 트리 항목 선택).

### 3. `scripts/play_ts_opencv.py` (Player)
- **역할**: 단순 비디오 재생기.
- **기능**: OpenCV(`cv2.VideoCapture`)를 사용하여 FFmpeg 백엔드로 영상을 디코딩하고 화면에 표시합니다. GUI에서 'Video Win' 버튼을 누르면 실행됩니다.

---

## 주요 기능 (Features)
1. **계층적 구조 분석 (Tree View)**
    - PAT를 파싱하여 프로그램 목록을 획득.
    - 각 프로그램의 PMT를 추적하여 Video/Audio PID 및 Stream Type(코덱)을 식별.
    - "Video (H.265)", "Audio (MPEG-1)" 등으로 친절하게 표시.

2. **패킷 단위 네비게이션**
    - `>` (Play), `||` (Pause) 기능 지원.
    - `< Pkt`, `Pkt >` 버튼으로 1패킷씩 정밀 이동 가능.
    - `<<`, `>>` 버튼으로 고속 탐색 지원.

3. **바이너리 데이터 확인 (Hex View)**
    - 현재 커서가 위치한 패킷의 Raw Data를 16진수와 ASCII로 실시간 표시.
    - 헤더 분석(PID, PUSI, Counter) 결과와 연동.

---

## 사용 방법
```bash
# 분석기 실행
python scripts/ts_analyzer_gui.py
```

## 향후 계획 (To-Do)
- [ ] **PES 정밀 분석**: 오디오/비디오 패킷의 PES Header(PTS/DTS) 파싱 상세화.
- [ ] **PCR 분석**: PCR(Program Clock Reference) Jitter 및 간격 분석 그래프 추가.
- [ ] **오디오 포맷 검증**: MP2/AAC 오디오 헤더를 파싱하여 샘플링 레이트, 비트레이트 표시.

