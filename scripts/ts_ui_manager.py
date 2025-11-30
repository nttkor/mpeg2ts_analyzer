import cv2
import os
import json
import sys
import time
import tkinter as tk
from tkinter import filedialog
import numpy as np

class UIManager:
    def __init__(self, gui_context):
        """
        :param gui_context: AnalyzerGUI 인스턴스 (상태값 참조 및 콜백 호출용)
        """
        self.gui = gui_context
        self.menu_open = False
        self.hover_btn = None
        self.clicked_btn_info = None # {'name': str, 'time': float}
        self.recent_files = []
        self._load_recents()
        self.menu_items_rects = []
        
        # 버튼 초기화
        self.buttons = []
        self._init_buttons()

    def _init_buttons(self):
        base_y = 10
        h = 40
        btn_defs = [
            ('file', 'File', 70),
            ('bscan', 'BScan', 80),
            ('jitter', 'Jitter', 80), # Jitter 버튼 추가
            ('rev', '<<', 70),
            ('play', '>', 70),
            ('ff', '>>', 70),
            ('stop', 'STOP', 80),
            ('ext_play', 'Video Win', 110)
        ]
        
        cur_x = 20
        for name, label, width in btn_defs:
            self.buttons.append({
                'name': name, 
                'label': label, 
                'rect': (cur_x, base_y, cur_x+width, base_y+h)
            })
            cur_x += width + 10
            
        # Filter Buttons (Video, Audio, PCR, PTS, DTS)
        # Start after Tool Status Text (~900px)
        filter_start_x = 950
        filter_w = 60
        filters = ['Video', 'Audio', 'PCR', 'PTS', 'DTS']
        
        for f_name in filters:
            self.buttons.append({
                'name': f'filter_{f_name}',
                'label': f_name,
                'rect': (filter_start_x, base_y, filter_start_x+filter_w, base_y+h)
            })
            filter_start_x += filter_w + 5

    def _load_recents(self):
        try:
            if os.path.exists("recent_files.json"):
                with open("recent_files.json", "r") as f:
                    self.recent_files = json.load(f)
        except: self.recent_files = []

    def add_recent(self, path):
        if not path: return
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:5]
        try:
            with open("recent_files.json", "w") as f:
                json.dump(self.recent_files, f)
        except: pass

    def draw_toolbar(self, img):
        for btn in self.buttons:
            x1, y1, x2, y2 = btn['rect']
            color = (60, 60, 60)
            if btn == self.hover_btn: color = (80, 80, 80)
            
            label = btn['label']
            if btn['name'] == 'play':
                label = "||" if self.gui.playing else ">"
                if self.gui.playing: color = (0, 100, 0)
            elif btn['name'] == 'rev':
                label = "<<" if self.gui.playing else "<-"
            elif btn['name'] == 'ff':
                label = ">>" if self.gui.playing else "->"
            elif btn['name'] == 'jitter':
                label = "Jitter"
                if self.gui.show_jitter: # GUI 상태에 따라 색상 변경 (토글됨)
                    color = (0, 100, 100)
                else: color = (50, 50, 50)
            elif btn['name'] == 'bscan':
                label = "Stop" if self.gui.scanner.running else "BScan"
                if self.gui.scanner.running: 
                    color = (0, 100, 0)
                elif self.gui.scanner.completed:
                    label = "Report"
                    color = (0, 100, 100)
                else: color = (50, 50, 50)
            
            # Click Effect
            if self.clicked_btn_info and btn['name'] == self.clicked_btn_info['name']:
                if time.time() - self.clicked_btn_info['time'] < 0.15:
                    color = (150, 150, 180) # Flash color

            # Hover Effect (배경색 밝게 + 테두리 강조)
            border_color = (150, 150, 150)
            thickness = 1
            
            # Filter Button Style
            if btn['name'].startswith('filter_'):
                f_name = btn['name'].replace('filter_', '')
                is_active = self.gui.active_filters.get(f_name, False)
                if is_active:
                    color = (0, 150, 150) # Active Color (Cyan-ish)
                    border_color = (0, 255, 255)
                    thickness = 2
            
            if btn == self.hover_btn:
                if not (btn['name'] == 'bscan' and self.gui.scanner.running) and \
                   not (btn['name'] == 'play' and self.gui.playing) and \
                   not (btn['name'].startswith('filter_') and self.gui.active_filters.get(btn['name'].replace('filter_', ''), False)):
                     if not (self.clicked_btn_info and btn['name'] == self.clicked_btn_info['name'] and time.time() - self.clicked_btn_info['time'] < 0.15):
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
        if self.gui.scanner.running:
            status_text = "SCANNING..."
            status_color = (0, 255, 0)
        elif self.gui.playing:
            status_text = f"PLAYING (x{self.gui.speed})"
            status_color = (0, 255, 255)
        elif self.gui.current_pkt_idx > 0:
            status_text = "PAUSED"
            status_color = (255, 255, 0)
        cv2.putText(img, status_text, (700, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        if self.menu_open:
            self.draw_menu(img)

    def draw_menu(self, img):
        # File Button 위치 찾기
        file_btn = next((b for b in self.buttons if b['name'] == 'file'), None)
        if not file_btn: return
        
        bx1, by1, bx2, by2 = file_btn['rect']
        menu_w = 200
        menu_h = 150 # Recent 포함해서 늘림
        
        mx = bx1
        my = by2 + 5
        
        # 메뉴 배경
        cv2.rectangle(img, (mx, my), (mx+menu_w, my+menu_h), (40, 40, 40), -1)
        cv2.rectangle(img, (mx, my), (mx+menu_w, my+menu_h), (100, 100, 100), 1)
        
        self.menu_items_rects = []
        
        # Menu Items
        items = [('Open', 'open'), ('Exit', 'exit')]
        cy = my + 25
        
        for label, action in items:
            # Hover Check
            color = (200, 200, 200)
            if mx <= self.gui.mouse_x <= mx+menu_w and cy-20 <= self.gui.mouse_y <= cy+5:
                color = (0, 255, 255)
                cv2.rectangle(img, (mx+2, cy-20), (mx+menu_w-2, cy+5), (60, 60, 80), -1)
            
            cv2.putText(img, label, (mx+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
            self.menu_items_rects.append({'action': action, 'rect': (mx, cy-20, mx+menu_w, cy+5)})
            cy += 30
            
        # Divider
        cv2.line(img, (mx+5, cy-10), (mx+menu_w-5, cy-10), (100, 100, 100), 1)
        cy += 10
        
        # Recent Files
        cv2.putText(img, "Recent Files:", (mx+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        cy += 25
        
        for i, path in enumerate(self.recent_files[:3]): # 최대 3개만 표시
            fname = os.path.basename(path)
            if len(fname) > 20: fname = fname[:17] + "..."
            
            action = f"recent_{i}"
            
            color = (180, 180, 180)
            x = mx
            w = menu_w
            
            if mx <= self.gui.mouse_x <= mx+w and cy-20 <= self.gui.mouse_y <= cy+5:
                color = (0, 255, 255)
                cv2.rectangle(img, (x+2, cy-20), (x+w-2, cy+5), (60, 60, 80), -1)
                
            cv2.putText(img, f"{i+1}. {fname}", (x+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            self.menu_items_rects.append({'action': action, 'rect': (x, cy-20, x+w, cy+5)})
            
            cy += 30

    def handle_mouse_move(self, x, y):
        self.gui.mouse_x = x
        self.gui.mouse_y = y
        self.hover_btn = None
        
        if not self.menu_open:
            for btn in self.buttons:
                x1, y1, x2, y2 = btn['rect']
                if x1<=x<=x2 and y1<=y<=y2:
                    self.hover_btn = btn
                    break

    def handle_click(self, x, y):
        # 1. Menu Click
        if self.menu_open:
            clicked_menu = False
            for item in self.menu_items_rects:
                mx1, my1, mx2, my2 = item['rect']
                if mx1<=x<=mx2 and my1<=y<=my2:
                    self._handle_menu_action(item['action'])
                    clicked_menu = True
                    break
            self.menu_open = False
            if clicked_menu: return True # UI에서 처리됨

        # 2. Button Click
        if self.hover_btn:
            self.clicked_btn_info = {'name': self.hover_btn['name'], 'time': time.time()}
            self._handle_btn_action(self.hover_btn['name'])
            return True # UI에서 처리됨
            
        return False # UI 처리 안됨 (Main GUI에서 TreeView 등 처리)

    def _handle_menu_action(self, action):
        # 로직 처리는 Main GUI에 위임
        if hasattr(self.gui, '_handle_menu'):
            self.gui._handle_menu(action)

    def _open_file_dialog(self, path=None):
        # 이제 사용하지 않음 (Main GUI의 _open_file 사용)
        pass

    def _handle_btn_action(self, name):
        # Main GUI의 메서드 호출
        if hasattr(self.gui, '_handle_btn'):
            self.gui._handle_btn(name)
