"""
[파일 개요]
MPEG2-TS 분석기 (MTS430 스타일)
TS 파일의 PSI(PAT, PMT)를 파싱하여 프로그램 및 구성 요소(Video/Audio)의 계층 구조를 분석하고,
실시간 패킷 통계를 OpenCV GUI에 트리 형태로 표시합니다.

[기능]
1. PSI 파싱: PAT(PID 0) -> PMT -> Component PID 자동 탐색
2. 계층적 뷰: Program -> Video/Audio PID 구조 시각화
3. 실시간 통계: 각 PID별 패킷 카운트 및 오디오 상태 모니터링
4. 플레이어 연동: 'p' 키로 영상 재생
"""
import cv2
import numpy as np
import threading
import time
import struct
import os
import sys
import importlib.util

# 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 파일 경로
ts_file_path = r"D:\git\mpeg2TS\TS\mama_uhd2.ts"

# 분석 데이터 (공유)
analysis_data = {
    'packet_count': 0,
    'programs': {},        # { prog_num: {'pmt_pid': x, 'pids': { pid: {'type': x, 'desc': 'Video'} }} }
    'pid_map': {},         # { pid: {'prog_num': 1, 'type': 0x1B, ...} } -> 역참조용
    'pid_counts': {},      # { pid: count }
    'last_log': "Initializing...",
    'running': True
}

# Stream Type 정의 (ISO/IEC 13818-1)
STREAM_TYPES = {
    0x00: "Reserved",
    0x01: "MPEG-1 Video",
    0x02: "MPEG-2 Video",
    0x03: "MPEG-1 Audio",
    0x04: "MPEG-2 Audio",
    0x06: "Private Data (AC3/Subtitle)",
    0x0F: "AAC Audio",
    0x1B: "H.264 (AVC)",
    0x24: "H.265 (HEVC)",
    0x81: "AC3 Audio" 
}

def get_stream_desc(stream_type):
    return STREAM_TYPES.get(stream_type, f"Unknown (0x{stream_type:02X})")

def parse_section_header(payload):
    """PSI Section Header 파싱 (Table ID, Section Length 등)"""
    if len(payload) < 3: return None
    table_id = payload[0]
    section_length = ((payload[1] & 0x0F) << 8) | payload[2]
    return table_id, section_length

def parse_pat(payload):
    """PID 0 (PAT) 파싱 -> Program Number 및 PMT PID 추출"""
    # Pointer Field 스킵
    if len(payload) < 1: return 0
    pointer_field = payload[0]
    if len(payload) < 1 + pointer_field: return 0
    section_data = payload[1 + pointer_field:]
    
    res = parse_section_header(section_data)
    if not res: return 0
    tid, length = res
    
    if tid != 0x00: return 0 # Not PAT
    
    # PAT Data (8바이트 헤더 이후부터 루프)
    # Program Number (2) + Reserved (3 bit) + PMT PID (13 bit)
    data = section_data[8:]
    programs_found = 0
    
    i = 0
    while i < len(data) - 4: # CRC 4바이트 제외
        prog_num = (data[i] << 8) | data[i+1]
        pmt_pid = ((data[i+2] & 0x1F) << 8) | data[i+3]
        
        if prog_num != 0: # Network PID(0) 제외
            if prog_num not in analysis_data['programs']:
                analysis_data['programs'][prog_num] = {'pmt_pid': pmt_pid, 'pids': {}}
                analysis_data['last_log'] = f"Found Program {prog_num}, PMT PID: 0x{pmt_pid:X}"
            programs_found += 1
        i += 4
    
    return programs_found

def parse_pmt(payload, prog_num):
    """PMT 파싱 -> Component PID 및 Stream Type 추출"""
    if len(payload) < 1: return
    pointer_field = payload[0]
    if len(payload) < 1 + pointer_field: return
    section_data = payload[1 + pointer_field:]
    
    res = parse_section_header(section_data)
    if not res: return
    tid, length = res
    
    if tid != 0x02: return # Not PMT
    
    # PMT Header (Program Info Length까지 12바이트)
    if len(section_data) < 12: return
    # pcr_pid = ((section_data[8] & 0x1F) << 8) | section_data[9]
    prog_info_len = ((section_data[10] & 0x0F) << 8) | section_data[11]
    
    # Descriptor 이후부터 Loop 시작
    idx = 12 + prog_info_len
    components_data = section_data[idx:]
    
    i = 0
    while i < len(components_data) - 4: # CRC 제외
        if i + 5 > len(components_data): break
        
        stream_type = components_data[i]
        elem_pid = ((components_data[i+1] & 0x1F) << 8) | components_data[i+2]
        es_info_len = ((components_data[i+3] & 0x0F) << 8) | components_data[i+4]
        
        # 데이터 저장
        prog = analysis_data['programs'].get(prog_num)
        if prog:
            desc = get_stream_desc(stream_type)
            if elem_pid not in prog['pids']:
                prog['pids'][elem_pid] = {'type': stream_type, 'desc': desc}
                analysis_data['pid_map'][elem_pid] = {'prog': prog_num, 'type': stream_type, 'desc': desc}
                # analysis_data['last_log'] = f"Found PID 0x{elem_pid:X} ({desc})"
        
        i += 5 + es_info_len

def parser_thread_func():
    global analysis_data
    
    if not os.path.exists(ts_file_path):
        analysis_data['last_log'] = "File not found!"
        return

    with open(ts_file_path, "rb") as f:
        analysis_data['last_log'] = "Scanning PSI Tables..."
        
        while analysis_data['running']:
            packet = f.read(188)
            if len(packet) != 188:
                break
            
            analysis_data['packet_count'] += 1
            
            header = struct.unpack('>I', packet[:4])[0]
            pid = (header >> 8) & 0x1FFF
            pusi = (header >> 22) & 0x1
            
            # PID Count
            analysis_data['pid_counts'][pid] = analysis_data['pid_counts'].get(pid, 0) + 1
            
            # 1. PAT Parsing (PID 0)
            if pid == 0 and pusi:
                payload_off = 4
                adapt = (header >> 4) & 0x3
                if adapt & 0x2: payload_off = 5 + packet[4]
                if payload_off < 188:
                    parse_pat(packet[payload_off:])
            
            # 2. PMT Parsing (Dynamic PID)
            # 현재 발견된 프로그램들의 PMT PID인지 확인
            for prog_num, prog_data in analysis_data['programs'].items():
                if pid == prog_data['pmt_pid'] and pusi:
                    payload_off = 4
                    adapt = (header >> 4) & 0x3
                    if adapt & 0x2: payload_off = 5 + packet[4]
                    if payload_off < 188:
                        parse_pmt(packet[payload_off:], prog_num)
            
            # 3. Audio Sync Check (임의의 오디오 PID)
            # pid_map에 등록된 PID 중 Audio 타입인 경우
            if pid in analysis_data['pid_map']:
                p_info = analysis_data['pid_map'][pid]
                # MPEG Audio(0x03, 0x04) or AAC(0x0F) or AC3(0x81)
                if p_info['type'] in [0x03, 0x04, 0x0F, 0x81] and pusi:
                    payload_off = 4
                    adapt = (header >> 4) & 0x3
                    if adapt & 0x2: payload_off = 5 + packet[4]
                    if payload_off < 188:
                        payload = packet[payload_off:]
                        # PES Start Code Check
                        if len(payload) > 6 and struct.unpack('>I', b'\x00'+payload[:3])[0] == 0x000001:
                             # Sync Word 간단 체크 (첫바이트 FF)
                             # 실제로는 PES Header Length 건너뛰어야 함
                             p_info['status'] = '[Active]'

            if analysis_data['packet_count'] % 2000 == 0:
                time.sleep(0.001)

def run_player():
    try:
        spec = importlib.util.spec_from_file_location("play_ts_opencv", os.path.join(os.path.dirname(__file__), "play_ts_opencv.py"))
        player_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(player_module)
        player_module.main()
    except Exception as e:
        print(f"Player Error: {e}")

def main():
    t = threading.Thread(target=parser_thread_func)
    t.daemon = True
    t.start()

    window_name = "MPEG2-TS Analyzer (MTS430 Style)"
    cv2.namedWindow(window_name)
    
    while True:
        board = np.zeros((700, 900, 3), dtype=np.uint8)
        
        # Header
        cv2.rectangle(board, (0, 0), (900, 60), (50, 50, 50), -1)
        cv2.putText(board, "MPEG2-TS Analyzer", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(board, f"Pkts: {analysis_data['packet_count']}", (700, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        y = 100
        # Tree View Drawing
        if not analysis_data['programs']:
            cv2.putText(board, "Scanning PAT/PMT...", (30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
        
        for prog_num, prog_data in analysis_data['programs'].items():
            # Program Node
            cv2.putText(board, f"[+] Program {prog_num} (PMT: 0x{prog_data['pmt_pid']:X})", (30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
            y += 35
            
            # PMT PID Stat
            pmt_cnt = analysis_data['pid_counts'].get(prog_data['pmt_pid'], 0)
            cv2.putText(board, f"    PMT Table (Cnt: {pmt_cnt})", (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            y += 30
            
            # Components
            for pid, p_info in prog_data['pids'].items():
                cnt = analysis_data['pid_counts'].get(pid, 0)
                
                # Icon-like text
                icon = "[?]"
                color = (200, 200, 200)
                if "Video" in p_info['desc']: 
                    icon = "[V]"
                    color = (0, 255, 255) # Yellow for Video
                elif "Audio" in p_info['desc']: 
                    icon = "[A]"
                    color = (0, 255, 0) # Green for Audio
                
                status = p_info.get('status', '')
                text = f"    |-- {icon} PID 0x{pid:X} : {p_info['desc']} (Cnt: {cnt}) {status}"
                
                cv2.putText(board, text, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
                y += 25
            
            y += 20 # Gap between programs

        # Footer Log
        cv2.line(board, (0, 620), (900, 620), (100, 100, 100), 1)
        cv2.putText(board, f"Log: {analysis_data['last_log']}", (20, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 255), 1)
        cv2.putText(board, "[P] Play Video   [Q] Quit", (20, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow(window_name, board)
        
        key = cv2.waitKey(50) & 0xFF
        if key == ord('q'):
            analysis_data['running'] = False
            break
        elif key == ord('p'):
            run_player()

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()