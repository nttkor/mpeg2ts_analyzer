import cv2
import numpy as np
import collections

# MTS-430 Style Color Palette (BGR)
COLOR_BG = (30, 30, 30)          # Dark Grey Background
COLOR_GRID = (60, 60, 60)        # Grid Lines
COLOR_AXIS = (150, 150, 150)     # Axis Text
COLOR_TIMING = (255, 255, 0)     # Cyan (Timing Jitter)
COLOR_ALIGN = (0, 255, 255)      # Yellow (Alignment Jitter)
COLOR_LIMIT = (0, 0, 255)        # Red (Limit Lines)
COLOR_TEXT = (0, 255, 0)         # Green Text

class TSJitterAnalyzer:
    def __init__(self):
        # Data Containers
        self.raw_pcr_data = []  # List of (byte_offset, pcr_value_seconds)
        
        # Calculated Results
        self.time_points = []   # X축 데이터 (seconds)
        self.timing_jitter = [] # Y축 데이터 1 (nanoseconds)
        self.align_jitter = []  # Y축 데이터 2 (nanoseconds)
        
        # Stats
        self.bitrate = 0.0
        self.max_jitter = 0.0
        self.min_jitter = 0.0
        
        # Viewport Control (Zoom/Pan)
        self.offset_x = 0.0     # Time Start (seconds)
        self.scale_x = 10.0     # Pixels per Second (Default Zoom)
        self.center_y = 0.0     # Jitter 0 position (relative to center)
        self.scale_y = 0.5      # Pixels per Nanosecond (1000ns = 500px)
        
        self.is_analyzed = False
        
        # Interaction State
        self.dragging = False
        self.last_mouse_pos = (0, 0)

    def reset(self):
        self.raw_pcr_data = []
        self.time_points = []
        self.timing_jitter = []
        self.align_jitter = []
        self.is_analyzed = False

    def add_pcr_data(self, offset, pcr_val):
        """
        PCR 데이터를 수집합니다.
        offset: 파일 내 바이트 위치
        pcr_val: 27MHz 기준 PCR raw value 또는 초 단위 시간
        """
        # 만약 raw value라면 초 단위로 변환 (여기서는 일단 초 단위로 들어온다고 가정하거나 변환)
        # pcr_seconds = pcr_val / 27_000_000.0 if pcr_val > 100000 else pcr_val
        self.raw_pcr_data.append((offset, pcr_val))

    def analyze_full(self):
        """
        [The Trick] 선형 회귀를 통해 Bitrate를 역산하고 지터를 계산합니다.
        """
        if len(self.raw_pcr_data) < 2:
            return

        # 1. 데이터 준비
        data = np.array(self.raw_pcr_data)
        x_offsets = data[:, 0]
        y_times = data[:, 1] # PCR Time

        # 2. 선형 회귀 (Linear Regression) : Find Ideal CBR Line
        # y = slope * x + intercept
        # slope (sec/byte) = 1 / ByteRate
        slope, intercept = np.polyfit(x_offsets, y_times, 1)
        
        self.bitrate = (1.0 / slope) * 8 # bits per second

        # 3. Jitter 계산
        # Ideal Time = slope * offset + intercept
        ideal_times = slope * x_offsets + intercept
        
        # Timing Jitter (Seconds) -> Nanoseconds
        jitter_seconds = y_times - ideal_times
        jitter_ns = jitter_seconds * 1_000_000_000

        self.time_points = y_times
        self.timing_jitter = jitter_ns
        
        # 4. Alignment Jitter (Remove Low Frequency Drift)
        # 간단한 Moving Average 제거 방식 사용 (Window size: 50 samples)
        window = 50
        if len(jitter_ns) > window:
            moving_avg = np.convolve(jitter_ns, np.ones(window)/window, mode='same')
            self.align_jitter = jitter_ns - moving_avg
        else:
            self.align_jitter = jitter_ns

        self.max_jitter = np.max(jitter_ns)
        self.min_jitter = np.min(jitter_ns)
        self.is_analyzed = True
        
        # 초기 뷰 자동 설정
        self.auto_scale()

    def auto_scale(self):
        if not self.is_analyzed:
            return
            
        # X축: 전체 시간 범위
        duration = self.time_points[-1] - self.time_points[0]
        if duration == 0: duration = 1.0
        
        # 화면 너비가 대략 800px이라고 가정할 때
        self.scale_x = 800.0 / duration
        self.offset_x = self.time_points[0]
        
        # Y축: Jitter 범위 (여유분 20%)
        jitter_range = max(abs(self.max_jitter), abs(self.min_jitter)) * 2
        if jitter_range == 0: jitter_range = 1000 # Default 1000ns
        
        # 화면 높이가 대략 400px이라고 가정할 때
        self.scale_y = 300.0 / jitter_range
        self.center_y = 0 # 중앙

    def render_graph(self, width, height):
        """
        MTS-430 스타일로 그래프를 그립니다.
        """
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = COLOR_BG
        
        cx = width // 2
        cy = height // 2
        
        # --- Grid Drawing ---
        # Y축 그리드 (Jitter) - 500ns 단위
        grid_ns_step = 500
        y_step_px = int(grid_ns_step * self.scale_y)
        if y_step_px < 20: grid_ns_step = 1000; y_step_px = int(grid_ns_step * self.scale_y)
        
        # 0선 (Center)
        base_y = cy + int(self.center_y * self.scale_y)
        cv2.line(img, (0, base_y), (width, base_y), COLOR_AXIS, 1)
        
        # +/- 그리드
        for i in range(1, 10):
            offset = i * y_step_px
            # Positive
            cv2.line(img, (0, base_y - offset), (width, base_y - offset), COLOR_GRID, 1)
            cv2.putText(img, f"{i*grid_ns_step}ns", (5, base_y - offset - 2), cv2.FONT_HERSHEY_PLAIN, 0.8, COLOR_AXIS, 1)
            # Negative
            cv2.line(img, (0, base_y + offset), (width, base_y + offset), COLOR_GRID, 1)
            cv2.putText(img, f"-{i*grid_ns_step}ns", (5, base_y + offset - 2), cv2.FONT_HERSHEY_PLAIN, 0.8, COLOR_AXIS, 1)

        # X축 그리드 (Time) - 1초/0.1초 단위 (Zoom에 따라 다름)
        # TODO: 시간 그리드 로직 추가

        # ISO Limit Lines (+/- 500ns)
        limit_px = int(500 * self.scale_y)
        cv2.line(img, (0, base_y - limit_px), (width, base_y - limit_px), COLOR_LIMIT, 1, cv2.LINE_AA)
        cv2.line(img, (0, base_y + limit_px), (width, base_y + limit_px), COLOR_LIMIT, 1, cv2.LINE_AA)

        if not self.is_analyzed:
            cv2.putText(img, "No Data / Waiting for Analysis...", (cx - 100, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1)
            return img

        # --- Graph Plotting ---
        # Data Transformation to Screen Coordinates
        # X: (time - offset_x) * scale_x
        # Y: base_y - (jitter * scale_y)
        
        # 화면에 보일 범위만 필터링 (Clipping)
        view_start_time = self.offset_x
        view_end_time = self.offset_x + (width / self.scale_x)
        
        # 이진 탐색 등으로 최적화 가능하지만 일단 Numpy 마스킹 사용
        mask = (self.time_points >= view_start_time) & (self.time_points <= view_end_time)
        
        valid_times = self.time_points[mask]
        valid_timing = self.timing_jitter[mask]
        valid_align = self.align_jitter[mask]

        if len(valid_times) > 0:
            # Vectorized Coordinate Calculation
            x_coords = ((valid_times - self.offset_x) * self.scale_x).astype(np.int32)
            
            # 1. Draw Timing Jitter (Cyan)
            y_timing = (base_y - (valid_timing * self.scale_y)).astype(np.int32)
            pts_timing = np.column_stack((x_coords, y_timing))
            cv2.polylines(img, [pts_timing], False, COLOR_TIMING, 1, cv2.LINE_AA)
            
            # 2. Draw Alignment Jitter (Yellow)
            y_align = (base_y - (valid_align * self.scale_y)).astype(np.int32)
            pts_align = np.column_stack((x_coords, y_align))
            cv2.polylines(img, [pts_align], False, COLOR_ALIGN, 1, cv2.LINE_AA)

        # --- Info Display ---
        info_text = f"Bitrate: {self.bitrate/1_000_000:.2f} Mbps | Max: {self.max_jitter:.0f}ns | Min: {self.min_jitter:.0f}ns"
        cv2.putText(img, info_text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1)
        
        # Zoom Level
        zoom_text = f"Scale: {self.scale_x:.1f} px/sec"
        cv2.putText(img, zoom_text, (width - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_AXIS, 1)

        return img

    # --- Interaction Handlers ---
    def zoom(self, factor_x, factor_y, center_px_x=0):
        # Zoom X around mouse pointer
        # New Scale
        new_scale_x = self.scale_x * factor_x
        
        # Adjust Offset to keep mouse center
        # world_x = offset_x + px / scale
        world_x = self.offset_x + (center_px_x / self.scale_x)
        self.offset_x = world_x - (center_px_x / new_scale_x)
        self.scale_x = new_scale_x

        self.scale_y *= factor_y

    def pan(self, dx, dy):
        # DX pixels -> Seconds
        dt = dx / self.scale_x
        self.offset_x -= dt # Drag left = Move time right
        
        # DY pixels -> Jitter offset (visual shift)
        self.center_y += dy # 단순 화면 이동
