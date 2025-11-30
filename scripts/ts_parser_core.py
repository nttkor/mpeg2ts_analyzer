"""
[파일 개요]
MPEG2-TS 분석 코어 모듈 (TSParser)
GUI와 독립적으로 TS 파일을 읽고 패킷 구조, PSI(PAT/PMT) 테이블, PES 헤더 등을 분석합니다.
"""
import struct
import os
import threading
import time

# Stream Type 정의 (ISO/IEC 13818-1)
STREAM_TYPES = {
    0x00: "Reserved", 0x01: "MPEG-1 Video", 0x02: "MPEG-2 Video", 0x03: "MPEG-1 Audio",
    0x04: "MPEG-2 Audio", 0x06: "Private Data", 0x0F: "AAC Audio", 0x1B: "H.264 (AVC)",
    0x24: "H.265 (HEVC)", 0x81: "AC3 Audio"
}

class TSParser:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self.total_pkts = self.file_size // 188
        
        # 분석 상태 데이터
        self.packet_count = 0
        self.programs = {}  # { prog_num: {'pmt_pid': x, 'pids': {}} }
        self.pid_counts = {} 
        self.pid_map = {}   # { pid: {'type': x, 'desc': ''} }
        self.running = False
        self.last_log = "Ready."
        
        self._thread = None

    def start_background_parsing(self):
        """백그라운드 파싱 스레드 시작"""
        if self.running: return
        self.running = True
        self._thread = threading.Thread(target=self._parsing_loop)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """파싱 중단"""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def quick_scan(self, limit=20000):
        """초기 구조 파악을 위해 앞부분만 빠르게 스캔 (Blocking)"""
        if not os.path.exists(self.file_path): return
        
        with open(self.file_path, "rb") as f:
            self.last_log = "Quick Scanning PSI..."
            for _ in range(limit):
                packet = f.read(188)
                if len(packet) != 188: break
                
                pid, pusi, adapt, _ = self.parse_header(packet)
                
                # 구조만 파악하고 카운트는 올리지 않음 (선택 사항)
                if pid == 0 and pusi: 
                    self._parse_pat(packet, adapt)
                
                for prog in list(self.programs.values()):
                    if pid == prog['pmt_pid'] and pusi:
                        self._parse_pmt(packet, adapt, prog)
            
            self.last_log = "Ready."

    def read_packet_at(self, index):
        """특정 인덱스의 패킷(188 bytes)을 읽어서 반환 (Seek 기능용)"""
        if not os.path.exists(self.file_path): return None
        try:
            with open(self.file_path, "rb") as f:
                f.seek(index * 188)
                data = f.read(188)
                return data if len(data) == 188 else None
        except: return None

    def parse_header(self, packet):
        """TS 패킷 헤더 파싱 (PID, PUSI, Adapt, ContinuityCounter)"""
        if len(packet) < 4: return 0, 0, 0, 0
        header = struct.unpack('>I', packet[:4])[0]
        pid = (header >> 8) & 0x1FFF
        pusi = (header >> 22) & 0x1
        adapt = (header >> 4) & 0x3
        cnt = header & 0xF
        return pid, pusi, adapt, cnt

    def _parsing_loop(self):
        """백그라운드 파싱 루프: 파일 전체를 스캔하며 구조 파악"""
        if not os.path.exists(self.file_path):
            self.last_log = "File not found."
            self.running = False
            return

        with open(self.file_path, "rb") as f:
            self.last_log = "Scanning..."
            while self.running:
                packet = f.read(188)
                if len(packet) != 188: 
                    self.last_log = "Scan Completed."
                    self.running = False
                    break
                
                self.packet_count += 1
                pid, pusi, adapt, _ = self.parse_header(packet)
                
                # PID 카운팅
                self.pid_counts[pid] = self.pid_counts.get(pid, 0) + 1
                
                # PSI Parsing (PAT)
                if pid == 0 and pusi: 
                    self._parse_pat(packet, adapt)
                
                # PSI Parsing (PMT)
                for prog in list(self.programs.values()):
                    if pid == prog['pmt_pid'] and pusi:
                        self._parse_pmt(packet, adapt, prog)

                # GUI 반응성을 위해 CPU 양보
                if self.packet_count % 5000 == 0:
                    time.sleep(0.001)

    def _parse_pat(self, packet, adapt):
        off = 4
        if adapt & 0x2: off = 5 + packet[4]
        if off >= 188: return
        
        payload = packet[off:]
        if len(payload) < 1: return
        pointer = payload[0]
        if len(payload) < 1 + pointer: return
        data = payload[1+pointer:]
        
        if len(data) < 8: return
        
        section_data = data[8:]
        i = 0
        while i < len(section_data) - 4:
            prog_num = (section_data[i] << 8) | section_data[i+1]
            pmt_pid = ((section_data[i+2] & 0x1F) << 8) | section_data[i+3]
            
            if prog_num != 0:
                if prog_num not in self.programs:
                    self.programs[prog_num] = {'pmt_pid': pmt_pid, 'pids': {}}
                    self.last_log = f"Found Program {prog_num}"
            i += 4

    def _parse_pmt(self, packet, adapt, prog_node):
        off = 4
        if adapt & 0x2: off = 5 + packet[4]
        if off >= 188: return
        
        payload = packet[off:]
        if len(payload) < 1: return
        pointer = payload[0]
        if len(payload) < 1 + pointer: return
        data = payload[1+pointer:]
        
        if len(data) < 12: return
        prog_info_len = ((data[10] & 0x0F) << 8) | data[11]
        
        idx = 12 + prog_info_len
        comp_data = data[idx:]
        
        i = 0
        while i < len(comp_data) - 4:
            if i + 5 > len(comp_data): break
            
            stype = comp_data[i]
            epid = ((comp_data[i+1] & 0x1F) << 8) | comp_data[i+2]
            es_len = ((comp_data[i+3] & 0x0F) << 8) | comp_data[i+4]
            
            desc = STREAM_TYPES.get(stype, f"Unk(0x{stype:02X})")
            
            if epid not in prog_node['pids']:
                prog_node['pids'][epid] = {'type': stype, 'desc': desc}
                self.pid_map[epid] = {'type': stype, 'desc': desc}
            
            i += 5 + es_len
