import cv2
import os
import json
import sys
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
            
            label = btn['label']
            if btn['name'] == 'play':
                label = "||" if self.gui.playing else ">"
                if self.gui.playing: color = (0, 100, 0)
            elif btn['name'] == 'rev':
                label = "<<" if self.gui.playing else "<-"
            elif btn['name'] == 'ff':
                label = ">>" if self.gui.playing else "->"
            elif btn['name'] == 'bscan':
                label = "Stop" if self.gui.scanner.running else "BScan"
                if self.gui.scanner.running: 
                    color = (0, 100, 0)
                elif self.gui.scanner.completed:
                    label = "Report"
                    color = (0, 100, 100)
                else: color = (50, 50, 50)
            
            border_color = (150, 150, 150)
            thickness = 1
            
            if btn == self.hover_btn:
                if not (btn['name'] == 'bscan' and self.gui.scanner.running) and not (btn['name'] == 'play' and self.gui.playing):
                     color = (90, 90, 110)
                border_color = (0, 255, 255)
                thickness = 2

            cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
            cv2.rectangle(img, (x1, y1), (x2, y2), border_color, thickness)
            
            ts = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
            tx = x1 + (x2-x1-ts[0])//2
            ty = y1 + (y2-y1+ts[1])//2
            cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

        # Status Text
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

    def draw_menu(self, img):
        if not self.menu_open: return
        
        bx, by, bw, bh = self.buttons[0]['rect']
        x = bx
        y = bh + 5
        w = 250
        
        items = [('Open File...', 'open'), ('Exit', 'exit')]
        if self.recent_files:
            items.insert(1, ('--- Recent Files ---', None))
            for i, f in enumerate(self.recent_files):
                fname = os.path.basename(f)
                items.insert(2+i, (f"{i+1}. {fname}", f'recent_{i}'))
        
        h = len(items) * 30 + 10
        cv2.rectangle(img, (x, y), (x+w, y+h), (50, 50, 50), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (200, 200, 200), 1)
        
        cy = y + 25
        self.menu_items_rects = []
        
        for label, action in items:
            color = (255, 255, 255)
            if action is None: color = (150, 150, 150)
            
            if action and x <= self.gui.mouse_x <= x+w and cy-20 <= self.gui.mouse_y <= cy+5:
                cv2.rectangle(img, (x+2, cy-20), (x+w-2, cy+5), (80, 80, 100), -1)
            
            cv2.putText(img, label, (x+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            if action:
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
            self._handle_btn_action(self.hover_btn['name'])
            return True # UI에서 처리됨
            
        return False # UI 처리 안됨 (Main GUI에서 TreeView 등 처리)

    def _handle_menu_action(self, action):
        if action == 'exit':
            sys.exit(0)
        elif action == 'open':
            self._open_file_dialog()
        elif action.startswith('recent_'):
            idx = int(action.split('_')[1])
            if idx < len(self.recent_files):
                self._open_file_dialog(self.recent_files[idx])

    def _open_file_dialog(self, path=None):
        if not path:
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askopenfilename(filetypes=[("MPEG2-TS Files", "*.ts;*.tp;*.m2ts"), ("All Files", "*.*")])
            root.destroy()
        
        if path and os.path.exists(path):
            self.gui.load_file(path) # Main GUI의 로드 메서드 호출

    def _handle_btn_action(self, name):
        if name == 'file':
            self.menu_open = not self.menu_open
        elif name == 'play': self.gui._toggle_play()
        elif name == 'stop': 
            self.gui.playing = False
            self.gui.current_pkt_idx = 0
            self.gui.update_packet_view()
        elif name == 'rev':
            if self.gui.playing: self.gui.speed = -1.0
            else: self.gui._step_packet(-1)
        elif name == 'ff':
            if self.gui.playing: self.gui.speed = 2.0
            else: self.gui._step_packet(1)
        elif name == 'ext_play':
            self.gui._launch_player()
        elif name == 'bscan':
            if self.gui.scanner.running: 
                self.gui.scanner.stop()
            elif self.gui.scanner.completed:
                self.gui.bscan_running = True
            else: 
                self.gui.scanner.start()
        elif name == 'prev': self.gui._step_packet(-1)
        elif name == 'next': self.gui._step_packet(1)

