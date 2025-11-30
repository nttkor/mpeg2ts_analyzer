# PCR Jitter Measurement & Analysis Plan

## 1. 개요 (Overview)
본 문서는 MPEG2-TS 스트림 내의 **PCR (Program Clock Reference)** 정밀도를 측정하고 시각화하기 위한 계획입니다.  
Tektronix MTS430 계측기와 유사하게 **시간(X축) vs 지터량(Y축)** 그래프를 제공하며, **Timing Jitter**와 **Alignment Jitter**를 분리하여 분석합니다.

## 2. 핵심 트릭: 가상 도착 시간 (The "Trick": Virtual Arrival Time)

**중요**: 일반적인 `.ts` 파일은 패킷의 실제 수신 시간 정보를 포함하지 않습니다. (PCAP 파일과 다름)  
따라서 파일 기반 분석에서 Jitter를 측정하기 위해서는 **수학적 트릭**을 사용하여 **가상의 도착 시간(Virtual Arrival Time)**을 만들어내야 합니다.

### 2.1. 트릭의 원리 (Mechanism)
우리는 **"먹스(Mux) 과정에서 의도된 비트레이트는 일정하다(CBR)"**는 가정을 전제로, 파일 내 **PCR 값**과 **파일 위치(Offset)**의 상관관계를 역추적합니다.

1.  **샘플링**: 파일 전체(혹은 구간)의 PCR 값($t_{pcr}$)과 해당 패킷의 바이트 위치($Pos_{byte}$)를 수집합니다.
2.  **선형 회귀 (Linear Regression)**:
    - X축: 바이트 위치 ($Pos_{byte}$)
    - Y축: PCR 시간 ($t_{pcr}$)
    - 이 데이터 분포에 가장 잘 맞는 **직선($y = ax + b$)**을 찾습니다.
    - 여기서 기울기 $a$는 **전송 시간 당 바이트 수(역수: Bitrate)**가 됩니다.
3.  **가상 도착 시간 생성**:
    - 위에서 구한 이상적인 직선(Ideal Line)을 기준으로, 각 패킷 위치에서의 **"이론적 도착 시간"**을 계산합니다.
    - $$ T_{arrival\_virtual} = \frac{Pos_{byte} \times 8}{Bitrate_{estimated}} + T_{start} $$

### 2.2. 무엇을 측정하는가?
이 방식은 네트워크 전송 중 발생하는 패킷 딜레이(Network Jitter)를 측정하는 것이 아니라, **인코더/멀티플렉서가 PCR을 얼마나 규칙적인 간격으로 잘 배치했는지(Muxing Jitter)**를 측정하는 것입니다.

---

## 3. 분석 모드 (Analysis Modes)

### Mode A: Post-Analysis (Background Scan)
- **동작**: 파일 전체를 스캔하여 모든 PCR 점을 확보한 뒤, **전체 구간에 대한 최적의 직선(Bitrate)**을 찾아 분석합니다.
- **특징**: 가장 정확한 평균 Bitrate를 산출할 수 있습니다.

### Mode B: Real-time Analysis
- **동작**: 재생 중 실시간으로 들어오는 데이터만으로 Bitrate를 추정해야 합니다.
- **알고리즘**: 초기에는 헤더 정보나 초반 100개 패킷으로 가상 Bitrate를 설정하고, 데이터가 쌓일수록 **기울기(Bitrate)를 점진적으로 보정**해 나가는 방식을 사용합니다.

---

## 4. 지터 계산식 (Formulas)

### A. Timing Jitter (PCR Accuracy)
실제 기록된 PCR 값이 이론적인 도착 시간(Ideal Line)에서 얼마나 벗어났는가?

$$ J_{timing}(i) = PCR(i) - T_{arrival\_virtual}(i) $$

### B. Alignment Jitter (Packet Placement)
Timing Jitter에서 장기적인 클럭 드리프트(Wander) 성분을 제거한, 순수한 고주파 성분입니다.
- **구현**: $J_{timing}$ 데이터에 대해 고역 통과 필터(HPF)를 적용하거나, 간단히는 $J_{timing}(i) - J_{timing}(i-1)$ 등을 응용하여 계산합니다.

---

## 5. 시각화 (Visualization) - Interactive Graph

OpenCV를 활용하여 MTS430 스타일의 전문 계측 UI를 구현합니다.

### 5.1. Graph Controls
- **Auto Scale**:
  - **Global**: 전체 데이터 범위에 맞춤.
  - **Y-Auto**: 현재 X축(시간) 구간 내의 데이터에 맞춰 Y축(지터) 확대.
  - **Follow**: 실시간 모드에서 최신 데이터를 따라 X축 자동 스크롤.
- **Zoom/Pan**:
  - **X축**: 시간 확대/축소 (구간 정밀 분석).
  - **Y축**: 지터 진폭 확대 (미세 흔들림 분석).
  - **Pan**: 마우스 드래그로 이동.

### 5.2. Layout
- **Colors**: 배경(Dark Grey), Grid(Dotted Grey), Timing Jitter(Cyan), Alignment Jitter(Yellow).
- **Limit Line**: ISO 13818-1 허용치(±500ns)를 붉은 점선으로 표시.

---

## 6. 구현 현황 (Implementation Status)

2025-11-30 기준 `scripts/zitter_measurement.py` 클래스 초안 작성 완료.

### Class: `TSJitterAnalyzer`
*   **Data Structure**:
    *   `raw_pcr_data`: `(offset, pcr_val)` 튜플 리스트 저장.
    *   `timing_jitter`, `align_jitter`: 계산된 지터 결과 배열 (Numpy).
*   **Core Methods**:
    *   `analyze_full()`: `numpy.polyfit`을 이용한 1차 선형 회귀로 Bitrate 및 Jitter 계산.
    *   `auto_scale()`: 데이터 범위에 맞춰 Viewport(`scale_x`, `scale_y`) 자동 조정.
    *   `render_graph(width, height)`: MTS-430 스타일(Cyan/Yellow) 그래프 렌더링.
    *   `zoom(fx, fy)`, `pan(dx, dy)`: 마우스 인터랙션 지원.

## 7. 향후 작업 (Next Steps)
- [ ] **Integration**: `ts_analyzer_gui.py`와 `TSJitterAnalyzer` 연동.
- [ ] **Threading**: 대용량 파일 분석 시 UI 프리징 방지를 위한 스레드 처리.
- [ ] **Real-time Logic**: 재생 중 실시간 업데이트 로직(`add_pcr_data` 호출 시 부분 갱신) 구현.
