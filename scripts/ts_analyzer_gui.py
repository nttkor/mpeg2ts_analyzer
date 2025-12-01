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
import time
import importlib.util
import tkinter as tk
from tkinter import filedialog

# Core 및 Scanner 모듈 import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ts_parser_core import TSParser
from ts_scanner import TSScanner
from ts_ui_manager import UIManager

# --- GUI 설정 ---
FONT_BTN = 0.6
FONT_HEX = 0.45 # 0.40 -> 0.45 (폰트 더 확대)
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
        
        # Jitter Analysis State
        self.show_jitter = False
        
        # Interactive Highlight State
        self.ui_regions = []        # 매 프레임 UI 영역 정보 저장 [{'rect':(x1,y1,x2,y2), 'range':(start, end), 'color':(b,g,r), 'name':str}]
        self.hover_region = None    # 현재 마우스 오버된 영역
        self.selected_region = None # 클릭으로 고정된 영역
        
        # Filter States (PAT, PMT, Video, Audio, PCR, PTS, DTS)
        self.active_filters = {
            'PAT': False,
            'PMT': False,
            'Video': False,
            'Audio': False,
            'PCR': False,
            'PTS': False,
            'DTS': False
        }
        
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
        
        # Auto Select First Valid Program (Skip Prog 0/NIT) & PMT
        if self.parser.programs:
            # 0번이 아닌 프로그램 중 가장 먼저 나오는 것 선택
            valid_progs = [p for p in self.parser.programs.keys() if p != 0]
            if valid_progs:
                first_prog_id = sorted(valid_progs)[0]
                self.selected_program = first_prog_id
                
                prog_info = self.parser.programs[first_prog_id]
                # PMT PID 자동 선택
                self.selected_pid = prog_info['pmt_pid']
                
                # PMT 필터 활성화
                self.active_filters['PMT'] = True
                print(f"[Auto] Initial Selection: Program {first_prog_id} (PMT PID: 0x{self.selected_pid:X})")
            elif 0 in self.parser.programs:
                # 0번밖에 없으면 어쩔 수 없이 0번 선택
                self.selected_program = 0
                self.selected_pid = self.parser.programs[0]['pmt_pid']
        
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
            
            # UI 영역 초기화
            self.ui_regions = []
            
            self.draw_layout(img)
            
            # BScan 상태 관리
            if self.scanner.running:
                # 스캔 중이면 아무것도 안 함 (백그라운드 동작)
                pass
            elif self.scanner.completed and not self.show_report and self.bscan_running:
                # 스캔 완료 후 아직 리포트를 안 봤거나, 버튼 눌러서 리포트 요청 시
                self.bscan_running = False # 트리거 해제
                self.show_report = True
                self.parser.last_log = "Report Generated."

            if self.show_report:
                self._draw_report_overlay(img)
            
            self.canvas = img
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
        
        # Right: Detail / PES / Hex (3분할, 높이 조정)
        # Detail: 60 ~ 340 (280)
        # PES: 340 ~ 560 (220) - 30px 추가 축소
        # Hex: 560 ~ 900 (340) - 30px 추가 확대 및 위로 이동
        self._draw_detail(img, 400, 60, 1000, 280)
        self._draw_pes_view(img, 400, 340, 1000, 220)
        
        if self.scanner.running:
            self._draw_scan_status(img, 400, 560, 1000, 340)
        else:
            self._draw_hex(img, 400, 560, 1000, 340)

        # Draw Menu Overlay (Always on top)
        if self.ui.menu_open:
            self.ui.draw_menu(img)

    def _draw_pat_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (40, 40, 40), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (100, 100, 100), 1)
        
        prog_count = len(self.parser.programs)
        
        # [UI 개선] 타이틀 영역 하이라이트 (클릭 가능 피드백)
        title_rect_h = 30
        if 0 <= self.mouse_x - x <= w and 0 <= self.mouse_y - y <= title_rect_h:
            cv2.rectangle(img, (x, y), (x+w, y+title_rect_h), (60, 60, 60), -1)
            
        cv2.putText(img, f"PAT (Programs: {prog_count})", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cur_y = y + 50
        for prog_num, prog in self.parser.programs.items():
            color = (200, 200, 200)
            text = f"Program {prog_num} (PMT PID: 0x{prog['pmt_pid']:X})"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            
            # 텍스트 영역 정밀 계산
            # 기존: 전체 너비 체크 -> 변경: 텍스트 너비 + 여유공간 체크
            rect_x1, rect_y1 = x + 20, cur_y - th - 5
            rect_x2, rect_y2 = x + 20 + tw, cur_y + 5
            
            is_hover = (rect_x1 <= self.mouse_x <= rect_x2 and rect_y1 <= self.mouse_y <= rect_y2)
            is_selected = (self.selected_program == prog_num)
            
            if is_selected:
                color = (0, 255, 255) # Cyan
                cv2.rectangle(img, (rect_x1-5, rect_y1), (rect_x2+5, rect_y2), (60, 60, 80), -1)
            elif is_hover:
                color = (255, 255, 200) # Bright
                cv2.rectangle(img, (rect_x1-5, rect_y1), (rect_x2+5, rect_y2), (80, 80, 100), -1)
            
            thickness = 2 if is_hover or is_selected else 1
            cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, thickness)
            
            # Register Region for Click Handling (if needed globally)
            # 여기서는 로컬 렌더링 루프에서 처리하지만, 전역 클릭 처리를 위해 등록할 수도 있음
            # 하지만 _mouse_cb에서 좌표 기반으로 처리하므로 시각적 피드백만 주면 됨.
            
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
            
            # PMT PID & PCR PID Display
            pcr_pid = prog.get('pcr_pid_val', 0x1FFF)
            cv2.putText(img, f"PMT PID: 0x{prog['pmt_pid']:X} | PCR PID: 0x{pcr_pid:X}", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
            cur_y += 25
            
            for pid, info in prog['pids'].items():
                color = (200, 200, 200)
                if "Video" in info['desc']: color = (0, 255, 255)
                elif "Audio" in info['desc']: color = (0, 255, 0)
                
                text = f"PID 0x{pid:X} : {info['desc']}"
                if pid == pcr_pid: text += " (PCR)"
                cnt = self.parser.pid_counts.get(pid, 0)
                text += f" ({cnt})"
                
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                rect_x1, rect_y1 = x + 20, cur_y - th - 5
                rect_x2, rect_y2 = x + 20 + tw, cur_y + 5
                
                is_hover = (rect_x1 <= self.mouse_x <= rect_x2 and rect_y1 <= self.mouse_y <= rect_y2)
                is_selected = (self.selected_pid == pid)
                
                if is_selected:
                    color = (255, 100, 100) # Red
                    cv2.rectangle(img, (rect_x1-5, rect_y1), (rect_x2+5, rect_y2), (60, 60, 80), -1)
                elif is_hover:
                    cv2.rectangle(img, (rect_x1-5, rect_y1), (rect_x2+5, rect_y2), (80, 80, 100), -1)
                
                thickness = 2 if is_hover or is_selected else 1
                cv2.putText(img, text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, thickness)
                cur_y += 25
        else:
            cv2.putText(img, "Select a Program above.", (x+50, y+50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    def _draw_pes_view(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (35, 35, 40), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80, 80, 80), 1)
        cv2.putText(img, "PES / Section Analysis", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        cur_y = y + 50
        if self.selected_pid is None:
            cv2.putText(img, "Select a PID to analyze.", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
            return

        # PID 및 기본 정보 표시
        info = self.parser.pid_map.get(self.selected_pid, {})
        pid_text = f"Selected PID: 0x{self.selected_pid:X} ({info.get('desc', 'Unknown')})"
        cv2.putText(img, pid_text, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        
        # Helper for adding region (Defined early for reuse)
        def add_region(name, start_offset, length, text_rect):
            if not hasattr(self, 'ui_regions'): return
            
            # Check Hover/Select for highlight drawing (Feedback)
            is_active = (self.selected_region and self.selected_region['name'] == name) or \
                        (self.hover_region and self.hover_region['name'] == name)
            
            if is_active:
                cv2.rectangle(img, text_rect[:2], text_rect[2:], (100, 100, 0), -1)

            self.ui_regions.append({
                'name': name,
                'rect': text_rect,
                'range': (start_offset, start_offset + length),
                'color': (0, 255, 255)
            })

        # PES Navigation Buttons (Selected PID 옆으로 이동)
        (text_w, text_h), _ = cv2.getTextSize(pid_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        btn_start_x = x + 20 + text_w + 30 
        
        gap = 10
        btn_w = 30
        
        # 1. Prev PES Start (<<)
        btn_pes_prev_rect = (btn_start_x, cur_y - 15, btn_start_x + btn_w, cur_y + 10)
        # 2. Prev Packet (<)
        bx = btn_start_x + btn_w + gap
        btn_pkt_prev_rect = (bx, cur_y - 15, bx + btn_w, cur_y + 10)
        # 3. Next Packet (>)
        bx += btn_w + gap
        btn_pkt_next_rect = (bx, cur_y - 15, bx + btn_w, cur_y + 10)
        # 4. Next PES Start (>>)
        bx += btn_w + gap
        btn_pes_next_rect = (bx, cur_y - 15, bx + btn_w, cur_y + 10)
        
        # --- Draw Buttons ---
        for rect, label in [(btn_pes_prev_rect, '<<'), (btn_pkt_prev_rect, '<'), (btn_pkt_next_rect, '>'), (btn_pes_next_rect, '>>')]:
            color = (255, 200, 0)
            if rect[0] <= self.mouse_x <= rect[2] and rect[1] <= self.mouse_y <= rect[3]:
                color = (0, 255, 255)
                cv2.rectangle(img, (rect[0]-3, rect[1]-3), (rect[2]+3, rect[3]+3), (60, 60, 80), -1)
            
            # Simple shape drawing for buttons
            mid_y = (rect[1] + rect[3]) // 2
            
            if label == '<<':
                pts = [((rect[0]+15, rect[1]+5), (rect[0]+15, rect[3]-5), (rect[0]+2, mid_y)),
                       ((rect[0]+25, rect[1]+5), (rect[0]+25, rect[3]-5), (rect[0]+12, mid_y))]
            elif label == '<':
                pts = [((rect[2]-5, rect[1]+5), (rect[2]-5, rect[3]-5), (rect[0]+5, mid_y))]
            elif label == '>':
                pts = [((rect[0]+5, rect[1]+5), (rect[0]+5, rect[3]-5), (rect[2]-5, mid_y))]
            elif label == '>>':
                pts = [((rect[0]+5, rect[1]+5), (rect[0]+5, rect[3]-5), (rect[0]+18, mid_y)),
                       ((rect[0]+15, rect[1]+5), (rect[0]+15, rect[3]-5), (rect[0]+28, mid_y))]
            
            for p in pts:
                cv2.drawContours(img, [np.array(p)], 0, color, -1)

        cur_y += 30
        
        # PES Navigation Target 초기 등록
        self.pes_nav_targets = {
            'pes_prev': {'rect': btn_pes_prev_rect, 'idx': -2},
            'pkt_prev': {'rect': btn_pkt_prev_rect},
            'pkt_next': {'rect': btn_pkt_next_rect},
            'pes_next': {'rect': btn_pes_next_rect}
        }
        
        if not self.current_hex_data: return
        
        # 헤더 파싱 및 TS 정보 요약
        pid, pusi, adapt, cnt = self.parser.parse_header(self.current_hex_data)
        import struct
        hdr_val = struct.unpack('>I', self.current_hex_data[:4])[0]
        scram = (hdr_val >> 6) & 0x3
        
        if pid != self.selected_pid:
            cv2.putText(img, "Current packet does not match selected PID.", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 150), 1)
            return
            
        ts_info = f"[TS Header] PUSI: {pusi} | CC: {cnt:02d} | Scram: {scram} | Adapt: {adapt}"
        cv2.putText(img, ts_info, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cur_y += 30

        # Payload 추출
        off = 4
        if adapt & 0x2: off = 5 + self.current_hex_data[4]
        
        payload = b''
        if off < 188:
            payload = self.current_hex_data[off:]

        # Check for PSI/SI Table PID
        is_psi_pid = False
        if pid == 0 or pid == 1 or pid == 2: # PAT, CAT, TSDT
            is_psi_pid = True
        else:
            # [수정] selected_program과 무관하게, 알려진 모든 PMT PID를 확인
            for prog in self.parser.programs.values():
                if pid == prog['pmt_pid']:
                    is_psi_pid = True
                    break
        
        # PES 분석 및 출력
        if pusi and not is_psi_pid:
            # === Case 1: PES Packet Start ===
            pes_title = ">> PES Packet Start <<"
            (tw, th), _ = cv2.getTextSize(pes_title, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            
            # Interactive Region: PES Header (General)
            # PES Header Range: off ~ off + (header length)
            if len(payload) >= 6:
                pes_hdr_len = 6 # Min
                if len(payload) >= 9:
                    pes_hdr_len += 3 + payload[8]
                if pes_hdr_len > len(payload): pes_hdr_len = len(payload)
                
                # 전체 헤더 영역
                add_region('PES Header', off, pes_hdr_len, (x+20-5, cur_y-th-5, x+20+tw+5, cur_y+5))
            
            cv2.putText(img, pes_title, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cur_y += 30
            
            pes_info = self.parser.parse_pes_header(payload)
            if pes_info:
                # Stream ID (Offset: off + 3, Len: 1)
                sid = pes_info['stream_id']
                sid_str = f"Stream ID: 0x{sid:02X}"
                if 0xC0 <= sid <= 0xDF: sid_str += " (Audio)"
                elif 0xE0 <= sid <= 0xEF: sid_str += " (Video)"
                elif sid == 0xBD: sid_str += " (Private)"
                
                (tw, th), _ = cv2.getTextSize(sid_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                add_region(f"Stream ID (0x{sid:02X})", off+3, 1, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                cv2.putText(img, sid_str, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # PES Packet Length (Offset: off + 4, Len: 2)
                p_len = pes_info['pes_length']
                len_str = f"Length: {p_len} bytes"
                if p_len == 0: len_str += " (Unbounded/Video)"
                
                (tw, th), _ = cv2.getTextSize(len_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                add_region(f"PES Length ({p_len})", off+4, 2, (x+250, cur_y-th-5, x+250+tw, cur_y+5))
                cv2.putText(img, len_str, (x+250, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cur_y += 25
                
                # PTS / DTS
                pts = pes_info.get('pts')
                dts = pes_info.get('dts')
                
                curr_field_off = off + 9
                
                pts_str = ""
                if pts is not None:
                    pts_sec = pts / 90000.0
                    pts_str = f"PTS: {pts} ({pts_sec:.3f}s)"
                    
                    (tw, th), _ = cv2.getTextSize(pts_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    add_region("PTS", curr_field_off, 5, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                    
                    cv2.putText(img, pts_str, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)
                    curr_field_off += 5
                
                if dts is not None:
                    dts_sec = dts / 90000.0
                    dts_str = f"DTS: {dts} ({dts_sec:.3f}s)"
                    
                    offset_x = 200
                    if pts_str:
                        (w_txt, _), _ = cv2.getTextSize(pts_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        offset_x = 20 + w_txt + 30
                        
                    (tw, th), _ = cv2.getTextSize(dts_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    add_region("DTS", curr_field_off, 5, (x+offset_x, cur_y-th-5, x+offset_x+tw, cur_y+5))
                    
                    cv2.putText(img, dts_str, (x+offset_x, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)
                
                if pts or dts: cur_y += 25
            else:
                cv2.putText(img, "[Error] Invalid PES Header", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                if len(payload) >= 8:
                    dump = " ".join(f"{b:02X}" for b in payload[:8])
                    cv2.putText(img, f"Raw: {dump}...", (x+20, cur_y+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                    cur_y += 25
            
            # PES Start에서도 Navigation 버튼은 표시
            found_start = True
            start_idx = self.current_pkt_idx
            
        elif pusi and is_psi_pid:
            # === Case 2: PSI Table Start (No PES Header) ===
            cv2.putText(img, ">> PSI/SI Table Start <<", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 255), 2)
            cur_y += 30
            
            if len(payload) > 0:
                ptr = payload[0]
                if len(payload) > 1 + ptr:
                    data = payload[1+ptr:]
                    if len(data) > 3:
                        tid = data[0]
                        sec_len = ((data[1] & 0x0F) << 8) | data[2]
                        base_off = off + 1 + ptr
                        
                        # 1. Table ID
                        tid_desc = f"Table ID: 0x{tid:02X}"
                        if tid == 0x00: tid_desc += " (PAT)"
                        elif tid == 0x01: tid_desc += " (CAT)"
                        elif tid == 0x02: tid_desc += " (PMT)"
                        
                        (tw, th), _ = cv2.getTextSize(tid_desc, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        add_region(f"Table ID (0x{tid:02X})", base_off, 1, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                        cv2.putText(img, tid_desc, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                        cur_y += 25
                        
                        # 2. Section Length
                        sec_len_str = f"Section Length: {sec_len} bytes"
                        (tw, th), _ = cv2.getTextSize(sec_len_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        add_region(f"Section Length ({sec_len})", base_off+1, 2, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                        cv2.putText(img, sec_len_str, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                        cur_y += 25
                        
                        # === Simple Content Parsing for PAT/PMT ===
                        if tid == 0x00: # PAT
                            if len(data) >= 8:
                                ts_id = (data[3] << 8) | data[4]
                                ver = (data[5] >> 1) & 0x1F
                                txt = f"TS ID: 0x{ts_id:04X} | Ver: {ver}"
                                (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                add_region(f"TS ID (0x{ts_id:04X})", base_off+3, 2, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                                cv2.putText(img, txt, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)
                                cur_y += 25
                                
                                loop_end = min(3 + sec_len - 4, len(data))
                                idx = 8
                                cnt = 0
                                while idx < loop_end - 3 and cnt < 5: 
                                    pn = (data[idx] << 8) | data[idx+1]
                                    pid_val = ((data[idx+2] & 0x1F) << 8) | data[idx+3]
                                    p_type = "NIT" if pn == 0 else "PMT"
                                    txt = f"- Prog {pn}: PID 0x{pid_val:X} ({p_type})"
                                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                    add_region(f"Prog {pn} Entry", base_off+idx, 4, (x+40, cur_y-th-5, x+40+tw, cur_y+5))
                                    cv2.putText(img, txt, (x+40, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                                    cur_y += 25
                                    idx += 4
                                    cnt += 1
                                if idx < loop_end - 3:
                                    cv2.putText(img, "... more programs ...", (x+40, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                                    cur_y += 25
                                    
                                if len(data) >= 3 + sec_len:
                                    crc_val = (data[3+sec_len-4]<<24) | (data[3+sec_len-3]<<16) | (data[3+sec_len-2]<<8) | data[3+sec_len-1]
                                    txt = f"CRC32: 0x{crc_val:08X}"
                                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                    add_region("CRC32", base_off+3+sec_len-4, 4, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                                    cv2.putText(img, txt, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)
                                    cur_y += 25

                        elif tid == 0x02: # PMT
                            if len(data) >= 12:
                                pcr_pid_val = ((data[8] & 0x1F) << 8) | data[9]
                                p_len = ((data[10] & 0x0F) << 8) | data[11]
                                txt = f"PCR PID: 0x{pcr_pid_val:X}"
                                (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                add_region(f"PCR PID (0x{pcr_pid_val:X})", base_off+8, 2, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                                cv2.putText(img, txt, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                                cur_y += 25
                                
                                if p_len > 0:
                                    txt = f"Program Descriptors ({p_len} bytes)"
                                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                    add_region("Program Descriptors", base_off+12, p_len, (x+30, cur_y-th-5, x+30+tw, cur_y+5))
                                    cv2.putText(img, txt, (x+30, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)
                                    cur_y += 25
                                
                                loop_start = 12 + p_len
                                loop_end = min(3 + sec_len - 4, len(data))
                                idx = loop_start
                                cnt = 0
                                while idx < loop_end - 4 and cnt < 6: 
                                    stype = data[idx]
                                    epid = ((data[idx+1] & 0x1F) << 8) | data[idx+2]
                                    es_info_len = ((data[idx+3] & 0x0F) << 8) | data[idx+4]
                                    from ts_parser_core import STREAM_TYPES
                                    st_desc = STREAM_TYPES.get(stype, "Unknown")
                                    if len(st_desc) > 15: st_desc = st_desc[:15] + "..."
                                    text = f"- Type 0x{stype:02X} ({st_desc}): PID 0x{epid:X}"
                                    entry_len = 5 + es_info_len
                                    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                                    add_region(f"ES Entry (PID 0x{epid:X})", base_off+idx, entry_len, (x+40, cur_y-th-5, x+40+tw, cur_y+5))
                                    cv2.putText(img, text, (x+40, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
                                    cur_y += 25
                                    idx += entry_len
                                    cnt += 1
                                if idx < loop_end - 4:
                                    cv2.putText(img, "... more streams ...", (x+40, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
                                    cur_y += 25

                                if len(data) >= 3 + sec_len:
                                    crc_val = (data[3+sec_len-4]<<24) | (data[3+sec_len-3]<<16) | (data[3+sec_len-2]<<8) | data[3+sec_len-1]
                                    txt = f"CRC32: 0x{crc_val:08X}"
                                    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                                    add_region("CRC32", base_off+3+sec_len-4, 4, (x+20, cur_y-th-5, x+20+tw, cur_y+5))
                                    cv2.putText(img, txt, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)
                                    cur_y += 25
            
            found_start = True
            start_idx = self.current_pkt_idx
            
        else:
            # PES Continuation
            cv2.putText(img, ">> PES Continuation <<", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2)
            cur_y += 30 # 한 줄 띄우기
            
            # Back-tracking to find PES Start
            found_start = False
            start_idx = -1
            acc_payload = 0 
            
            curr_p_len = len(payload)
            
            # Video 스트림이면 탐색 범위를 크게 잡음 (50,000 패킷 = 약 9.4MB)
            # 일반 Audio/Data는 5,000 패킷이면 충분
            is_video = False
            pid_info = self.parser.pid_map.get(self.selected_pid, {})
            if "Video" in pid_info.get('desc', ''): is_video = True
            
            search_limit = 50000 if is_video else 5000 
            dist = 0
            
            # 최적화: 파일을 한 번에 읽어서 메모리 탐색 (Batch Read)
            # [수정] PSI PID인 경우 Backtracking 생략
            if is_psi_pid:
                cv2.putText(img, "[Info] PSI/SI Table Section (No PES Header)", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 255), 1)
                cur_y += 25
            else:
                try:
                    with open(self.parser.file_path, "rb") as f:
                        start_search_idx = max(0, self.current_pkt_idx - search_limit)
                        read_count = self.current_pkt_idx - start_search_idx
                        
                        if read_count > 0:
                            f.seek(start_search_idx * 188)
                            chunk_data = f.read(read_count * 188)
                        
                            # 역방향 탐색 (메모리)
                            # chunk_data의 끝에서부터 앞으로 이동
                            for k in range(read_count):
                                # k=0 -> 바로 전 패킷 (idx - 1)
                                # offset calculation
                                # chunk size = read_count * 188
                                # target packet start = (read_count - 1 - k) * 188
                                
                                pkt_offset = (read_count - 1 - k) * 188
                                t_data = chunk_data[pkt_offset : pkt_offset + 188]
                                
                                # PID/PUSI Parsing
                                import struct
                                h = struct.unpack('>I', t_data[:4])[0]
                                t_pid = (h >> 8) & 0x1FFF
                                
                                if t_pid == self.selected_pid:
                                    dist += 1
                                    
                                    t_pusi = (h >> 22) & 0x1
                                    t_adapt = (h >> 4) & 0x3
                                    
                                    t_off = 4
                                    if t_adapt & 0x2: 
                                        t_off = 5 + t_data[4]
                                    
                                    if t_off < 188:
                                        acc_payload += (188 - t_off)
                                    
                                    if t_pusi:
                                        found_start = True
                                        start_idx = self.current_pkt_idx - 1 - k
                                        
                                        # PES Header Parsing for Start Packet
                                        t_payload = t_data[t_off:]
                                        pes_info = self.parser.parse_pes_header(t_payload)
                                        
                                        if pes_info:
                                            total_len = pes_info['pes_length']
                                            current_seq = dist
                                            processed_bytes = acc_payload + curr_p_len
                                            
                                            prog_info = ""
                                            # Video (0) Handling
                                            if total_len == 0:
                                                seq_str = f"Seq: {current_seq} (Unbounded)"
                                                prog_info = f" | Acc: {processed_bytes:,} bytes"
                                            else:
                                                pct = (processed_bytes / total_len) * 100
                                                est_total_pkts = int((total_len + 6) / 184.0) + 1
                                                prog_info = f" | {pct:.1f}% ({processed_bytes:,}/{total_len:,})"
                                                seq_str = f"Seq: {current_seq} / ~{est_total_pkts}"
                                                
                                            # [이동 완료] PES Continuation 바로 아래에 표시
                                            cv2.putText(img, seq_str + prog_info, (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 100), 1)
                                            cur_y += 25 # 줄바꿈 반영
                                        break
                except Exception as e:
                     print(f"[Error] Back-tracking failed: {e}")
            
            # PES Navigation Target 업데이트 (좌표는 위에서 계산됨)
        # 버튼이 눌렸을 때 동작하도록 targets 딕셔너리를 갱신해야 함
        if found_start:
            self.pes_nav_targets['pes_prev']['idx'] = start_idx
        
        # 클릭 피드백 (버튼 위치에 사각형 그리기)
        if hasattr(self, 'last_click_time') and hasattr(self, 'last_click_target'):
            if time.time() - self.last_click_time < 0.2:
                if self.last_click_target == 'pes_prev':
                     cv2.rectangle(img, btn_pes_prev_rect[:2], btn_pes_prev_rect[2:], (0, 0, 255), 2)
                elif self.last_click_target == 'pes_next':
                     cv2.rectangle(img, btn_pes_next_rect[:2], btn_pes_next_rect[2:], (0, 0, 255), 2)

        # Simple Audio Sync Check
        if len(payload) > 2:
            for i in range(len(payload)-1):
                # MP2/ADTS (FFF) Check
                if payload[i] == 0xFF and (payload[i+1] & 0xF0) == 0xF0:
                    # cur_y 좌표 그대로 사용 (위에서 간격 조정됨)
                    cv2.putText(img, f"[Audio Sync] Found at offset {i} (0xFFF...)", (x+20, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    break

    def _draw_detail(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (35, 35, 45), -1)
        # Title
        cv2.putText(img, "ISO 13818-1 Packet Header Analysis", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        
        if not self.current_hex_data: return
        
        # 1. Parse Header & Adaptation Field
        adapt_info = self.parser.parse_adapt_field(self.current_hex_data)
        pid, pusi, adapt, cnt = self.parser.parse_header(self.current_hex_data)
        
        import struct
        hdr_val = struct.unpack('>I', self.current_hex_data[:4])[0]
        tei = (hdr_val >> 23) & 0x1
        prio = (hdr_val >> 21) & 0x1
        scram = (hdr_val >> 6) & 0x3
        
        # 2. Layout Config
        col1_x = x + 20
        col2_x = x + 500
        cur_y = y + 50
        line_h = 22 # 줄간격 축소 (25 -> 22)
        font_size = 0.5 # 폰트 확대 (0.45 -> 0.5)
        
        # --- Column 1: TS Header Fixed Part (4 Bytes) ---
        # Interactive Region 등록: TS Header (전체)
        header_title = f"[TS Header] Packet Index: {self.current_pkt_idx}"
        (tw, th), _ = cv2.getTextSize(header_title, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        
        # Draw Background if Active
        region_key = 'TS Header'
        is_active = (self.selected_region and self.selected_region['name'] == region_key) or \
                    (self.hover_region and self.hover_region['name'] == region_key)
        
        if is_active:
            cv2.rectangle(img, (col1_x-5, cur_y-th-5), (col1_x+tw+5, cur_y+5), (100, 50, 50), -1) # Red-ish bg
            
        cv2.putText(img, header_title, (col1_x, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 255), 1)
        
        # Register Region (Range: 0~4)
        self.ui_regions.append({
            'name': region_key,
            'rect': (col1_x-5, cur_y-th-5, col1_x+tw+5, cur_y+5),
            'range': (0, 4),
            'color': (50, 50, 200) # Red
        })
        cur_y += line_h
        
        # Helper for field drawing
        def draw_field(text, region_name, byte_range, color=(200, 200, 200), bg_color=(80, 80, 100)):
            nonlocal cur_y
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_size, 1)
            
            is_active = (self.selected_region and self.selected_region['name'] == region_name) or \
                        (self.hover_region and self.hover_region['name'] == region_name)
            
            if is_active:
                cv2.rectangle(img, (col1_x-5, cur_y-th-5), (col1_x+tw+5, cur_y+5), bg_color, -1)
                
            cv2.putText(img, text, (col1_x, cur_y), cv2.FONT_HERSHEY_SIMPLEX, font_size, color, 1)
            
            self.ui_regions.append({
                'name': region_name,
                'rect': (col1_x-5, cur_y-th-5, col1_x+tw+5, cur_y+5),
                'range': byte_range,
                'color': (0, 255, 255) # Yellow Highlight in Hex
            })
            cur_y += line_h
        
        # [추가] ETR-290 Section Check (PAT/PMT)
        # 현재 PID가 PAT(0)이거나 PMT PID인 경우 검사
        section_check_str = ""
        is_psi_table = False
        
        if pid == 0 and pusi:
            # PAT Check
            res = self.parser._parse_pat(self.current_hex_data, adapt)
            if res:
                if res['valid_crc'] is None:
                    crc_status = "Incomplete"
                elif res['valid_crc']:
                    crc_status = f"OK (0x{res['calc_crc']:08X})"
                else:
                    # Fail case: show calc vs expected
                    calc = res['calc_crc'] if res['calc_crc'] is not None else 0
                    exp = res['expected_crc'] if res['expected_crc'] is not None else 0
                    crc_status = f"FAIL (Cal:0x{calc:08X}, Exp:0x{exp:08X})"
                
                section_check_str = f"PAT Check | CRC: {crc_status} | TID: {'OK' if res['valid_tid'] else 'FAIL'}"
                is_psi_table = True
        
        elif self.selected_program and self.selected_program in self.parser.programs:
            prog = self.parser.programs[self.selected_program]
            if pid == prog['pmt_pid'] and pusi:
                # PMT Check
                dummy_node = {'pids': {}} 
                res = self.parser._parse_pmt(self.current_hex_data, adapt, dummy_node)
                if res:
                    if res['valid_crc'] is None:
                        crc_status = "Incomplete"
                    elif res['valid_crc']:
                        crc_status = f"OK (0x{res['calc_crc']:08X})"
                    else:
                        calc = res['calc_crc'] if res['calc_crc'] is not None else 0
                        exp = res['expected_crc'] if res['expected_crc'] is not None else 0
                        crc_status = f"FAIL (Cal:0x{calc:08X}, Exp:0x{exp:08X})"

                    section_check_str = f"PMT Check | CRC: {crc_status} | TID: {'OK' if res['valid_tid'] else 'FAIL'}"
                    is_psi_table = True

        # Fixed Header Fields (Byte 0, 1)
        draw_field(f"Sync Byte: 0x47", "Sync Byte", (0, 1))
        
        # ETR-290 Info Display
        if is_psi_table:
            if "FAIL" in section_check_str:
                check_color = (100, 100, 255) # Red
            elif "Incomplete" in section_check_str:
                check_color = (100, 255, 255) # Yellow/Cyan
            else:
                check_color = (100, 255, 100) # Green
            draw_field(section_check_str, "Section Check", (0, 188), color=check_color)

        draw_field(f"Transport Error Indicator (TEI): {tei}", "TEI", (1, 2))
        draw_field(f"Payload Unit Start Indicator (PUSI): {pusi}", "PUSI", (1, 2))
        draw_field(f"Transport Priority: {prio}", "Transport Priority", (1, 2))
            
        # PID (Byte 1, 2)
        pid_color = (0, 255, 0) if pid == self.selected_pid else (200, 200, 200)
        pid_desc = self.parser.pid_map.get(pid, {}).get('desc', 'Unknown')
        draw_field(f"PID: 0x{pid:04X} ({pid}) - {pid_desc}", "PID", (1, 3), color=pid_color)
        
        # Flags & Counters (Byte 3)
        draw_field(f"Transport Scrambling Control: {scram}", "Scrambling", (3, 4))
        draw_field(f"Adaptation Field Control: {adapt}", "Adaptation Control", (3, 4))
        draw_field(f"Continuity Counter: {cnt}", "Continuity Counter", (3, 4))

        # --- Column 2: Adaptation Field Detail ---
        # Reset Y for Col 2 (but keep draw_field helper adapting to x)
        save_col1_x = col1_x
        col1_x = col2_x # Hack to reuse draw_field
        cur_y = y + 50
        
        if adapt_info['exist']:
            # Adaptation Field Header
            adapt_title = "[Adaptation Field]"
            (tw, th), _ = cv2.getTextSize(adapt_title, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            
            region_key = 'Adaptation Field'
            is_active = (self.selected_region and self.selected_region['name'] == region_key) or \
                        (self.hover_region and self.hover_region['name'] == region_key)
            
            if is_active:
                cv2.rectangle(img, (col2_x-5, cur_y-th-5), (col2_x+tw+5, cur_y+5), (50, 100, 50), -1)

            cv2.putText(img, adapt_title, (col2_x, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)
            
            a_len = self.current_hex_data[4]
            self.ui_regions.append({
                'name': region_key,
                'rect': (col2_x-5, cur_y-th-5, col2_x+tw+5, cur_y+5),
                'range': (4, 5 + a_len),
                'color': (50, 200, 50)
            })
            cur_y += line_h
            
            # Length (Byte 4)
            draw_field(f"Adaptation Field Length: {adapt_info['length']}", "Adapt Length", (4, 5))
            
            if adapt_info['length'] > 0:
                # Flags (Byte 5)
                flags_range = (5, 6)
                draw_field(f"Discontinuity Indicator: {adapt_info['discontinuity']}", "Discontinuity", flags_range)
                draw_field(f"Random Access Indicator: {adapt_info['random_access']}", "Random Access", flags_range)
                draw_field(f"ES Priority Indicator: {adapt_info['es_priority']}", "ES Priority", flags_range)
                draw_field(f"PCR Flag: {adapt_info['pcr_flag']}", "PCR Flag", flags_range)
                draw_field(f"OPCR Flag: {adapt_info['opcr_flag']}", "OPCR Flag", flags_range)
                draw_field(f"Splicing Point Flag: {adapt_info['splicing_point_flag']}", "Splicing Point", flags_range)
                
                # Optional Fields Offset Calculation
                curr_off = 6
                if adapt_info['pcr'] is not None:
                    pcr_val = adapt_info['pcr']
                    pcr_sec = pcr_val / 27_000_000.0
                    pcr_str = f">> PCR: {pcr_val} ({pcr_sec:.6f}s)"
                    # PCR is 6 bytes (48 bits)
                    draw_field(pcr_str, "PCR Value", (curr_off, curr_off+6), color=(0, 255, 255))
                    curr_off += 6
                    
                if adapt_info['opcr'] is not None:
                    # OPCR is 6 bytes
                    draw_field(f"OPCR: {adapt_info['opcr']}", "OPCR Value", (curr_off, curr_off+6))
                    curr_off += 6
                    
                if adapt_info['splicing_point_flag']:
                    draw_field("Splicing Point: ...", "Splicing Point", (curr_off, curr_off+1))
                    curr_off += 1
                    
        else:
            cv2.putText(img, "[No Adaptation Field]", (col2_x, cur_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
            
        col1_x = save_col1_x # Restore

    def _draw_hex(self, img, x, y, w, h):
        cv2.rectangle(img, (x, y), (x+w, y+h), (20, 20, 20), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80, 80, 80), 1)
        cv2.putText(img, "Packet Binary Data (188 Bytes)", (x+10, y+25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
        
        # Play 중에는 Hex Dump 생략 (성능 최적화)
        if self.playing:
             cv2.putText(img, "Playback in progress...", (x+50, y+100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1)
             return
        
        if not self.current_hex_data: return
        
        # Highlight Info 준비
        hl_start, hl_end, hl_color = -1, -1, None
        
        target = self.selected_region if self.selected_region else self.hover_region
        if target:
            hl_start, hl_end = target['range']
            hl_color = target['color']
        
        sy = y + 50
        char_w = 14 # 폰트 0.45일 때 대략적인 글자 너비 (조정 필요)
        
        for i in range(0, 188, 16):
            chunk = self.current_hex_data[i:i+16]
            hexs = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join((chr(b) if 32<=b<127 else ".") for b in chunk)
            
            # 줄간격 20 -> 24 확대
            ly = sy + (i//16)*24 
            
            # Highlight Box Drawing
            if hl_color and hl_end > i and hl_start < i + 16:
                # 이 행(Row)에 하이라이트가 포함됨
                row_start = max(i, hl_start)
                row_end = min(i + 16, hl_end)
                
                # Column Index (0~15)
                c_s = row_start - i
                c_e = row_end - i
                
                # Hex Part Box
                # Hex Start X: x+60
                # 각 바이트 "XX " = 3 chars. 
                # Box Start: x + 60 + c_s * (3 * char_w)
                # Box End: x + 60 + c_e * (3 * char_w) - space
                
                # 정밀한 좌표 계산을 위해 getTextSize 사용 권장하지만, 성능을 위해 고정폭 근사
                # FONT_HEX 0.45 기준 "00 " 너비 약 36px?
                # 실제 렌더링: (x+60, ly)에서 시작.
                
                # Hex 영역 박스
                hex_step_x = 33 # 글자간격 튜닝
                box_x1 = x + 60 + int(c_s * hex_step_x)
                box_x2 = x + 60 + int(c_e * hex_step_x) - 5
                box_y1 = ly - 18
                box_y2 = ly + 6
                
                cv2.rectangle(img, (box_x1, box_y1), (box_x2, box_y2), hl_color, 2)
                
                # ASCII 영역 박스 (Optional)
                # Start X: x+490
                # Char Step: 12 px?
                asc_step_x = 14
                box_ax1 = x + 490 + int(c_s * asc_step_x)
                box_ax2 = x + 490 + int(c_e * asc_step_x)
                
                # ASCII는 겹침 방지를 위해 은은하게
                overlay = img.copy()
                cv2.rectangle(overlay, (box_ax1, box_y1), (box_ax2, box_y2), hl_color, -1)
                cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)

            cv2.putText(img, f"{i:02X}:", (x+10, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (150, 150, 150), 1)
            cv2.putText(img, hexs, (x+60, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (200,200,200), 1)
            # ASCII Text 오른쪽으로 추가 이동 (450 -> 490)
            cv2.putText(img, asc, (x+490, ly), cv2.FONT_HERSHEY_SIMPLEX, FONT_HEX, (100,255,100), 1)

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
        cv2.putText(img, status_text, (550, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

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
        # Update mouse coordinates globally
        self.mouse_x = x
        self.mouse_y = y

        if event == cv2.EVENT_MOUSEMOVE:
            self.ui.handle_mouse_move(x, y)
            
            # Handle Field Hover
            self.hover_region = None
            if not self.ui.menu_open: # 메뉴가 열려있지 않을 때만
                for region in self.ui_regions:
                    rx1, ry1, rx2, ry2 = region['rect']
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        self.hover_region = region
                        break
                        
        elif event == cv2.EVENT_LBUTTONDOWN:
            print(f"[DEBUG] Mouse Click at ({x}, {y})")
            
            # Handle Field Click (Selection Toggle)
            clicked_field = False
            if not self.ui.menu_open:
                for region in self.ui_regions:
                    rx1, ry1, rx2, ry2 = region['rect']
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        if self.selected_region and self.selected_region['name'] == region['name']:
                            self.selected_region = None # Toggle Off
                        else:
                            self.selected_region = region # Select
                        clicked_field = True
                        break
            
            # 1. Menu & Button Click (Delegated to UIManager)
            if self.ui.handle_click(x, y):
                return

            # 2. PES Navigation Click
            if hasattr(self, 'pes_nav_targets') and self.pes_nav_targets:
                # 2-1. Prev Packet (<)
                if 'pkt_prev' in self.pes_nav_targets:
                    r = self.pes_nav_targets['pkt_prev']['rect']
                    if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
                        self._step_packet(-1)
                        return

                # 2-2. Next Packet (>)
                if 'pkt_next' in self.pes_nav_targets:
                    r = self.pes_nav_targets['pkt_next']['rect']
                    if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
                        self._step_packet(1)
                        return

                # 2-3. PES Start Prev (<<)
                if 'pes_prev' in self.pes_nav_targets:
                    r = self.pes_nav_targets['pes_prev']['rect']
                    if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
                        print("[DEBUG] Prev PES Start Clicked")
                        self.last_click_time = time.time()
                        self.last_click_target = 'pes_prev'
                        
                        # Start Backward Playback Search
                        # 1. Use Selected PID from PMT (Priority)
                        target_pid = self.selected_pid
                        
                        # 2. Fallback: Current Packet PID
                        if target_pid is None:
                            data = self.parser.read_packet_at(self.current_pkt_idx)
                            if data:
                                import struct
                                target_pid = (struct.unpack('>I', data[:4])[0] >> 8) & 0x1FFF
                        
                        if target_pid is not None:
                            self.search_target_pid = target_pid
                            self.playing = True
                            self.speed = -50.0 # 고속 역방향
                            self.pes_search_mode = True
                            
                            # 현재 패킷에서 바로 멈추지 않도록 한 칸 이동
                            self.current_pkt_idx = max(0, self.current_pkt_idx - 1)
                            
                            print(f"[DEBUG] Search Prev PES Start (PID: 0x{target_pid:X})")
                        else:
                            print("[Error] No Target PID for Search")
                        
                        return # Playback 루프에서 처리됨

                # 2-4. PES Start Next (>>)
                if 'pes_next' in self.pes_nav_targets:
                    r = self.pes_nav_targets['pes_next']['rect']
                    if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
                        print("[DEBUG] Next PES Start Clicked")
                        self.last_click_time = time.time()
                        self.last_click_target = 'pes_next'
                        
                        # Start Forward Playback Search
                        # 1. Use Selected PID from PMT (Priority)
                        target_pid = self.selected_pid
                        
                        # 2. Fallback: Current Packet PID
                        if target_pid is None:
                            data = self.parser.read_packet_at(self.current_pkt_idx)
                            if data:
                                import struct
                                target_pid = (struct.unpack('>I', data[:4])[0] >> 8) & 0x1FFF

                        if target_pid is not None:
                            self.search_target_pid = target_pid
                            self.playing = True
                            self.speed = 50.0 # 고속 정방향
                            self.pes_search_mode = True
                            
                            # 현재 패킷에서 바로 멈추지 않도록 한 칸 이동
                            self.current_pkt_idx += 1
                            
                            print(f"[DEBUG] Search Next PES Start (PID: 0x{target_pid:X})")
                        else:
                            print("[Error] No Target PID for Search")

                        return # Playback 루프에서 처리됨

            # 3. Tree View Selection
            # PAT 영역 (y: 60~480)
            if 0 <= x <= 400 and 60 <= y <= 480:
                # [New] Click Title "PAT (Programs)" to select PID 0
                if 60 <= y <= 90:
                    self.selected_pid = 0
                    # [수정] PAT 선택 시 개별 프로그램 선택 해제
                    self.selected_program = None
                    
                    # [UI 연동] 모든 필터 끄고 PAT만 켬 (Exclusive)
                    for k in self.active_filters: self.active_filters[k] = False
                    self.active_filters['PAT'] = True
                    
                    print("[UI] Selected PAT -> Toolbar: PAT Only")
                    return

                cur_y = 60 + 50
                for prog_num in self.parser.programs.keys():
                    if cur_y - 20 <= y <= cur_y + 5:
                        self.selected_program = prog_num
                        
                        # [수정] 프로그램 선택 시 해당 PMT PID를 자동 선택하여 바로 보여줌
                        prog_info = self.parser.programs[prog_num]
                        self.selected_pid = prog_info['pmt_pid']
                        
                        # [UI 연동] 프로그램 선택 시 PMT 필터 활성화
                        for k in self.active_filters: self.active_filters[k] = False
                        self.active_filters['PMT'] = True
                        print(f"[UI] Selected Program {prog_num} (PMT: 0x{self.selected_pid:X}) -> Toolbar: PMT Only")
                        
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
                        # [UI 연동] PMT 필터 활성화 (나머지 OFF)
                        for k in self.active_filters: self.active_filters[k] = False
                        self.active_filters['PMT'] = True
                        print("[UI] Selected PMT PID -> Toolbar: PMT Only")
                    else:
                        # 2. Components Check
                        cur_y += 25
                        for pid in prog['pids'].keys():
                            if cur_y - 20 <= y <= cur_y + 5:
                                self.selected_pid = pid
                                
                                # Sync with Filter Buttons
                                pid_info = self.parser.pid_map.get(pid, {})
                                pid_type = pid_info.get('type', 0)
                                desc = pid_info.get('desc', '')
                                
                                # [수정] 좌측 트리에서 PID 선택 시: 해당 PID만 단독 필터링 (Exclusive)
                                # 툴바 필터 버튼(전체 타입 필터)은 모두 끕니다.
                                # 사용자가 특정 PID를 찍었다는 건 그것만 보겠다는 뜻이기 때문입니다.
                                for k in self.active_filters: self.active_filters[k] = False
                                
                                print(f"[UI] Selected PID 0x{pid:X} -> All Global Filters OFF (Single PID Focus)")
                                
                                break
                            cur_y += 25

    def _handle_btn(self, name):
        if name == 'file':
            self.ui.menu_open = not self.ui.menu_open
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
                # 이미 완료된 상태면 리포트 다시 보기 트리거
                self.bscan_running = True 
            else: 
                # 초기 상태면 스캔 시작
                self.scanner.start()
        elif name == 'jitter':
            self.show_jitter = not self.show_jitter
            print(f"[UI] Jitter Analysis Window: {self.show_jitter}")
            # TODO: Open Jitter Window logic here
            
        elif name == 'prev': self._step_packet(-1)
        elif name == 'next': self._step_packet(1)
        
        # Filter Toggle
        elif name.startswith('filter_'):
            f_name = name.replace('filter_', '')
            if f_name in self.active_filters:
                # Toggle
                new_state = not self.active_filters[f_name]
                self.active_filters[f_name] = new_state
                print(f"[Filter] {f_name} -> {new_state}")
                
                # [UX 개선] 필터 버튼 클릭 시 해당 PID 자동 선택 및 화면 전환
                if new_state:
                    if f_name == 'PAT':
                        self.selected_pid = 0
                        self.selected_program = None # PAT 집중을 위해 프로그램 선택 해제
                        # 다른 필터 끄기 (PAT 독점)
                        for k in self.active_filters: 
                            if k != 'PAT': self.active_filters[k] = False
                        print("[Auto] PAT Button -> Selected PID 0")
                        
                    elif f_name == 'PMT':
                        # 현재 선택된 프로그램이 있으면 그 PMT, 없으면 첫 번째 프로그램의 PMT 선택
                        target_prog = self.selected_program
                        if target_prog is None and self.parser.programs:
                            target_prog = list(self.parser.programs.keys())[0]
                            self.selected_program = target_prog
                        
                        if target_prog and target_prog in self.parser.programs:
                            self.selected_pid = self.parser.programs[target_prog]['pmt_pid']
                            # 다른 필터 끄기
                            for k in self.active_filters:
                                if k != 'PMT': self.active_filters[k] = False
                            print(f"[Auto] PMT Button -> Selected Prog {target_prog}, PID 0x{self.selected_pid:X}")
                
                # Sync with PMT Selection (Video/Audio Only)
                if f_name in ['Video', 'Audio']:
                    if new_state:
                        # 필터 켜짐: 해당 타입의 첫 번째 PID 자동 선택
                        # 다른 필터는 끄는게 직관적일 수 있음 (Radio Button 처럼) -> 여기서는 OR 로직이므로 유지하되 선택만 변경
                        
                        # Find first matching PID in current program
                        if self.selected_program and self.selected_program in self.parser.programs:
                            prog = self.parser.programs[self.selected_program]
                            for pid, info in prog['pids'].items():
                                p_type = info.get('type', 0)
                                desc = info.get('desc', '')
                                is_match = False
                                
                                if f_name == 'Video' and (p_type in [0x01, 0x02, 0x1B, 0x24] or "Video" in desc): is_match = True
                                if f_name == 'Audio' and (p_type in [0x03, 0x04, 0x0F, 0x81] or "Audio" in desc): is_match = True
                                
                                if is_match:
                                    self.selected_pid = pid
                                    # 상호 배제적 선택을 위해 다른 필터 끄기 (User UX에 따라 다름)
                                    # 요청사항: "Video선택시 Audio해제" 등 명시는 없으나 보통 하나만 봄.
                                    # 여기서는 켜진 필터에 맞는 PID로 포커스만 이동
                                    break
                    else:
                        # 필터 꺼짐: 현재 선택된 PID가 해당 타입이면 선택 해제
                        if self.selected_pid:
                            pid_info = self.parser.pid_map.get(self.selected_pid, {})
                            p_type = pid_info.get('type', 0)
                            desc = pid_info.get('desc', '')
                            
                            is_match = False
                            if f_name == 'Video' and (p_type in [0x01, 0x02, 0x1B, 0x24] or "Video" in desc): is_match = True
                            if f_name == 'Audio' and (p_type in [0x03, 0x04, 0x0F, 0x81] or "Audio" in desc): is_match = True
                            
                            if is_match:
                                self.selected_pid = None # 선택 해제

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
            try:
                root = tk.Tk()
                root.withdraw() # 메인 윈도우 숨김
                # 최상위로 띄우기 위한 트릭
                root.attributes('-topmost', True)
                path = filedialog.askopenfilename(
                    title="Open MPEG2-TS File",
                    filetypes=[("MPEG2-TS Files", "*.ts;*.tp;*.m2ts"), ("All Files", "*.*")]
                )
                root.destroy()
            except Exception as e:
                print(f"[Error] File Dialog failed: {e}")
                return
        
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
        
        # PES Search State
        self.pes_search_mode = False
        self.search_target_pid = None
        
        # Init Scan (UI blocking for short time)
        self.parser.quick_scan(limit=20000)
        
        if self.parser.programs:
            # 0번이 아닌 프로그램 중 가장 먼저 나오는 것 선택
            valid_progs = [p for p in self.parser.programs.keys() if p != 0]
            if valid_progs:
                first = sorted(valid_progs)[0]
                self.selected_program = first
                self.selected_pid = self.parser.programs[first]['pmt_pid']
                self.active_filters['PMT'] = True
            elif 0 in self.parser.programs:
                self.selected_program = 0
                self.selected_pid = self.parser.programs[0]['pmt_pid']
                
        self.update_packet_view()

    def _toggle_play(self):
        self.playing = not self.playing
        if self.playing: self.speed = 1.0

    def check_packet_filter(self, packet):
        """
        현재 활성화된 필터 조건에 패킷이 부합하는지 확인 (OR 연산)
        필터가 모두 꺼져 있으면 True 반환 (필터링 없음)
        """
        # Check if any filter is active
        is_any_filter_active = any(self.active_filters.values())
        if not is_any_filter_active:
            return True
            
        # Parse packet for filtering
        pid, pusi, adapt, _ = self.parser.parse_header(packet)
        
        # 1. Video / Audio Filter
        if self.active_filters['Video'] or self.active_filters['Audio']:
            pid_type = self.parser.pid_map.get(pid, {}).get('type', 0)
            
            # Video Types: MPEG1(1), MPEG2(2), H.264(0x1B), HEVC(0x24)
            if self.active_filters['Video'] and pid_type in [0x01, 0x02, 0x1B, 0x24]: return True
            
            # Audio Types: MPEG1(3), MPEG2(4), AAC(0x0F), AC3(0x81)
            if self.active_filters['Audio'] and pid_type in [0x03, 0x04, 0x0F, 0x81]: return True
            
        # 2. PCR Filter
        if self.active_filters['PCR']:
            if adapt & 0x2: # Adapt Field Exists
                if len(packet) > 5:
                    flags = packet[5]
                    pcr_flag = (flags >> 4) & 0x1
                    if pcr_flag: return True
                    
        # 3. PTS / DTS Filter
        if self.active_filters['PTS'] or self.active_filters['DTS']:
            if pusi:
                # Check PES Header
                off = 4
                if adapt & 0x2: off = 5 + packet[4]
                
                if off < 188:
                    payload = packet[off:]
                    if len(payload) >= 9:
                        start_code = (payload[0]<<16) | (payload[1]<<8) | payload[2]
                        if start_code == 1:
                            flags_2 = payload[7]
                            pts_dts_flag = (flags_2 >> 6) & 0x3
                            
                            if self.active_filters['PTS'] and (pts_dts_flag & 0x2): return True
                            if self.active_filters['DTS'] and (pts_dts_flag & 0x1): return True

        # 5. PAT / PMT Filter
        if self.active_filters.get('PAT', False):
            if pid == 0: return True
            
        if self.active_filters.get('PMT', False):
            # Check against known PMT PIDs
            for prog in self.parser.programs.values():
                if pid == prog['pmt_pid']: return True

        return False

    def _step_packet(self, step):
        """
        패킷 이동 (탐색)
        - 조건(PID 선택 or 필터 활성)이 있으면: 'Smart Search' 모드로 재생 (고속 탐색)
        - 조건이 없으면: 단순 1칸 이동
        """
        # 1. 활성 조건 확인
        is_filter_active = any(self.active_filters.values())
        has_condition = (self.selected_pid is not None) or is_filter_active
        
        # 2. 조건이 없으면 단순 이동
        if not has_condition:
            self.playing = False
            self.current_pkt_idx = max(0, self.current_pkt_idx + step)
            self.update_packet_view()
            return

        # 3. 조건이 있으면 'Filter Search Mode'로 재생 시작
        # (무한루프 방지 및 UI 반응성 확보를 위해 Play Loop 이용)
        self.playing = True
        self.speed = 50.0 if step > 0 else -50.0  # 탐색 속도 (x50)
        
        self.filter_search_mode = True  # 필터 탐색 모드 활성화
        self.pes_search_mode = False    # PES 탐색 모드는 해제
        
        # 현재 위치에서는 이미 멈춰있을 수 있으므로, 일단 한 칸 이동 후 탐색 시작
        self.current_pkt_idx += (1 if step > 0 else -1)
        if self.current_pkt_idx < 0: self.current_pkt_idx = 0
        
        print(f"[Search] Searching with speed {self.speed}... (Filter: {is_filter_active}, PID: {self.selected_pid})")

    def _search_pes_start_backward(self):
        """현재 위치에서 뒤로 가며 PES Start(PUSI=1)를 찾음 (Deep Search)"""
        print("[DEBUG] Start Backward Search")
        
        # Searching 표시
        if hasattr(self, 'canvas'):
            temp_img = self.canvas.copy()
            cv2.rectangle(temp_img, (500, 400), (1100, 500), (0, 0, 0), -1)
            cv2.rectangle(temp_img, (500, 400), (1100, 500), (0, 255, 255), 2)
            cv2.putText(temp_img, "Searching Previous PES Start...", (520, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.imshow("MPEG2-TS Analyzer", temp_img)
            cv2.waitKey(1)

        # 현재 패킷의 PID를 타겟으로 설정
        import struct
        data = self.parser.read_packet_at(self.current_pkt_idx)
        if not data: 
            print("[DEBUG] No data at current index")
            return -1
            
        header = struct.unpack('>I', data[:4])[0]
        target_pid = (header >> 8) & 0x1FFF
        print(f"[DEBUG] Target PID: 0x{target_pid:X}")
        
        # 최대 500,000 패킷 (약 90MB) 검색
        max_search = 500000
        curr = self.current_pkt_idx
        
        for k in range(1, max_search):
            idx = curr - k
            if idx < 0: break
            
            data = self.parser.read_packet_at(idx)
            if not data: break
            
            # PID 및 PUSI 직접 파싱 (속도 최적화)
            h = struct.unpack('>I', data[:4])[0]
            pid = (h >> 8) & 0x1FFF
            pusi = (h >> 22) & 0x1
            
            if pid == target_pid:
                if pusi:
                    print(f"[DEBUG] Found PES Start at #{idx}")
                    return idx
        
        print("[DEBUG] PES Start not found in backward search")
        return -1

    def _search_pes_start_forward(self):
        """현재 위치에서 앞으로 가며 다음 PES Start(PUSI=1)를 찾음"""
        print("[DEBUG] Start Forward Search")
        
        # Searching 표시
        if hasattr(self, 'canvas'):
            temp_img = self.canvas.copy()
            cv2.rectangle(temp_img, (500, 400), (1100, 500), (0, 0, 0), -1)
            cv2.rectangle(temp_img, (500, 400), (1100, 500), (0, 255, 255), 2)
            cv2.putText(temp_img, "Searching Next PES Start...", (540, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.imshow("MPEG2-TS Analyzer", temp_img)
            cv2.waitKey(1)

        import struct
        data = self.parser.read_packet_at(self.current_pkt_idx)
        if not data: return -1
        header = struct.unpack('>I', data[:4])[0]
        target_pid = (header >> 8) & 0x1FFF
        print(f"[DEBUG] Target PID: 0x{target_pid:X}")
        
        max_search = 500000
        curr = self.current_pkt_idx
        
        for k in range(1, max_search):
            idx = curr + k
            data = self.parser.read_packet_at(idx)
            if not data: break # EOF
            
            h = struct.unpack('>I', data[:4])[0]
            pid = (h >> 8) & 0x1FFF
            pusi = (h >> 22) & 0x1
            
            if pid == target_pid:
                if pusi:
                    print(f"[DEBUG] Found PES Start at #{idx}")
                    return idx
        
        print("[DEBUG] PES Start not found in forward search")
        return -1

    def update_packet_view(self):
        data = self.parser.read_packet_at(self.current_pkt_idx)
        if data: 
            self.current_hex_data = data
        else:
            # EOF or Error: Revert to last valid index if possible
            if self.current_pkt_idx > 0:
                self.current_pkt_idx -= 1
                # Retry once
                data = self.parser.read_packet_at(self.current_pkt_idx)
                if data: self.current_hex_data = data

    def _handle_playback(self):
        wait = 10
        if self.playing:
            # === 1. 일반 재생 모드 (조건 없음) ===
            if (not hasattr(self, 'pes_search_mode') or not self.pes_search_mode) and \
               (not hasattr(self, 'filter_search_mode') or not self.filter_search_mode):
                self.current_pkt_idx += int(self.speed)
                if self.current_pkt_idx < 0: self.current_pkt_idx = 0
                self.update_packet_view()
                if self.speed == 1.0: wait = 10
                else: wait = 1
            
            # === 2. PES 탐색 모드 (정밀 검사) ===
            elif hasattr(self, 'pes_search_mode') and self.pes_search_mode:
                # 고속 이동하되, 건너뛰지 않고 모든 패킷 검사
                step = 1 if self.speed > 0 else -1
                steps_to_check = abs(int(self.speed)) # 예: 50개씩 검사
                
                found = False
                for _ in range(steps_to_check):
                    self.current_pkt_idx += step
                    if self.current_pkt_idx < 0: 
                        self.current_pkt_idx = 0
                        self.playing = False
                        self.pes_search_mode = False
                        break
                        
                    data = self.parser.read_packet_at(self.current_pkt_idx)
                    if not data: 
                        self.playing = False # EOF
                        self.pes_search_mode = False
                        break
                    
                    import struct
                    h = struct.unpack('>I', data[:4])[0]
                    pid = (h >> 8) & 0x1FFF
                    pusi = (h >> 22) & 0x1
                    
                    if pid == self.search_target_pid and pusi:
                        print(f"[DEBUG] Found PES Start at {self.current_pkt_idx}")
                        found = True
                        break # 찾음! 루프 탈출
                
                if found:
                    self.playing = False # 정지
                    self.pes_search_mode = False
                    self.speed = 1.0

                self.update_packet_view()
                wait = 1 # 빠른 갱신

            # === 3. Filter/PID 탐색 모드 (Smart Search) ===
            elif hasattr(self, 'filter_search_mode') and self.filter_search_mode:
                step = 1 if self.speed > 0 else -1
                steps_to_check = abs(int(self.speed))
                
                is_filter_active = any(self.active_filters.values())
                found = False
                
                # 파일 I/O 최적화를 위해 한 번 Open
                try:
                    with open(self.parser.file_path, "rb") as f:
                        for _ in range(steps_to_check):
                            # 경계 체크
                            if self.current_pkt_idx < 0:
                                self.current_pkt_idx = 0
                                found = True
                                break
                            
                            # Read Packet directly
                            f.seek(self.current_pkt_idx * 188)
                            data = f.read(188)
                            
                            if len(data) != 188: # EOF
                                self.playing = False
                                self.filter_search_mode = False
                                break
                                
                            # --- 조건 검사 ---
                            match = True
                            
                            # 필터가 켜져 있으면: PID 선택 무시하고 필터 조건만 검사 (Global Search)
                            if is_filter_active:
                                if not self.check_packet_filter(data):
                                    match = False
                            # 필터가 꺼져 있으면: 선택된 PID만 검사
                            elif self.selected_pid is not None:
                                import struct
                                h = struct.unpack('>I', data[:4])[0]
                                pid = (h >> 8) & 0x1FFF
                                if pid != self.selected_pid:
                                    match = False
                            
                            if match:
                                found = True
                                # 필터 탐색으로 찾았는데 PID가 다르면, 선택 PID를 자동 변경
                                if is_filter_active and self.selected_pid is not None:
                                    import struct
                                    h = struct.unpack('>I', data[:4])[0]
                                    pid = (h >> 8) & 0x1FFF
                                    if pid != self.selected_pid:
                                        self.selected_pid = pid
                                break
                            
                            # 다음 패킷으로
                            self.current_pkt_idx += step
                            
                except Exception as e:
                    print(f"[Error] Search IO failed: {e}")
                    self.playing = False
                    self.filter_search_mode = False
                
                if found:
                    self.playing = False
                    self.filter_search_mode = False
                    self.speed = 1.0
                    print(f"[Search] Found match at {self.current_pkt_idx}")
                
                self.update_packet_view()
                wait = 1

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
