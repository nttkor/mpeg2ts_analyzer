"""
[파일 개요]
MPEG2-TS 분석 코어 모듈 (TSParser)
GUI와 독립적으로 TS 파일을 읽고 패킷 구조, PSI(PAT/PMT) 테이블, PES 헤더 등을 분석합니다.
"""
import struct
import os
import threading
import time
import zlib

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
        
        # Precompute CRC32 Table for MPEG-2 (Poly: 0x04C11DB7)
        self._crc32_table = []
        poly = 0x04C11DB7
        for i in range(256):
            crc = i << 24
            for _ in range(8):
                if (crc & 0x80000000):
                    crc = (crc << 1) ^ poly
                else:
                    crc = (crc << 1)
                crc &= 0xFFFFFFFF
            self._crc32_table.append(crc)


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

    def calculate_crc32(self, data):
        """MPEG2-TS CRC32 Calculation (Using Table)"""
        crc = 0xFFFFFFFF
        for byte in data:
            idx = ((crc >> 24) ^ byte) & 0xFF
            crc = ((crc << 8) ^ self._crc32_table[idx]) & 0xFFFFFFFF
        return crc


    def parse_header(self, packet):
        """TS 패킷 헤더 파싱 (PID, PUSI, Adapt, ContinuityCounter)"""
        if len(packet) < 4: return 0, 0, 0, 0
        header = struct.unpack('>I', packet[:4])[0]
        pid = (header >> 8) & 0x1FFF
        pusi = (header >> 22) & 0x1
        adapt = (header >> 4) & 0x3
        cnt = header & 0xF
        return pid, pusi, adapt, cnt

    def parse_adapt_field(self, packet):
        """
        Adaptation Field 상세 파싱
        :param packet: 188-byte TS packet
        :return: dict with adapt field details
        """
        pid, pusi, adapt, cnt = self.parse_header(packet)
        info = {
            'exist': False,
            'length': 0,
            'discontinuity': 0,
            'random_access': 0,
            'es_priority': 0,
            'pcr_flag': 0,
            'opcr_flag': 0,
            'splicing_point_flag': 0,
            'transport_private_data_flag': 0,
            'adapt_field_extension_flag': 0,
            'pcr': None,
            'opcr': None
        }
        
        # Check Adaptation Field Control
        # 00: Reserved, 01: Payload Only, 10: Adapt Only, 11: Adapt + Payload
        if adapt == 0 or adapt == 1:
            return info

        if len(packet) < 5: return info

        adapt_len = packet[4]
        info['exist'] = True
        info['length'] = adapt_len
        
        if adapt_len > 0:
            if len(packet) < 6: return info
            flags = packet[5]
            info['discontinuity'] = (flags >> 7) & 0x1
            info['random_access'] = (flags >> 6) & 0x1
            info['es_priority'] = (flags >> 5) & 0x1
            info['pcr_flag'] = (flags >> 4) & 0x1
            info['opcr_flag'] = (flags >> 3) & 0x1
            info['splicing_point_flag'] = (flags >> 2) & 0x1
            info['transport_private_data_flag'] = (flags >> 1) & 0x1
            info['adapt_field_extension_flag'] = flags & 0x1
            
            idx = 6
            # PCR Parsing
            if info['pcr_flag']:
                if len(packet) >= idx + 6:
                    pcr_bytes = packet[idx:idx+6]
                    # PCR is 33 bits base + 6 bits reserved + 9 bits extension
                    v = struct.unpack('>Q', b'\x00\x00' + pcr_bytes)[0]
                    pcr_base = (v >> 15) & 0x1FFFFFFFF
                    pcr_ext = v & 0x1FF
                    info['pcr'] = pcr_base * 300 + pcr_ext
                    idx += 6
            
            # OPCR Parsing
            if info['opcr_flag']:
                if len(packet) >= idx + 6:
                    opcr_bytes = packet[idx:idx+6]
                    v = struct.unpack('>Q', b'\x00\x00' + opcr_bytes)[0]
                    opcr_base = (v >> 15) & 0x1FFFFFFFF
                    opcr_ext = v & 0x1FF
                    info['opcr'] = opcr_base * 300 + opcr_ext
                    idx += 6
                    
        return info

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
        if off >= 188: return None
        
        payload = packet[off:]
        if len(payload) < 1: return None
        pointer = payload[0]
        if len(payload) < 1 + pointer: return None
        data = payload[1+pointer:]
        
        # Section Header (3 bytes) + Table ID Ext (2) + Ver/Num (1) + SecNum (1) + LastSecNum (1) = 8 bytes
        if len(data) < 8: return None
        
        table_id = data[0]
        section_length = ((data[1] & 0x0F) << 8) | data[2]
        
        # [DEBUG] PAT Header Info
        # print(f"[PAT DEBUG] Len: {section_length}, Raw: {data[:16].hex()}...")

        # 1.3b PAT Table ID Check (Should be 0x00)
        is_valid_tid = (table_id == 0x00)
        
        # 2.2 CRC Check
        total_len = 3 + section_length
        
        is_crc_valid = None
        calc_crc_val = None
        expected_crc_val = None
        
        if len(data) >= total_len:
            section_bytes = data[:total_len]
            if self.calculate_crc32(section_bytes) == 0:
                is_crc_valid = True
            else:
                is_crc_valid = False
            calc_crc_val = self.calculate_crc32(section_bytes[:-4])
            expected_crc_val = struct.unpack('>I', section_bytes[-4:])[0]
        else:
            is_crc_valid = None
        
        # Parsing Programs
        section_data = data[8:]
        
        i = 0
        prog_data_len = section_length - 5 - 4
        limit = min(len(section_data), prog_data_len)
        
        while i + 4 <= limit:
            prog_num = (section_data[i] << 8) | section_data[i+1]
            pmt_pid = ((section_data[i+2] & 0x1F) << 8) | section_data[i+3]
            
            # [수정] Program 0 (NIT) 포함 모든 프로그램 수집
            if prog_num not in self.programs:
                self.programs[prog_num] = {'pmt_pid': pmt_pid, 'pids': {}}
                self.last_log = f"Found Program {prog_num}"
            else:
                if self.programs[prog_num]['pmt_pid'] != pmt_pid:
                        self.programs[prog_num]['pmt_pid'] = pmt_pid
                        self.programs[prog_num]['pids'] = {} 
            
            i += 4
            
        return {
            'valid_tid': is_valid_tid, 
            'valid_crc': is_crc_valid,
            'calc_crc': calc_crc_val,
            'expected_crc': expected_crc_val
        }

    def _parse_pmt(self, packet, adapt, prog_node):
        off = 4
        if adapt & 0x2: off = 5 + packet[4]
        if off >= 188: return None
        
        payload = packet[off:]
        if len(payload) < 1: return None
        pointer = payload[0]
        if len(payload) < 1 + pointer: return None
        data = payload[1+pointer:]
        
        if len(data) < 12: return None
        
        table_id = data[0]
        section_length = ((data[1] & 0x0F) << 8) | data[2]
        
        # 1.5b PMT Table ID Check (Should be 0x02)
        is_valid_tid = (table_id == 0x02)
        
        # 2.2 CRC Check
        total_len = 3 + section_length
        
        is_crc_valid = None
        calc_crc_val = None
        expected_crc_val = None
        
        if len(data) >= total_len:
            section_bytes = data[:total_len]
            if self.calculate_crc32(section_bytes) == 0:
                is_crc_valid = True
            else:
                is_crc_valid = False
            
            calc_crc_val = self.calculate_crc32(section_bytes[:-4])
            expected_crc_val = struct.unpack('>I', section_bytes[-4:])[0]
        else:
            is_crc_valid = None
        
        # PCR PID Parsing (13 bits)
        pcr_pid = ((data[8] & 0x1F) << 8) | data[9]
        prog_node['pcr_pid_val'] = pcr_pid  # Store PCR PID
        
        prog_info_len = ((data[10] & 0x0F) << 8) | data[11]
        
        idx = 12 + prog_info_len
        comp_data = data[idx:]
        
        # Loop limit: section_length - 9 (fixed header) - 4 (CRC) - prog_info_len
        # Simplified: just ensure buffer safety
        limit = total_len - 4 # Exclude CRC
        
        i = 0
        # Re-calculate index relative to comp_data start
        # comp_data starts at 12 + prog_info_len
        # absolute limit is total_len. 
        # relative limit for while loop:
        
        while i < len(comp_data) - 4:
            if 12 + prog_info_len + i + 5 > limit: break
            
            stype = comp_data[i]
            epid = ((comp_data[i+1] & 0x1F) << 8) | comp_data[i+2]
            es_len = ((comp_data[i+3] & 0x0F) << 8) | comp_data[i+4]
            
            desc = STREAM_TYPES.get(stype, f"Unk(0x{stype:02X})")
            
            if epid not in prog_node['pids']:
                prog_node['pids'][epid] = {'type': stype, 'desc': desc}
                self.pid_map[epid] = {'type': stype, 'desc': desc}
            
            i += 5 + es_len
            
        return {
            'valid_tid': is_valid_tid, 
            'valid_crc': is_crc_valid,
            'calc_crc': calc_crc_val,
            'expected_crc': expected_crc_val
        }

    def parse_pes_header(self, payload):
        """
        PES 헤더를 파싱하여 딕셔너리로 반환
        :param payload: TS 패킷의 Payload (Byte string)
        """
        if len(payload) < 6: return None
        
        # Start Code Prefix (3 bytes) + Stream ID (1 byte) + PES Packet Length (2 bytes)
        start_code = struct.unpack('>I', b'\x00' + payload[:3])[0]
        if start_code != 1: return None
        
        stream_id = payload[3]
        pes_length = struct.unpack('>H', payload[4:6])[0]
        
        info = {
            'stream_id': stream_id,
            'pes_length': pes_length,
            'pts': None,
            'dts': None
        }
        
        # Optional PES Header
        # Stream ID check: video, audio, private_1 (BD)
        if (0xC0 <= stream_id <= 0xEF) or stream_id == 0xBD:
            if len(payload) > 9:
                flags_2 = payload[7]
                pts_dts_flag = (flags_2 >> 6) & 0x3
                header_len = payload[8]
                
                # PTS/DTS Parsing
                if pts_dts_flag == 2: # PTS only
                    if len(payload) >= 14:
                        pts = self._parse_pts(payload[9:14])
                        info['pts'] = pts
                elif pts_dts_flag == 3: # PTS and DTS
                    if len(payload) >= 19:
                        pts = self._parse_pts(payload[9:14])
                        dts = self._parse_pts(payload[14:19])
                        info['pts'] = pts
                        info['dts'] = dts
                
        return info

    def _parse_pts(self, data):
        # 33-bit PTS parsing logic
        if len(data) < 5: return 0
        val = struct.unpack('>Q', b'\x00\x00\x00' + data)[0]
        pts = ((val >> 29) & 0x0E) << 29 | \
              ((val >> 14) & 0xFFFE) << 14 | \
              ((val >> 0) & 0xFFFE) >> 1
        return pts
