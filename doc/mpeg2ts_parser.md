# MPEG2-TS Parser Project

## 개요
Python과 OpenCV를 활용한 MPEG2-TS 스트림 분석기입니다.
Tektronix MTS430과 유사한 직관적인 GUI를 제공하며, 실시간 패킷 분석 및 탐색이 가능합니다.

## Architecture
본 프로젝트는 5개의 모듈로 구성되어 있습니다:
1. `ts_analyzer_gui.py`: 메인 GUI 컨트롤러 (OpenCV 기반)
2. `ts_parser_core.py`: TS 패킷 파싱 핵심 로직
3. `ts_scanner.py`: 백그라운드 전체 파일 스캔 및 리포트 생성
4. `ts_ui_manager.py`: UI 드로잉 및 입력 이벤트 관리
5. `ts_models.py`: TS 데이터 구조체 (Packet, Header, Section 등)

## 주요 기능 (Features)

### 1. Multi-View Dashboard
- **PAT / PMT View**: 트리 구조로 프로그램 및 스트림 구성을 시각화. 클릭하여 필터링 가능.
- **Detail View**: 선택된 패킷의 헤더 정보(PID, PUSI, CC, Scrambling 등) 상세 표시.
- **PES View**: PES 헤더 파싱, PTS/DTS 타임스탬프, 오디오/비디오 스트림 정보 표시.
- **Hex View**: 패킷 데이터의 16진수 및 ASCII 덤프 (재생 중 최적화).

### 2. Smart Navigation
- **Timeline Control**: Play, Pause, FF(x2, x50), Rewind 기능.
- **PES Jump**: 이전/다음 PES Start 패킷으로 자동 탐색 및 이동.
  - 고속 탐색 모드 지원 (모든 패킷 정밀 검사).
  - PMT 선택 PID 우선 추적.
- **PID Filtering**: 특정 PID만 필터링하여 탐색 가능.

### 3. Background Analysis (BScan)
- 별도 스레드에서 전체 파일을 스캔하여 PID별 사용량, 점유율, 연속성 오류 등을 분석.
- 분석 완료 후 Markdown 형식의 리포트 자동 생성 (`output/` 폴더).

## 2025-11-30 Update: Advanced PES Navigation & Optimization

### 주요 변경 사항
1. **PES Navigation (Jump) 기능 강화**
   - **양방향 탐색**: `Prev(◀)` / `Next(▶)` 버튼을 통해 이전/다음 PES Start 패킷으로 이동 가능.
   - **스마트 탐색**: 
     - PMT에서 선택된 PID를 우선적으로 추적.
     - 선택된 PID가 없으면 현재 패킷의 PID를 기준으로 탐색.
   - **고속 탐색 모드**: 버튼 클릭 시 `x50` 배속으로 재생하며 탐색하고, `PES Start(PUSI=1)`를 발견하면 자동으로 정지.
   - **정밀 검사**: 고속 재생 중에도 건너뛰는 패킷 없이 모든 패킷을 검사하여 Start 패킷을 놓치지 않음.

2. **UI/UX 개선**
   - **직관적인 버튼 배치**: `>> PES Packet Start <<` 문구 양옆에 네비게이션 버튼 배치.
   - **불필요한 텍스트 제거**: "Find Prev/Next Start" 텍스트를 제거하고 아이콘만 남김.
   - **Start 상태 표시**: PES Start 패킷일 때도 네비게이션 버튼을 표시하여 연속적인 탐색 지원.
   - **Play 모드 최적화**: 재생/탐색 중에는 Hex Dump 등 무거운 텍스트 렌더링을 생략하여 반응 속도 향상 ("Playback in progress...").

3. **버그 수정**
   - PES Start 패킷 인식 오류 수정 (현재 패킷부터 검사하도록 로직 변경).
   - 고속 탐색 시 패킷을 건너뛰어 멈추지 않는 문제 해결.
   - 네비게이션 버튼 미표시 문제 해결.

## 사용 방법 (Usage)
```bash
python scripts/ts_analyzer_gui.py
```
- **File**: TS 파일 열기 (Open) 또는 종료 (Exit).
- **BScan**: 백그라운드 스캔 시작/중지 및 리포트 보기.
- **Playback**: 하단 컨트롤 바 또는 키보드 단축키 사용.
- **PES Jump**: PES 뷰의 `◀`, `▶` 버튼 클릭.

## To-Do
- [ ] 오디오 코덱별 상세 헤더 파싱 (MP2, AAC, AC3 등)
- [ ] 비디오 프레임 타입(I/P/B) 분석 추가
- [ ] PCR 클럭 분석 및 Jitter 그래프
