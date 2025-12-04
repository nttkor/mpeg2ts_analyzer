import struct

# Stream Type 정의 (ISO/IEC 13818-1)
STREAM_TYPES = {
    0x00: "Reserved", 0x01: "MPEG-1 Video", 0x02: "MPEG-2 Video", 0x03: "MPEG-1 Audio",
    0x04: "MPEG-2 Audio", 0x06: "Private Data", 0x0F: "AAC Audio", 0x1B: "H.264 (AVC)",
    0x24: "H.265 (HEVC)", 0x81: "AC3 Audio"
}

class TSPacket:
    """188-byte TS Packet Model"""
    def __init__(self, raw_data):
        self.raw = raw_data
        self.pid = 0x1FFF
        self.pusi = False
        self.tei = False
        self.prio = False
        self.scram = 0
        self.adapt = 0
        self.cc = 0
        self.payload = b''
        
        if len(raw_data) >= 4:
            self._parse_header()
            self._extract_payload()

    def _parse_header(self):
        header = struct.unpack('>I', self.raw[:4])[0]
        self.tei = (header >> 23) & 0x1
        self.pusi = bool((header >> 22) & 0x1)
        self.prio = (header >> 21) & 0x1
        self.pid = (header >> 8) & 0x1FFF
        self.scram = (header >> 6) & 0x3
        self.adapt = (header >> 4) & 0x3
        self.cc = header & 0xF

    def _extract_payload(self):
        off = 4
        if self.adapt & 0x2: # Adapt Field Exists
            if len(self.raw) > 4:
                adapt_len = self.raw[4]
                off = 5 + adapt_len
        
        if off < 188:
            self.payload = self.raw[off:]
        else:
            self.payload = b''

class PSISection:
    """Base class for PSI Tables (PAT, PMT, etc.)"""
    def __init__(self, payload):
        self.valid = False
        if len(payload) < 1: return
        
        # Pointer Field
        pointer = payload[0]
        if len(payload) < 1 + pointer + 1: return
        
        # Section Start
        data = payload[1+pointer:]
        if len(data) < 3: return
        
        self.table_id = data[0]
        self.section_length = ((data[1] & 0x0F) << 8) | data[2]
        self.section_data = data
        self.valid = True

class PATSection(PSISection):
    """Program Association Table"""
    def __init__(self, payload):
        super().__init__(payload)
        self.programs = {} # { prog_num: pmt_pid }
        if self.valid and self.table_id == 0x00:
            self._parse_programs()
            
    def _parse_programs(self):
        # Header 8 bytes (TableID...LastSecNum)
        if len(self.section_data) < 8: return
        
        # Loop limit: section starts at offset 0.
        # Section Length includes everything after length field (offset 3).
        # CRC is last 4 bytes.
        end_idx = 3 + self.section_length - 4
        
        i = 8
        while i < end_idx:
            if i + 4 > len(self.section_data): break
            prog_num = (self.section_data[i] << 8) | self.section_data[i+1]
            pid = ((self.section_data[i+2] & 0x1F) << 8) | self.section_data[i+3]
            
            if prog_num != 0:
                self.programs[prog_num] = pid
            i += 4

class PMTSection(PSISection):
    """Program Map Table"""
    def __init__(self, payload):
        super().__init__(payload)
        self.pcr_pid = 0x1FFF
        self.streams = {} # { pid: {type, desc} }
        if self.valid and self.table_id == 0x02:
            self._parse_streams()
            
    def _parse_streams(self):
        data = self.section_data
        if len(data) < 12: return
        
        self.pcr_pid = ((data[8] & 0x1F) << 8) | data[9]
        prog_info_len = ((data[10] & 0x0F) << 8) | data[11]
        
        idx = 12 + prog_info_len
        end_idx = 3 + self.section_length - 4 # Exclude CRC
        
        while idx < end_idx:
            if idx + 5 > len(data): break
            
            stype = data[idx]
            epid = ((data[idx+1] & 0x1F) << 8) | data[idx+2]
            es_info_len = ((data[idx+3] & 0x0F) << 8) | data[idx+4]
            
            desc = STREAM_TYPES.get(stype, f"Unk(0x{stype:02X})")
            self.streams[epid] = {'type': stype, 'desc': desc}
            
            idx += 5 + es_info_len

class PESHeader:
    """Packetized Elementary Stream Header"""
    def __init__(self, payload):
        self.valid = False
        self.stream_id = 0
        self.length = 0
        self.pts = None
        self.dts = None
        self.header_len = 0
        
        if len(payload) >= 6:
            self._parse(payload)
            
    def _parse(self, data):
        start_code = struct.unpack('>I', b'\x00' + data[:3])[0]
        if start_code != 1: return
        
        self.stream_id = data[3]
        self.length = struct.unpack('>H', data[4:6])[0]
        self.valid = True
        
        # Optional Header
        if (0xC0 <= self.stream_id <= 0xEF) or self.stream_id == 0xBD:
            if len(data) > 9:
                flags_2 = data[7]
                pts_dts_flag = (flags_2 >> 6) & 0x3
                self.header_len = data[8]
                
                if pts_dts_flag == 2: # PTS
                    if len(data) >= 14:
                        self.pts = self._parse_pts(data[9:14])
                elif pts_dts_flag == 3: # PTS + DTS
                    if len(data) >= 19:
                        self.pts = self._parse_pts(data[9:14])
                        self.dts = self._parse_pts(data[14:19])

    def _parse_pts(self, data):
        if len(data) < 5: return 0.0
        val = struct.unpack('>Q', b'\x00\x00\x00' + data)[0]
        pts = ((val >> 29) & 0x0E) << 29 | \
              ((val >> 14) & 0xFFFE) << 14 | \
              ((val >> 0) & 0xFFFE) >> 1
        return pts / 90000.0 # Seconds

