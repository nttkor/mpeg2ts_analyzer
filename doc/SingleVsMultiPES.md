네, **말씀하신 대로 이미 그렇게 동작하도록 구현되어 있습니다.**

현재 구현된 로직을 분석해 보면 사용자가 원하시는 **"모든 오디오 채널 검색 + 검색된 PID 자동 표시"** 기능이 정상적으로 작동하는 구조입니다.

### 🛠️ 현재 구현된 로직 분석

**1. 툴바 Audio 버튼의 역할 (검색 조건)**
*   툴바의 `Audio` 버튼을 켜면, 특정 PID 하나만 찾는 것이 아니라 **"Audio 타입(0x03, 0x0F 등)을 가진 모든 패킷"**을 검색 조건(`check_packet_filter`)으로 설정합니다.
*   따라서 PMT에서 무엇이 선택되어 있든 상관없이, 다음(Next) 버튼을 누르면 **스트림 내의 모든 오디오 패킷**을 찾습니다.

**2. 검색 시 화면 갱신 (자동 PID 선택)**
*   `_handle_playback` (스마트 서치) 루프 안에는 다음과 같은 로직이 있습니다.
    ```python
    # 필터 탐색으로 찾았는데 PID가 다르면, 선택 PID를 자동 변경
    if is_filter_active and self.selected_pid is not None:
        # ... (PID 파싱) ...
        if pid != self.selected_pid:
            self.selected_pid = pid  # <--- 여기서 자동으로 PMT 선택을 바꿈
    ```
*   즉, `Audio Ch 1`을 보고 있다가 `Next`를 눌렀는데 `Audio Ch 2` 패킷이 발견되면, **자동으로 `Audio Ch 2` PID로 포커스가 이동**하며 화면(PES View, Detail View)도 그에 맞춰 갱신됩니다.

### 📝 요약

사용자께서 느끼시는 **"애매함"**은 UI의 표현 방식 때문일 수 있습니다.

*   **PMT 영역**: 현재 **"보고 있는"** 하나의 채널 (Current Focus)
*   **툴바 영역**: 앞으로 **"찾을"** 대상들의 그룹 (Search Condition)

**결론:**
지금 상태에서도 툴바의 `Audio`만 켜져 있으면, `Next`(`->`) 버튼을 누를 때마다 채널 1, 채널 2, 채널 3 등 **오디오 패킷이 나오는 순서대로 번갈아가

며 자동으로 PID가 바뀌면서 보여집니다.** 별도로 수정할 필요는 없어 보입니다.
네, 맞습니다. **PUSI(Payload Unit Start Indicator)** 플래그의 정의와 **PES 패킷 구조**를 생각하면 사용자님의 말씀이 정확합니다.

### 1. PUSI = 1 (Start of PES)
이 패킷의 Payload 시작 부분에 **PES Header**가 존재한다는 뜻입니다.
*   이때 PES Header 안에 있는 `PES_packet_length` 필드를 확인합니다.
    *   **Length > 0 (예: 2048)**: 이 PES 패킷은 총 2048바이트입니다. TS 패킷 하나(payload 184바이트)에 다 안 들어가므로, 뒤에 `PUSI=0`인 패킷들이 이어져야 합니다 (**Multi-packet**).
    *   **Length <= 184 (Small)**: 이 PES 패킷은 TS 패킷 하나에 쏙 들어갑니다 (**Single-packet**). 뒤에 `PUSI=0`이 올 필요가 없습니다.
    *   **Length = 0 (Unbounded)**: 비디오 스트림 등에서 길이를 지정하지 않을 때 씁니다. 다음 `PUSI=1`이 나올 때까지 무한정 `PUSI=0`이 이어집니다 (**Multi-packet**).

### 2. PUSI = 0 (Continuation)
이 패킷에는 **PES Header가 없습니다.** 즉, **이전(Previous)에 시작된 PES 패킷의 데이터가 계속 이어지고 있음**을 의미합니다.
*   TS 표준상, `PUSI=0`인 패킷은 **반드시** 앞선 `PUSI=1` 패킷(Start)의 **연장선(Continuation)**이어야 합니다.
*   따라서 **"PUSI=0이면 Multi-packet PES의 일부(Continuation)이다"**라는 명제는 **참(True)**입니다.

### ⚠️ 예외 케이스 (주의할 점)
단, "Continuation이 맞다"고 확신하기 위해서는 **단 하나의 전제 조건**이 필요합니다.
> **"패킷 손실(Packet Loss)이 없었고, 스트림이 중간에 끊기지 않았다."**

만약 방송 신호 불량으로 `PUSI=1` 패킷이 유실되고 그 뒤의 `PUSI=0` 패킷만 수신되었다면, 규격상으로는 Continuation이 맞지만 **디코더 입장에서는 "헤더 없는 고아 패킷"**이 되어 디코딩할 수 없습니다. (CC 에러 발생)

하지만 분석기 입장에서는 **"논리적으로 Continuation 패킷의 형태를 띠고 있다"**고 판단하고 표시하는 것이 맞습니다. 사용자님의 판단이 옳습니다.