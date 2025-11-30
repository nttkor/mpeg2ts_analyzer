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
from ts_ui_manager import UIManager

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
        
        self.mouse_x = 0
        self.mouse_y = 0
        self.current_hex_data = b''
        self.show_report = False
        self.bscan_running = False
        
        # UI Manager 초기화
        self.ui = UIManager(self)
        if file_path:
            self.ui.add_recent(file_path)

    def run(self):
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_cb)
        
        # Initializing Screen
        img = np.zeros((900, 1400, 3), dtype=np.uint8)
        img[:] = COLOR_BG
        cv2.putText(img, "Initializing...", (600, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
        cv2.imshow(self.window_name, img)
        cv2.waitKey(10)
        
        self.parser.quick_scan(limit=20000)
        
        # Auto Select First Program & PMT
        if self.parser.programs:
            first_prog_id = list(self.parser.programs.keys())[0]
            self.selected_program = first_prog_id
            
            prog_info = self.parser.programs[first_prog_id]
            if prog_info['pids']:
                # Select first ES PID
                first_pid = list(prog_info['pids'].keys())[0]
                self.selected_pid = first_pid
        
        self.current_pkt_idx = 0
        self.playing = False
        self.update_packet_view()

        while True:
            # OpenCV Window X 버튼(닫기) 감지
            try:
                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except: pass

            img = np.zeros((900, 1400, 3), dtype=np.uint8)
            img[:] = COLOR_BG
            
            self.draw_layout(img)
            
            # BScan 상태 관리
            if self.scanner.running:
                # 스캔 중일 때는 플래그 유지
                pass
            elif self.bscan_running:
                # 스캔이 방금 끝났거나(scanner.completed=True), 완료된 상태에서 버튼을 누른 경우
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
        self.ui.draw_toolbar(img)
        
        # Left: PAT / PMT (2분할, 높이 420씩)
        self._draw_pat_view(img, 0, 60, 400, 420)
        self._draw_pmt_view(img, 0, 480, 400, 420)
        
        # Right: Detail / PES / Hex (3분할, 높이 280씩)
        self._draw_detail(img, 400, 60, 1000, 280)
        self._draw_pes_view(img, 400, 340, 1000, 280)
        
        if self.scanner.running:
            self._draw_scan_status(img, 400, 620, 1000, 280)
        else:
            self._draw_hex(img, 400, 620, 1000, 280)

        # Draw Menu Overlay (Always on top)
        if self.ui.menu_open:
            self.ui.draw_menu(img)

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
            
            thickness = 1
            if x <= self.mouse_x <= x+w and cur_y-20 <= self.mouse_y <= cur_y+5:
                thickness = 2
                
            cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, thickness)
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
                
                thickness = 1
                if x <= self.mouse_x <= x+w and cur_y-20 <= self.mouse_y <= cur_y+5:
                    thickness = 2

                cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, thickness)
                cur_y += 25
        else:
            cv2.putText(img, "Select a Program above.", (x+50, y+50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    def _draw_pes_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (35, 35, 40), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80, 80, 80), 1)
        cv2.putText(img, "PES / Section Analysis", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cur_y = y + 50
        if not self.selected_pid:
            cv2.putText(img, "Select a PID to analyze.", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
            return

        # PID 및 기본 정보 표시
        info = self.parser.pid_map.get(self.selected_pid, {})
        cv2.putText(img, f"Selected PID: 0x{self.selected_pid:X} ({info.get('desc', 'Unknown')})", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cur_y += 30

        # 현재 패킷 데이터 확인
        if not self.current_hex_data: return
        
        # 헤더 파싱 및 TS 정보 요약
        pid, pusi, adapt, cnt = self.parser.parse_header(self.current_hex_data)
        import struct
        hdr_val = struct.unpack('>I', self.current_hex_data[:4])[0]
        scram = (hdr_val >> 6) & 0x3
        
        if pid != self.selected_pid:
            cv2.putText(img, "Current packet does not match selected PID.", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 150), 1)
            return
            
        # TS Header Summary (허전함 보완)
        ts_info = f"[TS Header] PUSI: {pusi} | CC: {cnt:02d} | Scram: {scram} | Adapt: {adapt}"
        cv2.putText(img, ts_info, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cur_y += 30

        # Payload 추출
        off = 4
        if adapt & 0x2: off = 5 + self.current_hex_data[4]
        
        payload = b''
        if off < 188:
            payload = self.current_hex_data[off:]

        # PES 분석 및 출력
        if pusi:
            # PES Start
            cv2.putText(img, ">> PES Packet Start <<", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cur_y += 25
            
            pes_info = self.parser.parse_pes_header(payload)
            if pes_info:
                # Stream ID
                sid = pes_info['stream_id']
                sid_desc = "Unknown"
                if 0xC0 <= sid <= 0xDF: sid_desc = f"Audio {sid & 0x1F}"
                elif 0xE0 <= sid <= 0xEF: sid_desc = f"Video {sid & 0x0F}"
                elif sid == 0xBD: sid_desc = "Private 1 (AC3/DTS)"
                
                cv2.putText(img, f"Stream ID: 0x{sid:02X} ({sid_desc})", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                cur_y += 25
                
                # PES Length & Structure
                plen = pes_info['pes_length']
                len_str = f"{plen} bytes" if plen > 0 else "Unknown (0)"
                
                # 패킷 구조 판별
                struct_str = "Multi-Packet (Start)"
                est_pkts = ""
                
                if plen > 0:
                    if (plen + 6) <= len(payload):
                        struct_str = "Single Packet (Complete)"
                    else:
                        # 예상 패킷 수 (헤더 제외 184바이트 기준 대략 계산)
                        count = (plen + 6) / 184.0
                        est_pkts = f" (Needs ~{count:.1f} packets)"
                
                cv2.putText(img, f"PES Len: {len_str}{est_pkts}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)
                cur_y += 25
                cv2.putText(img, f"Type: {struct_str}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 150, 150), 1)
                cur_y += 25
                
                # PTS / DTS
                if pes_info['pts'] is not None:
                    pts_val = pes_info['pts'] / 90000.0
                    dts_str = ""
                    if pes_info['dts'] is not None:
                        dts_val = pes_info['dts'] / 90000.0
                        dts_str = f"  DTS: {dts_val:.3f}s"
                    
                    cv2.putText(img, f"PTS: {pts_val:.3f}s{dts_str}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                    cur_y += 25
            else:
                 cv2.putText(img, "Invalid or Non-PES Header", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1)

        else:
            # PES Continuation
            cv2.putText(img, ">> PES Continuation <<", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2)
            cur_y += 25
            cv2.putText(img, "Part of Multi-Packet PES", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cur_y += 25
            
            # Simple Audio Sync Check
            if len(payload) > 2:
                for i in range(len(payload)-1):
                    # MP2/ADTS (FFF) Check
                    if payload[i] == 0xFF and (payload[i+1] & 0xF0) == 0xF0:
                        cv2.putText(img, f"[Audio Sync] Found at offset {i} (0xFFF...)", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                        break

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
                label = "Stop" if self.scanner.running else "BScan"
                if self.scanner.running: 
                    color = (0, 100, 0)
                elif self.scanner.completed:
                    label = "Report" # 완료되면 Report 보기 버튼으로 변경해도 좋음
                    color = (0, 100, 100)
                else: color = (50, 50, 50)
            
            # Hover Effect (배경색 밝게 + 테두리 강조)
            border_color = (150, 150, 150)
            thickness = 1
            
            if btn == self.hover_btn:
                if not (btn['name'] == 'bscan' and self.scanner.running) and not (btn['name'] == 'play' and self.playing):
                     color = (90, 90, 110)
                border_color = (0, 255, 255)
                thickness = 2

            cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), border_color, thickness)
            
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

    def _draw_scan_status(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (30, 40, 30), -1) # 약간 녹색 틴트 배경
        cv2.rectangle(img, (x, y), (x+w, y+h), (0, 200, 0), 1)
        
        cv2.putText(img, "Background Scanning in Progress...", (x+20, y+40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # 진행률 계산
        total_pkts = self.parser.file_size // 188
        current = self.parser.packet_count
        progress = 0.0
        if total_pkts > 0:
            progress = min(1.0, current / total_pkts)
            
        # Progress Bar
        bar_x = x + 50
        bar_y = y + 80
        bar_w = w - 100
        bar_h = 30
        
        cv2.rectangle(img, (bar_x, bar_y), (bar_x+bar_w, bar_y+bar_h), (60, 60, 60), -1)
        fill_w = int(bar_w * progress)
        cv2.rectangle(img, (bar_x, bar_y), (bar_x+fill_w, bar_y+bar_h), (0, 200, 0), -1)
        
        # 텍스트 정보
        percent = int(progress * 100)
        status = f"Scanned: {current:,} / {total_pkts:,} Packets ({percent}%)"
        cv2.putText(img, status, (bar_x, bar_y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # 안내 문구
        cv2.putText(img, "The GUI remains responsive. You can continue to analyze packets.", (bar_x, bar_y + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    def _mouse_cb(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            self.ui.handle_mouse_move(x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            # 1. Menu & Button Click (Delegated to UIManager)
            if self.ui.handle_click(x, y):
                return

            # 2. Tree View Selection
            # PAT 영역 (y: 60~480)
            if 0 <= x <= 400 and 60 <= y <= 480:
                cur_y = 60 + 50
                for prog_num in self.parser.programs.keys():
                    if cur_y - 20 <= y <= cur_y + 5:
                        self.selected_program = prog_num
                        self.selected_pid = None # PMT 초기화
                        break
                    cur_y += 25
            
            # PMT 영역 (y: 480~900)
            elif 0 <= x <= 400 and 480 <= y <= 900:
                if self.selected_program and self.selected_program in self.parser.programs:
                    prog = self.parser.programs[self.selected_program]
                    cur_y = 480 + 50
                    
                    # 1. PMT PID Check
                    if cur_y - 20 <= y <= cur_y + 5:
                        self.selected_pid = prog['pmt_pid']
                    else:
                        # 2. Components Check
                        cur_y += 25
                        for pid in prog['pids'].keys():
                            if cur_y - 20 <= y <= cur_y + 5:
                                self.selected_pid = pid
                                break
                            cur_y += 25

    def _handle_btn(self, name):
        if name == 'file':
            self.menu_open = not self.menu_open
        elif name == 'play': self._toggle_play()
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
            if self.scanner.running: 
                self.scanner.stop()
            elif self.scanner.completed:
                self.bscan_running = True # 리포트 오버레이 트리거
            else: 
                self.scanner.start()
        elif name == 'prev': self._step_packet(-1)
        elif name == 'next': self._step_packet(1)

    def _handle_menu(self, action):
        if action == 'exit':
            sys.exit(0)
        elif action == 'open':
            self._open_file()
        elif action.startswith('recent_'):
            idx = int(action.split('_')[1])
            if idx < len(self.recent_files):
                self._open_file(self.recent_files[idx])

    def _open_file(self, path=None):
        if not path:
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askopenfilename(filetypes=[("MPEG2-TS Files", "*.ts;*.tp;*.m2ts"), ("All Files", "*.*")])
            root.destroy()
        
        if not path or not os.path.exists(path): return
        
        # Reset Logic
        if self.scanner.running: self.scanner.stop()
        
        # Re-initialize
        self.parser = TSParser(path)
        self.scanner = TSScanner(self.parser)
        self._add_recent(path)
        
        # Reset State
        self.current_pkt_idx = 0
        self.playing = False
        self.selected_program = None
        self.selected_pid = None
        self.bscan_running = False
        self.show_report = False
        
        # Init Scan (UI blocking for short time)
        self.parser.quick_scan(limit=20000)
        
        if self.parser.programs:
            first = list(self.parser.programs.keys())[0]
            self.selected_program = first
            if self.parser.programs[first]['pids']:
                self.selected_pid = list(self.parser.programs[first]['pids'].keys())[0]
                
        self.update_packet_view()

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
        wait = 10 # 기본 대기 시간 단축 (반응성 향상)
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
