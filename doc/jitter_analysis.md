# PCR Jitter Measurement & Analysis

## 1. 개요 (Overview)
본 문서는 MPEG2-TS 스트림 내의 **PCR (Program Clock Reference)** 정밀도를 분석하는 기능에 대한 기술 문서입니다.  
Tektronix MTS430과 유사한 인터페이스를 제공하며, **Timing Jitter**와 **Alignment Jitter**를 분리하여 시각화합니다.

## 2. 분석 알고리즘 (Algorithm)

### 2.1. "The Trick": 가상 도착 시간 (Virtual Arrival Time)
일반적인 `.ts` 파일은 패킷의 실제 수신 시간(Timestamp) 정보를 포함하지 않습니다. (PCAP 파일과 다름)  
따라서 파일 기반 분석에서 Jitter를 측정하기 위해 다음과 같은 수학적 모델을 사용합니다.

**전제**: 인코더/멀티플렉서의 의도된 출력 비트레이트(CBR)는 일정하다.

1.  **데이터 수집**: 파일 전체의 `(Byte Offset, PCR Value)` 쌍을 수집합니다.
2.  **선형 회귀 (Linear Regression)**:
    - 수집된 데이터에 대해 $y = ax + b$ (x: offset, y: time) 형태의 추세선을 구합니다.
    - 여기서 기울기 $a$의 역수는 **Bitrate (bits/sec)**가 됩니다.
3.  **가상 시간 생성**:
    - 위에서 구한 추세선(Ideal Line)이 곧 "지터가 없는 이상적인 도착 시간"입니다.
    - $$ T_{virtual} = \frac{Offset \times 8}{Bitrate} + T_{start} $$

### 2.2. 지터 종류 (Jitter Types)

#### A. Timing Jitter (PCR Accuracy)
전체 시스템 클럭의 편차를 포함한 지터입니다.
$$ J_{timing} = PCR_{actual} - T_{virtual} $$

#### B. Alignment Jitter
Timing Jitter에서 저주파 성분(Wander)을 제거한, 순수한 패킷 배치 간격의 흔들림입니다.
- **구현**: $J_{timing}$ 값에서 이동 평균(Moving Average)을 뺀 값으로 계산합니다.

---

## 3. 구현 구조 (Implementation)

### 3.1. Class: `TSJitterAnalyzer` (`scripts/zitter_measurement.py`)
Jitter 분석을 담당하는 핵심 클래스입니다.

*   **주요 속성**:
    *   `raw_pcr_data`: 수집된 PCR 데이터 리스트.
    *   `bitrate`: 선형 회귀로 역산된 스트림 전송률.
    *   `timing_jitter`, `align_jitter`: 계산된 지터 배열 (Numpy Array).
*   **주요 메서드**:
    *   `analyze_full()`: 전체 데이터를 기반으로 회귀 분석 및 지터 계산 수행.
    *   `render_graph(w, h)`: OpenCV를 이용해 MTS-430 스타일의 그래프 이미지 생성.
    *   `zoom(fx, fy)`, `pan(dx, dy)`: 그래프 뷰포트 제어.

### 3.2. GUI 통합
*   **Toolbar**: 메인 툴바에 `Jitter` 버튼이 추가되었습니다. (`ts_ui_manager.py`)
*   **Interaction**: 버튼 클릭 시 Jitter 분석 창을 팝업하거나 뷰 모드를 전환합니다. (`ts_analyzer_gui.py`)

## 4. UI 구성 (User Interface)

*   **Graph View**:
    *   **X축**: 시간 (Time, sec).
    *   **Y축**: 지터 (Jitter, ns).
    *   **Color**: Cyan (Timing), Yellow (Alignment).
*   **Controls**:
    *   Zoom In/Out, Pan (마우스 조작).
    *   Auto Scale (데이터 범위에 맞춤).

## 5. 참고 (Reference)
*   **ISO/IEC 13818-1**: PCR 허용 오차는 **±500ns**입니다.
*   그래프 상에 ±500ns 지점에 붉은 점선(Limit Line)을 표시하여 규격 준수 여부를 직관적으로 보여줍니다.

## 6. 구현 현황 (Status) - 2025-12-01
*   **Analysis Logic**: `TSJitterAnalyzer` 클래스에 Timing Jitter 및 Alignment Jitter 계산 로직 구현 완료.
*   **Report Integration**: `BScan` 리포트에 PCR Accuracy (Timing Jitter) 및 Alignment Jitter 수치(Max/Min ns) 출력 기능 통합.
*   **ETR-290 Integration**: Jitter 측정값을 `TSETR290Analyzer`로 전달하여 `PCR_accuracy_error` 판정에 활용.
