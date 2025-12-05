# 작업 요약 (2025-11-30)

## 1. 구현 완료 사항

### A. PES / Section Analysis 윈도우 하이라이트 기능 구현
- **기능**: 우측 중간 분석 창의 데이터 필드(Table ID, PCR, Stream ID, PTS/DTS 등)에 마우스 오버 시 하이라이트 박스 표시.
- **연동**: 하이라이트된 필드에 해당하는 바이너리 데이터가 Hex View에서도 동시에 강조되도록 `ui_regions` 연동 처리.
- **적용 범위**:
  - **PES 패킷**: Stream ID, Packet Length, PTS, DTS.
  - **PSI 테이블 (PAT/PMT)**: Table ID, Section Length, TS ID/PCR PID, Program Info, ES 항목.

### B. UI/UX 및 레이아웃 개선
- **Toolbar 재배치**:
  - `PLAYING` 상태 텍스트 하단에 배속 정보(`x50.0`) 표시.
  - Play/Pause 버튼 폰트 크기 원복 및 좌측 정렬.
  - 필터 버튼(PAT, PMT, Video, Audio 등) 우측으로 이동하여 간섭 제거.
- **PAT 버튼 동기화**: Toolbar의 PAT 버튼 클릭 시 `selected_pid=0`으로 강제 설정하여 분석 창에 PAT 정보 즉시 표시.
- **마우스 호버 개선**:
  - PAT 목록에서 마우스 오버 시 반응하도록 좌표 계산 로직 정밀화.
  - 마우스 좌표(`mouse_x`, `mouse_y`)의 전역 갱신 이슈 해결.

## 2. 버그 수정 (Fixes)

### A. "Program이 1개만 보이는 문제" 수정
- **원인**: `run()` 함수에서 초기 `quick_scan`만 실행하고, 파일 전체를 분석하는 백그라운드 파싱이 시작되지 않음.
- **해결**: `self.parser.start_background_parsing()` 호출 코드를 추가하여 모든 프로그램을 감지하도록 수정.

### B. PAT 리스트 마우스 오버 반응성 개선
- **원인**: 선택된 항목(Selected)이 호버(Hover) 상태보다 우선순위가 높아, 선택된 상태에서는 마우스 오버 효과가 보이지 않음.
- **해결**: 선택된 항목이라도 마우스 오버 시 배경색을 더 밝게 변경(`(80, 80, 110)`)하여 시각적 피드백 제공.

### C. PAT 정보 사라짐 문제
- **해결**: PAT 영역 클릭 또는 필터 버튼 클릭 시 PID 0번을 명시적으로 선택하도록 로직 보강.

