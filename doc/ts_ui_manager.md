# UI Manager Documentation

## 1. 개요
**UIManager**는 `ts_analyzer_gui.py`의 복잡도를 줄이기 위해, GUI의 **화면 그리기(Drawing)** 및 **사용자 입력 처리(Input Handling)** 로직을 분리한 모듈입니다.
OpenCV 기반의 UI 요소(버튼, 메뉴, 오버레이)를 관리하며, 메인 컨트롤러(`AnalyzerGUI`)와 상호작용합니다.

## 2. 주요 역할
- **Toolbar 관리**: 재생, 탐색, BScan 등 상단 툴바 버튼의 배치 및 상태별 렌더링.
- **Menu System**: `File` 버튼 클릭 시 드롭다운 메뉴(Open, Recent Files, Exit) 표시 및 동작 처리.
- **Mouse Event**: 마우스 이동(Hover 효과) 및 클릭 이벤트를 감지하여 적절한 액션 수행.
- **Recent Files**: 최근 열어본 파일 목록을 `recent_files.json`에 저장하고 불러오기.

## 3. 클래스 구조 (`ts_ui_manager.py`)

### `UIManager` Class
#### 초기화
- `__init__(self, gui_context)`: 메인 GUI 인스턴스를 참조로 받아 상태값(재생 여부, 스캐너 상태 등)에 접근합니다.

#### UI 그리기 메서드
- `draw_toolbar(img)`: 상단 툴바와 상태 메시지(READY, SCANNING...)를 그립니다.
- `draw_menu(img)`: 메뉴가 열려있을 때(`menu_open=True`) 오버레이 메뉴를 그립니다.

#### 입력 처리 메서드
- `handle_mouse_move(x, y)`: 마우스 좌표를 갱신하고 버튼 호버 상태를 판별합니다.
- `handle_click(x, y)`: 클릭 좌표를 분석하여 메뉴 선택 또는 버튼 클릭 이벤트를 처리합니다.
    - 처리된 경우 `True`를 반환하여 메인 GUI가 추가 처리를 하지 않도록 합니다.

#### 내부 로직
- `_handle_btn_action(name)`: 버튼별 동작(Play, Stop, BScan 등)을 수행합니다. 메인 GUI의 메서드를 호출하거나 상태를 변경합니다.
- `_open_file_dialog(path)`: 파일 열기 대화상자를 띄우거나, 특정 경로의 파일을 로드하도록 메인 GUI에 요청합니다.

## 4. 메인 GUI와의 연동
`AnalyzerGUI`는 `UIManager`를 인스턴스로 생성하여 사용합니다.

```python
# scripts/ts_analyzer_gui.py

class AnalyzerGUI:
    def __init__(self, file_path):
        self.ui = UIManager(self)  # UI 매니저 생성
        # ...

    def draw_layout(self, img):
        self.ui.draw_toolbar(img)  # 그리기 위임
        # ...
        if self.ui.menu_open:
            self.ui.draw_menu(img)

    def _mouse_cb(self, event, x, y, ...):
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.ui.handle_click(x, y):  # 입력 처리 위임
                return
```

