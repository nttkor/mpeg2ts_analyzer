# MPEG2-TS Class Architecture & Models

## 1. 개요
이 문서는 MPEG2-TS 분석기의 데이터 모델링 및 객체 지향 구조를 설명합니다.
기존의 함수 위주 파싱 로직을 **데이터 모델(Model)** 클래스로 캡슐화하여, `ts_parser_core.py`와 `ts_analyzer_gui.py`에서 공통으로 사용합니다.

## 2. 파일 구조
```text
scripts/
├── ts_models.py          # [Implemented] TS 데이터 모델 클래스 (Packet, PSI, PES)
├── ts_parser_core.py     # [Core] 모델 클래스를 활용한 파싱 엔진
├── ts_analyzer_gui.py    # [View] 모델 데이터를 시각화
```

## 3. 클래스 상세 (ts_models.py)

### A. `TSPacket` (기본 패킷)
- **역할**: 188바이트 TS 패킷의 헤더 파싱 및 Payload 추출.
- **주요 속성**:
    - `pid`: Packet Identifier (13-bit)
    - `pusi`: Payload Unit Start Indicator (bool)
    - `tei`: Transport Error Indicator (bool)
    - `cc`: Continuity Counter (4-bit)
    - `adapt`: Adaptation Field Control (2-bit)
    - `payload`: 헤더와 Adaptation Field를 제외한 순수 데이터.

### B. PSI (Program Specific Information)
**`PSISection` (Base Class)**
- 테이블 섹션(Section)의 공통 헤더(Table ID, Length)를 파싱합니다.

**`PATSection` (inherits PSISection)**
- **Program Association Table**.
- `programs` 속성: `{ program_number: pmt_pid }` 딕셔너리로 프로그램 맵 제공.

**`PMTSection` (inherits PSISection)**
- **Program Map Table**.
- `pcr_pid`: PCR(Program Clock Reference) PID.
- `streams` 속성: `{ elementary_pid: { 'type': int, 'desc': str } }`.
- 스트림 타입(Stream Type)에 따라 "MPEG-2 Video", "AAC Audio" 등의 설명을 자동 매핑.

### C. `PESHeader` (Packetized Elementary Stream)
- **역할**: PUSI=1인 패킷의 Payload 시작 부분에 위치한 PES 헤더를 분석.
- **주요 속성**:
    - `stream_id`: 스트림 종류 식별 (Audio, Video, Private).
    - `length`: PES 패킷 길이. 0이면 길이 미지정(비디오 등).
    - `pts`: Presentation Time Stamp (초 단위 `float`로 변환됨).
    - `dts`: Decoding Time Stamp.

## 4. 데이터 흐름 (Data Flow)
1. **Raw Data Read**: `TSParser`가 파일에서 188바이트를 읽습니다.
2. **Model Creation**: `packet = TSPacket(raw_data)`를 생성하여 헤더 정보를 즉시 파악합니다.
3. **Dispatch**:
    - `packet.pid == 0`: `PATSection(packet.payload)` 생성.
    - `packet.pid == PMT_PID`: `PMTSection(packet.payload)` 생성.
    - `packet.pusi == True`: `PESHeader(packet.payload)` 생성하여 오디오/비디오 상세 정보 획득.

## 5. 향후 계획
- **SIT / SDT / NIT**: 추가적인 SI 테이블용 클래스 구현 (`PSISection` 상속).
- **Adaptation Field**: `TSPacket` 내에 PCR 등 Adaptation Field 상세 파싱 로직 추가.
