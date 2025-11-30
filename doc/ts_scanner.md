# TSScanner (Background Scanner) Documentation

## 1. 개요
**TSScanner**는 MPEG2-TS 파일 전체를 처음부터 끝까지 스캔하여 스트림의 구조와 통계 정보를 수집하는 백그라운드 워커 모듈입니다.
사용자가 GUI를 통해 영상을 탐색하는 동안, 보이지 않는 뒷부분의 데이터까지 미리 분석하여 정확한 정보를 제공하기 위해 사용됩니다.

## 2. 목적 및 필요성
- **전체 구조 파악**: 파일 중간이나 끝부분에만 등장하는 프로그램 정보나 PID를 놓치지 않기 위함.
- **정확한 통계**: 파일 전체의 PID 점유율(%)을 계산하여 대역폭 분석 가능.
- **PSI/SI 수집**: PAT, PMT 등의 테이블 정보를 완벽하게 구축하여 트리 뷰(Tree View)를 완성.

## 3. 동작 방식 (Mechanism)
### 스레드 분리
GUI의 응답성을 해치지 않기 위해 `threading` 모듈을 사용하여 별도의 스레드에서 동작합니다.
- **Start**: `AnalyzerGUI`에서 `BScan` 버튼 클릭 시 실행.
- **Stop**: 버튼을 다시 누르거나, 프로그램 종료 시, 또는 파일 끝(EOF) 도달 시 자동 종료.

### 스캔 루프 (Scan Loop)
1. 파일을 `rb` (Binary Read) 모드로 엽니다.
2. 188바이트(1 TS Packet) 단위로 순차적으로 읽습니다.
3. **헤더 파싱**: PID, PUSI, Adapt Field 등을 분석합니다.
4. **카운팅**: `parser.pid_counts` 딕셔너리에 PID별 등장 횟수를 누적합니다.
5. **PSI 파싱**:
    - **PID 0 (PAT)** 발견 시: 프로그램 목록 업데이트.
    - **PMT PID** 발견 시: 해당 프로그램의 구성 요소(Video/Audio PID) 및 코덱 정보 업데이트.
6. **CPU 제어**: 5000 패킷마다 `time.sleep(0.001)`을 호출하여 GUI 스레드에 CPU 자원을 양보합니다.

## 4. 결과물 (Output)

### 실시간 데이터 업데이트
스캔이 진행되는 동안 다음 데이터들이 실시간으로 갱신되어 GUI에 반영됩니다.
- **Total Packets**: 전체 스캔된 패킷 수.
- **Tree View**: 새로 발견된 프로그램이나 PID가 트리에 즉시 추가됨.

### 분석 리포트 (Scan Report)
스캔이 완료되면(EOF 도달 또는 중지), 요약 리포트를 생성합니다.

#### 저장 위치
- 경로: `output/` 폴더
- 파일명: `BScan_Report_YYYYMMDD_HHMMSS.md`

#### 리포트 포맷 예시
```markdown
# MPEG2-TS Scan Report
- Date: 2023-10-27 14:30:00
- File: D:\git\mpeg2TS\TS\mama_uhd2.ts
- Total Packets: 123456
- File Size: 23456789 bytes

## PID Usage Statistics
| PID | Description | Count | Percentage |
|---|---|---|---|
| 0x0200 | H.265 (HEVC) | 110000 | 89.10% |
| 0x0102 | MPEG-1 Audio | 500 | 0.40% |
| 0x0000 | PAT | 100 | 0.08% |
...
```

## 5. 코드 위치
- **파일**: `scripts/ts_scanner.py`
- **클래스**: `TSScanner`

