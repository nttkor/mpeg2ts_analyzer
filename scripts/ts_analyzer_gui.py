"""
[파일 개요]
MPEG2-TS 분석기 GUI (AnalyzerGUI)
OpenCV를 사용하여 계측기 스타일의 분석 화면을 제공합니다.
- 좌측: PAT / PMT (2분할)
- 우측: Detail / PES / Hex (3분할)
- 하단: 타임라인 컨트롤
"""
import cv2
import numpy as np
import os
import sys
import importlib.util

# Core 및 Scanner 모듈 import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ts_parser_core import TSParser
from ts_scanner import TSScanner

# --- GUI 설정 ---
FONT_BTN = 0.6
FONT_HEX = 0.35
FONT_TREE = 0.4
COLOR_BG = (30, 30, 30)

class AnalyzerGUI:
    def __init__(self, file_path):
        self.parser = TSParser(file_path)
        self.scanner = TSScanner(self.parser)
        self.window_name = "MPEG2-TS Advanced Analyzer"
        
        # Playback State
        self.current_pkt_idx = 0
        self.playing = False
        self.speed = 1.0
        
        self.selected_program = None
        self.selected_pid = None
        
        self.hover_btn = None
        self.current_hex_data = b''
        self.show_report = False
        self.bscan_running = False

        # Buttons (Toolbar)
        base_y = 10
        h = 40
        self.buttons = [
            {'name': 'bscan', 'label': 'BScan', 'rect': (20, base_y, 90, base_y+h)},
            {'name': 'rev', 'label': '<<', 'rect': (110, base_y, 170, base_y+h)},
            {'name': 'play', 'label': '>', 'rect': (190, base_y, 250, base_y+h)},
            {'name': 'ff', 'label': '>>', 'rect': (270, base_y, 330, base_y+h)},
            {'name': 'stop', 'label': 'STOP', 'rect': (350, base_y, 410, base_y+h)},
            {'name': 'ext_play', 'label': 'Video Win', 'rect': (430, base_y, 530, base_y+h)},
        ]

    def run(self):
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_cb)
        
        self.parser.quick_scan(limit=20000)
        
        self.current_pkt_idx = 0
        self.playing = False
        self.update_packet_view()

        while True:
            img = np.zeros((900, 1400, 3), dtype=np.uint8)
            img[:] = COLOR_BG
            
            self.draw_layout(img)
            
            if not self.scanner.running and self.bscan_running:
                self.bscan_running = False
                self.show_report = True
                if "Completed" in self.parser.last_log:
                    self.parser.last_log = "Report Generated."

            if self.show_report:
                self._draw_report_overlay(img)
            
            cv2.imshow(self.window_name, img)
            
            key = self._handle_playback()
            if key == ord('q'): break
            elif key == 32: self._toggle_play()
            elif key == ord('p'): self._launch_player()
            elif key == ord(','): self._handle_btn('prev')
            elif key == ord('.'): self._handle_btn('next')
            
            if self.show_report and key != 255:
                self.show_report = False

        self.scanner.stop()
        cv2.destroyAllWindows()

    def draw_layout(self, img):
        # Toolbar
        cv2.rectangle(img, (0, 0), (1400, 60), (50, 50, 50), -1)
        self._draw_controls(img)
        
        # Left: PAT / PMT (2분할, 높이 420씩)
        self._draw_pat_view(img, 0, 60, 400, 420)
        self._draw_pmt_view(img, 0, 480, 400, 420)
        
        # Right: Detail / PES / Hex (3분할, 높이 280씩)
        self._draw_detail(img, 400, 60, 1000, 280)
        self._draw_pes_view(img, 400, 340, 1000, 280)
        self._draw_hex(img, 400, 620, 1000, 280)

    def _draw_pat_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (40, 40, 40), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (100, 100, 100), 1)
        cv2.putText(img, "PAT (Programs)", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cur_y = y + 50
        for prog_num, prog in self.parser.programs.items():
            color = (200, 200, 200)
            if self.selected_program == prog_num:
                color = (0, 255, 255) # Cyan (Selected)
                cv2.rectangle(img, (x+5, cur_y-15), (x+w-5, cur_y+5), (60, 60, 80), -1)
            
            text = f"Program {prog_num} (PMT PID: 0x{prog['pmt_pid']:X})"
            cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            cur_y += 25

    def _draw_pmt_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (30, 30, 35), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (100, 100, 100), 1)
        
        title = "PMT (Components)"
        if self.selected_program: title += f" - Prog {self.selected_program}"
        cv2.putText(img, title, (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        cur_y = y + 50
        if self.selected_program and self.selected_program in self.parser.programs:
            prog = self.parser.programs[self.selected_program]
            
            cv2.putText(img, f"[PMT] PID 0x{prog['pmt_pid']:X}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
            cur_y += 25
            
            for pid, info in prog['pids'].items():
                color = (200, 200, 200)
                if "Video" in info['desc']: color = (0, 255, 255)
                elif "Audio" in info['desc']: color = (0, 255, 0)
                
                if self.selected_pid == pid:
                    color = (255, 100, 100) # Red (Selected)
                    cv2.rectangle(img, (x+5, cur_y-15), (x+w-5, cur_y+5), (60, 60, 80), -1)
                
                cnt = self.parser.pid_counts.get(pid, 0)
                text = f"PID 0x{pid:X} : {info['desc']} ({cnt})"
                cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
                cur_y += 25
        else:
            cv2.putText(img, "Select a Program above.", (x+50, y+50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    def _draw_pes_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (35, 35, 40), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80, 80, 80), 1)
        cv2.putText(img, "PES / Section Analysis", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cur_y = y + 50
        if self.selected_pid:
            info = self.parser.pid_map.get(self.selected_pid, {})
            cv2.putText(img, f"Selected PID: 0x{self.selected_pid:X} ({info.get('desc', 'Unknown')})", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cur_y += 30
            cv2.putText(img, "Analysis info will appear here...", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
        else:
            cv2.putText(img, "Select a PID to analyze.", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    def _draw_detail(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (35, 35, 45), -1)
        cv2.putText(img, "Packet / PID Detail", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        
        cur_y = y + 50
        if self.current_hex_data:
            import struct
            header_bytes = struct.unpack('>I', self.current_hex_data[:4])[0]
            tei = (header_bytes >> 23) & 0x1
            pusi = (header_bytes >> 22) & 0x1
            prio = (header_bytes >> 21) & 0x1
            pid = (header_bytes >> 8) & 0x1FFF
            scram = (header_bytes >> 6) & 0x3
            adapt = (header_bytes >> 4) & 0x3
            cnt = header_bytes & 0xF
            
            cv2.putText(img, f"[Packet Info] Index: {self.current_pkt_idx}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            cur_y += 25
            cv2.putText(img, f"PID: 0x{pid:04X} ({pid})   CC: {cnt}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
            cur_y += 25
            
            # Flags
            flags_str = f"TEI: {tei}  PUSI: {pusi}  Prio: {prio}  Scram: {scram}"
            cv2.putText(img, flags_str, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,200), 1)
            cur_y += 25
            
            # Adaptation
            adapt_desc = ["Rsrv", "Payload Only", "Adapt Only", "Adapt + Payload"][adapt]
            cv2.putText(img, f"Adaptation: {adapt} ({adapt_desc})", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,200), 1)
            cur_y += 30
            
            if pid in self.parser.pid_map:
                info = self.parser.pid_map[pid]
                cv2.putText(img, f"[Type] {info['desc']}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100,255,100), 1)

    def _draw_hex(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (20, 20, 20), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80, 80, 80), 1)
        cv2.putText(img, "Packet Binary Data (188 Bytes)", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
        
        if not self.current_hex_data: return
        
        sy = y + 50
        for i in range(0, 188, 16):
            chunk = self.current_hex_data[i:i+16]
            hexs = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join((chr(b) if 32<=b<127 else ".") for b in chunk)
            ly = sy + (i//16)*20
            cv2.putText(img, f"{i:02X}:", (x+10, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (150, 150, 150), 1)
            cv2.putText(img, hexs, (x+50, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (200,200,200), 1)
            cv2.putText(img, asc, (x+350, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (100,255,100), 1)

    def _draw_controls(self, img):
        for btn in self.buttons:
            x1, y1, x2, y2 = btn['rect']
            color = (60, 60, 60)
            if btn == self.hover_btn: color = (80, 80, 80)
            
            label = btn['label']
            if btn['name'] == 'play':
                label = "||" if self.playing else ">"
                if self.playing: color = (0, 100, 0)
            elif btn['name'] == 'rev':
                label = "<<" if self.playing else "<-"
            elif btn['name'] == 'ff':
                label = ">>" if self.playing else "->"
            elif btn['name'] == 'bscan':
                label = "Scanning..." if self.scanner.running else "BScan"
                if self.scanner.running: 
                    color = (0, 150, 0)
                    self.bscan_running = True # 상태 업데이트
                else: color = (50, 50, 50)
            
            cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), (150, 150, 150), 1)
            
            ts = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
            tx = x1 + (x2-x1-ts[0])//2
            ty = y1 + (y2-y1+ts[1])//2
            cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

        status_text = "READY"
        status_color = (200, 200, 200)
        if self.scanner.running:
            status_text = "SCANNING..."
            status_color = (0, 255, 0)
        elif self.playing:
            status_text = f"PLAYING (x{self.speed})"
            status_color = (0, 255, 255)
        elif self.current_pkt_idx > 0:
            status_text = "PAUSED"
            status_color = (255, 255, 0)
        cv2.putText(img, status_text, (700, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

    def _draw_report_overlay(self, img):
        overlay = img.copy()
        cv2.rectangle(overlay, (200, 100), (1200, 800), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.85, img, 0.15, 0, img)
        cv2.rectangle(img, (200, 100), (1200, 800), (0, 255, 255), 2)
        
        if hasattr(self.scanner, 'report') and self.scanner.report:
            cv2.putText(img, "Scan Completed - Press any key to close", (250, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            y = 180
            for line in self.scanner.report[:20]:
                text = line.replace("|", " ").strip()
                cv2.putText(img, text, (250, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y += 30

    def _mouse_cb(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            self.hover_btn = None
            for btn in self.buttons:
                x1, y1, x2, y2 = btn['rect']
                if x1<=x<=x2 and y1<=y<=y2:
                    self.hover_btn = btn
                    break
        elif event == cv2.EVENT_LBUTTONDOWN:
            if self.hover_btn:
                self._handle_btn(self.hover_btn['name'])
            else:
                # Tree View Selection (간단 구현)
                # PAT 영역 (y: 60~480)
                if 0 <= x <= 400 and 60 <= y <= 480:
                    # 클릭 위치로 대략적인 인덱스 계산 (높이 25px 가정)
                    idx = (y - 110) // 25
                    if idx >= 0:
                        progs = list(self.parser.programs.keys())
                        if idx < len(progs):
                            self.selected_program = progs[idx]
                            self.selected_pid = None # PMT 초기화
                
                # PMT 영역 (y: 480~900)
                elif 0 <= x <= 400 and 480 <= y <= 900:
                    if self.selected_program:
                        idx = (y - 530) // 25
                        prog = self.parser.programs[self.selected_program]
                        # PMT PID + Components 리스트
                        items = [prog['pmt_pid']] + list(prog['pids'].keys())
                        if 0 <= idx < len(items):
                            self.selected_pid = items[idx]

    def _handle_btn(self, name):
        if name == 'play': self._toggle_play()
        elif name == 'stop': 
            self.playing = False
            self.current_pkt_idx = 0
            self.update_packet_view()
        elif name == 'rev':
            if self.playing: self.speed = -1.0
            else: self._step_packet(-1)
        elif name == 'ff':
            if self.playing: self.speed = 2.0
            else: self._step_packet(1)
        elif name == 'ext_play':
            self._launch_player()
        elif name == 'bscan':
            if self.scanner.running: self.scanner.stop()
            else: self.scanner.start()
        elif name == 'prev': self._step_packet(-1)
        elif name == 'next': self._step_packet(1)

    def _toggle_play(self):
        self.playing = not self.playing
        if self.playing: self.speed = 1.0

    def _step_packet(self, step):
        self.playing = False
        
        # PID 필터링 이동
        if self.selected_pid is None:
            self.current_pkt_idx = max(0, self.current_pkt_idx + step)
        else:
            # 선택된 PID 탐색 모드
            target_pid = self.selected_pid
            search_dir = 1 if step > 0 else -1
            temp_idx = self.current_pkt_idx
            found = False
            max_search = 100000 # 최대 탐색 범위
            
            for _ in range(max_search):
                temp_idx += search_dir
                if temp_idx < 0: break
                
                data = self.parser.read_packet_at(temp_idx)
                if not data: break # EOF
                
                pid, _, _, _ = self.parser.parse_header(data)
                if pid == target_pid:
                    self.current_pkt_idx = temp_idx
                    found = True
                    break
            
            if not found:
                print(f"PID 0x{target_pid:X} not found in direction {search_dir}")

        self.update_packet_view()

    def update_packet_view(self):
        data = self.parser.read_packet_at(self.current_pkt_idx)
        if data: self.current_hex_data = data

    def _handle_playback(self):
        wait = 50
        if self.playing:
            self.current_pkt_idx += int(self.speed)
            if self.current_pkt_idx < 0: self.current_pkt_idx = 0
            self.update_packet_view()
            if self.speed == 1.0: wait = 10
            else: wait = 1
        return cv2.waitKey(wait) & 0xFF

    def _launch_player(self):
        try:
            spec = importlib.util.spec_from_file_location("play_ts_opencv", os.path.join(os.path.dirname(__file__), "play_ts_opencv.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.main()
        except: pass

if __name__ == "__main__":
    ts_file = r"D:\git\mpeg2TS\TS\mama_uhd2.ts"
    app = AnalyzerGUI(ts_file)
    app.run()
