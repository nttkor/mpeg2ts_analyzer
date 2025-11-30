# MPEG2-TS Class Refactoring Plan

## 1. 개요
기존의 함수 위주 파싱 로직을 **객체 지향적(Object-Oriented)** 구조로 리팩토링하여 유지보수성과 확장성을 높입니다.
데이터 모델(`Model`)과 처리 로직(`Parser/Handler`)을 분리하고, 각 TS 구성 요소(PAT, PMT, PES 등)를 클래스로 정의합니다.

## 2. 파일 구조 (File Structure)
```text
scripts/
├── ts_models.py          # [New] TS 데이터 모델 클래스 정의 (Packet, PAT, PMT, PES)
├── ts_parser_core.py     # [Refactor] TSDemuxer 역할 (패킷 읽기 및 모델 생성)
├── ts_analyzer_gui.py    # [View] 모델 데이터를 받아 화면에 표시
└── ...
```

## 3. 클래스 설계 (Class Hierarchy)

### A. 기본 패킷 (Base Packet)
**`TSPacket`**
- **역할**: 188바이트 TS 패킷의 기본 래퍼(Wrapper).
- **속성**:
    - `raw_data`: `bytes` (188)
    - `pid`: `int` (13-bit)
    - `pusi`: `bool` (Payload Unit Start Indicator)
    - `transport_error`: `bool`
    - `continuity_counter`: `int`
    - `adaptation_field_control`: `int`
    - `payload`: `bytes` (헤더/Adaptation 제외한 실제 데이터)
- **메서드**:
    - `parse_header()`: 헤더 비트 파싱.
    - `has_payload()`: 페이로드 존재 여부 반환.

### B. PSI (Program Specific Information)
**`PSISection` (Base Class)**
- **역할**: PAT, PMT 등 테이블 섹션의 공통 부모 클래스.
- **속성**:
    - `table_id`: `int`
    - `section_length`: `int`
    - `version_number`: `int`

**`PATSection` (inherits `PSISection`)**
- **역할**: Program Association Table 파싱.
- **속성**:
    - `programs`: `dict` { `program_number`: `pmt_pid` }

**`PMTSection` (inherits `PSISection`)**
- **역할**: Program Map Table 파싱.
- **속성**:
    - `program_number`: `int`
    - `pcr_pid`: `int`
    - `streams`: `list` of `ESInfo`
        - `ESInfo`: { `stream_type`: `int`, `elementary_pid`: `int`, `desc`: `str` }

### C. PES (Packetized Elementary Stream)
**`PESHeader`**
- **역할**: PES 헤더 정보 파싱 (Payload의 시작 부분 분석).
- **속성**:
    - `stream_id`: `int`
    - `packet_length`: `int`
    - `pts`: `float` or `None`
    - `dts`: `float` or `None`
    - `is_video`: `bool`
    - `is_audio`: `bool`

### D. 처리기 (Core/Demuxer)
**`TSParser` (Existing, to be refactored)**
- **역할**: 파일을 읽고 `TSPacket` 객체를 생성한 뒤, PID에 따라 적절한 `PSISection`이나 `PESHeader`를 생성하여 저장.

## 4. 데이터 흐름 (Data Flow)
1. `TSParser`가 파일에서 188바이트 `read`.
2. `TSPacket(data)` 객체 생성 (헤더 자동 파싱).
3. `packet.pid` 확인:
    - **PID 0**: `PATSection(packet.payload)` 생성 -> 프로그램 목록 업데이트.
    - **PMT PID**: `PMTSection(packet.payload)` 생성 -> 스트림 정보 업데이트.
    - **ES PID**: `packet.pusi`가 True면 `PESHeader(packet.payload)` 생성 -> PES 정보 분석.

## 5. 장점
- **가독성**: `pid_map['desc']` 처럼 딕셔너리를 직접 쓰는 대신 `pmt.streams[0].desc` 처럼 명시적인 속성 접근 가능.
- **확장성**: 추후 `SIT`, `SDT` 등 새로운 테이블 추가 시 `PSISection`을 상속받아 쉽게 구현 가능.
- **유지보수**: 파싱 로직이 각 클래스 내부에 캡슐화되어 있어, 수정 시 영향 범위가 한정됨.

