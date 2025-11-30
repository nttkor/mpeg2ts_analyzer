# MPEG2-TS PCR (Program Clock Reference) 분석

## 1. 개요 (Overview)
**PCR (Program Clock Reference)**은 MPEG2-TS 스트림에서 디코더의 **시스템 타임 클럭(STC)**을 인코더의 클럭과 동기화하기 위해 전송되는 기준 시간 정보입니다.
수신 측(디코더)은 이 값을 이용해 내부 클럭(27MHz)을 보정하고, PTS/DTS와 비교하여 오디오/비디오의 재생 시점을 결정합니다.

## 2. PCR 데이터 구조 (Structure)
PCR은 총 **42비트**로 구성되며, 27MHz 클럭을 기준으로 합니다. Adaptation Field 내에 존재합니다.

- **PCR Base (33 bits)**: 90kHz 클럭 (시스템 기본 클럭).
- **Reserved (6 bits)**: 예약된 비트 (주로 1로 채워짐).
- **PCR Extension (9 bits)**: 27MHz 클럭 (0~299 사이의 값, 300이 되면 Base가 1 증가).

$$ PCR\_Value = PCR\_base \times 300 + PCR\_ext $$
$$ Time(sec) = \frac{PCR\_Value}{27,000,000} $$

## 3. 프로젝트 구현 현황 (Implementation)

본 분석기는 PCR의 **전송 경로(PID)** 식별과 **실제 값(Value)** 파싱을 모두 지원합니다.

### 3.1. PCR PID 식별 (Core Logic)
PCR이 어떤 PID를 통해 전송되는지는 **PMT (Program Map Table)**에 정의되어 있습니다.
- **Video PID와 동일한 경우**: 비디오 패킷 헤더(Adaptation Field)에 PCR을 실어 보냄 (대역폭 효율적, 일반적).
- **별도 PID인 경우**: PCR 전송만을 위한 독립적인 PID 사용 (라디오 등).

**코드 구현 (`ts_parser_core.py`):**
```python
# PMT Section Parsing
pcr_pid = ((data[8] & 0x1F) << 8) | data[9]
prog_node['pcr_pid_val'] = pcr_pid
```

### 3.2. PCR 값 추출 (Packet Parsing)
개별 패킷의 **Adaptation Field**를 분석하여 `PCR_flag`가 `1`인 경우 6바이트의 PCR 데이터를 추출합니다.

**코드 구현 (`ts_parser_core.py`):**
```python
if info['pcr_flag']:
    pcr_bytes = packet[idx:idx+6]
    v = struct.unpack('>Q', b'\x00\x00' + pcr_bytes)[0]
    pcr_base = (v >> 15) & 0x1FFFFFFFF
    pcr_ext = v & 0x1FF
    info['pcr'] = pcr_base * 300 + pcr_ext
```

## 4. GUI 기능 (User Interface)

### 4.1. PMT View (좌측 패널)
- **PCR PID 표시**: 프로그램 정보 상단에 `PCR PID: 0xXXX` 형태로 명시.
- **스트림 태그**: 스트림 목록에서 PCR을 담당하는 PID 옆에 `(PCR)` 태그를 붙여 시각적으로 구분.
  - 예: `PID 0x0100 : H.264 (Video) (PCR)`

### 4.2. Detail View (우측 패널)
- 패킷 상세 분석 화면에서 Adaptation Field가 존재하고 PCR이 포함된 경우 값을 표시.
- **표시 항목**:
  - **Raw Value**: 27MHz 기준 정수값.
  - **Time**: 초(sec) 단위 환산값 (소수점 6자리).

## 5. 활용 (Usage)
1. **PCR 전송 경로 확인**: PMT 뷰를 통해 PCR이 비디오 PID에 묻혀오는지(Embedded), 따로 오는지(Separate) 확인.
2. **PCR 간격 분석**: Detail View에서 연속된 PCR 패킷의 시간을 확인하여 전송 간격(Interval)이 규격(통상 100ms, 최대 40ms 권장)을 준수하는지 1차적인 확인 가능.
