"""
[파일 개요]
MPEG2-TS 백그라운드 스캐너 (TSScanner)

[목적 및 필요성]
TSParser(Core)는 '패킷 단위 읽기'와 '헤더 파싱' 같은 기본 기능에 집중하고,
'파일 전체를 순회하며 통계를 내는 작업'은 별도 클래스로 분리하여 복잡도를 낮춥니다.
이 스캐너는 별도 스레드에서 동작하며, GUI가 멈추지 않게 하면서 파일의 전체 구조(PAT/PMT)와
PID별 패킷 개수, 오디오 상태 등을 지속적으로 업데이트합니다.
"""
import struct
import threading
import time
import os
import datetime
import sys

# Jitter Analyzer 연동
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from zitter_measurement import TSJitterAnalyzer
except ImportError:
    TSJitterAnalyzer = None

try:
    from ts_etr290_analyzer import TSETR290Analyzer
except ImportError:
    TSETR290Analyzer = None

class TSScanner:
    """
    백그라운드에서 TS 파일을 처음부터 끝까지 읽으며 분석하는 클래스.
    TSParser 인스턴스를 참조하여 파싱 로직을 수행하고 결과를 공유합니다.
    """
    def __init__(self, parser_instance):
        self.parser = parser_instance       # 파싱 도구 및 데이터 저장소 공유 (TSParser 객체)
        self.running = False                # 스캔 루프 실행 여부 플래그
        self.completed = False              # 스캔 완료 여부
        self._thread = None                 # 백그라운드 작업 스레드
        self.file_path = parser_instance.file_path  # 분석할 파일 경로
        self.report = []                    # 분석 결과 리포트
        
        # --- 상세 통계 데이터 저장소 ---
        self.stats = {} 
        # 구조:
        # self.stats[pid] = {
        #    'cc_errors': 0, 
        #    'last_cc': -1,
        #    'pcr_list': [], # (offset, pcr_val) for Jitter Analysis
        #    'last_pcr': None,
        #    'pcr_intervals': [], # seconds
        #    'last_pts': None,
        #    'pts_intervals': [], # seconds
        #    'scrambled_count': 0
        # }
        
        self.jitter_analyzers = {} # { pid: TSJitterAnalyzer() }
        
        # ETR-290 Analyzer
        self.etr290 = TSETR290Analyzer() if TSETR290Analyzer else None

    def start(self):
        """백그라운드 스캔 스레드 시작"""
        if self.running: return             # 이미 실행 중이면 무시
        
        # 재시작 시 초기화
        self.parser.packet_count = 0
        self.parser.pid_counts = {}
        self.completed = False
        
        # 통계 초기화
        self.stats = {}
        self.jitter_analyzers = {}
        if self.etr290:
            self.etr290 = TSETR290Analyzer()
        
        self.running = True                 # 실행 플래그 ON
        self._thread = threading.Thread(target=self._scan_loop)
        self._thread.daemon = True          # 메인 프로그램 종료 시 함께 종료되도록 설정
        self._thread.start()                # 스레드 시작

    def stop(self):
        """스캔 중단 요청"""
        self.running = False                # 루프 종료 조건 설정
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)  # 스레드가 안전하게 종료될 때까지 대기 (최대 1초)
            self._thread = None             # 스레드 핸들 초기화

    def _scan_loop(self):
        """실제 파일 스캔을 수행하는 워커 메서드"""
        if not os.path.exists(self.file_path):
            self.parser.last_log = "Scanner: File not found."
            self.running = False
            return

        # 파일 열기 (바이너리 읽기 모드)
        with open(self.file_path, "rb") as f:
            self.parser.last_log = "Scanner: Started..."
            
            # running 플래그가 True인 동안 계속 읽기
            while self.running:
                packet = f.read(188)        # 188바이트(1패킷) 읽기
                if len(packet) != 188:      # 파일 끝(EOF) 도달 시
                    break
                
                # Core의 카운터 증가 (전체 통계)
                self.parser.packet_count += 1
                
                # Core의 헤더 파서 이용
                pid, pusi, adapt, cnt = self.parser.parse_header(packet)
                
                # ETR-290 분석 (패킷 단위)
                if self.etr290:
                    offset = (self.parser.packet_count - 1) * 188
                    self.etr290.process_packet(packet, offset, pid, pusi, adapt, cnt)
                
                # PID별 패킷 수 카운팅 (딕셔너리 업데이트)
                self.parser.pid_counts[pid] = self.parser.pid_counts.get(pid, 0) + 1
                
                # --- 통계 데이터 초기화 (처음 발견된 PID) ---
                if pid not in self.stats:
                    self.stats[pid] = {
                        'cc_errors': 0, 'last_cc': -1, 'scrambled': 0,
                        'pcr_list': [], 'last_pcr': None, 'pcr_intervals': [],
                        'last_pts': None, 'pts_intervals': [],
                        # Packet Arrival Jitter Stats (Byte-based)
                        'last_pkt_offset': -1, 'pkt_intervals_sum': 0, 'pkt_intervals_count': 0,
                        'pkt_max_intv': 0, 'pkt_min_intv': 99999999,
                        # PES Length Stats (PUSI=1)
                        'pes_len_sum': 0, 'pes_count': 0
                    }
                
                st = self.stats[pid]
                
                # Packet Arrival Interval Calc (Byte based)
                curr_offset = self.parser.packet_count * 188
                if st['last_pkt_offset'] != -1:
                    diff = curr_offset - st['last_pkt_offset']
                    st['pkt_intervals_sum'] += diff
                    st['pkt_intervals_count'] += 1
                    if diff > st['pkt_max_intv']: st['pkt_max_intv'] = diff
                    if diff < st['pkt_min_intv']: st['pkt_min_intv'] = diff
                st['last_pkt_offset'] = curr_offset

                # 1. CC Error Check (Null Packet 0x1FFF 제외)
                if pid != 0x1FFF:
                    # Adapt field control이 00(Reserved)이나 10(Adapt only)인 경우 등 예외 처리 필요할 수 있음
                    # 여기서는 단순하게 연속성만 체크 (Discontinuity indicator 고려 안 함 - 심화 분석 시 필요)
                    if st['last_cc'] != -1:
                        # Adapt Field Only (No Payload)인 경우 CC 증가 안 할 수 있음 (표준 참조)
                        # 하지만 일반적인 경우 (Last + 1) % 16
                        # (Duplicate Packet 등 복잡한 케이스는 제외하고 단순 불연속성만 체크)
                        if adapt & 0x1: # Payload exists
                            expected = (st['last_cc'] + 1) % 16
                            if cnt != expected and cnt != st['last_cc']: # Duplicate도 아님
                                st['cc_errors'] += 1
                    
                    if adapt & 0x1: # Payload가 있을 때만 CC 업데이트
                        st['last_cc'] = cnt
                
                # 2. Scrambling Check
                scram = (struct.unpack('>I', packet[:4])[0] >> 6) & 0x3
                if scram != 0: st['scrambled'] += 1

                # 3. PCR Analysis
                if adapt & 0x2: # Adapt Field Exists
                    # 성능을 위해 필요한 경우에만 상세 파싱
                    # (Core의 parse_adapt_field는 다소 무거울 수 있으니 필요한 부분만 추출하거나 그대로 사용)
                    # 여기서는 Core 함수 재사용
                    ad_info = self.parser.parse_adapt_field(packet)
                    if ad_info['pcr'] is not None:
                        pcr_val = ad_info['pcr']
                        pcr_sec = pcr_val / 27_000_000.0
                        
                        # Jitter 분석용 데이터 수집
                        st['pcr_list'].append((self.parser.packet_count * 188, pcr_sec))
                        
                        # Interval 계산
                        if st['last_pcr'] is not None:
                            diff = pcr_sec - st['last_pcr']
                            if 0 < diff < 5.0: # 5초 이상 갭은 무시 (불연속으로 간주)
                                st['pcr_intervals'].append(diff)
                        st['last_pcr'] = pcr_sec

                # 4. PTS Analysis (PUSI=1)
                if pusi and (adapt & 0x1):
                    off = 4
                    if adapt & 0x2: off = 5 + packet[4]
                    
                    if off < 188 - 6: # Min PES header
                        # PES Length (Average Calc)
                        pes_len = (packet[off+4] << 8) | packet[off+5]
                        if pes_len > 0:
                            st['pes_len_sum'] += pes_len
                            st['pes_count'] += 1

                        payload = packet[off:]
                        pes_info = self.parser.parse_pes_header(payload)
                        if pes_info and pes_info['pts'] is not None:
                            pts_sec = pes_info['pts'] / 90000.0
                            
                            if st['last_pts'] is not None:
                                diff = pts_sec - st['last_pts']
                                if 0 < diff < 5.0:
                                    st['pts_intervals'].append(diff)
                            st['last_pts'] = pts_sec
                
                # --- PSI (Program Specific Information) 파싱 ---
                if pid == 0 and pusi: 
                    self.parser._parse_pat(packet, adapt)
                
                for prog in list(self.parser.programs.values()):
                    # ETR-290: PMT PID 등록
                    if self.etr290: self.etr290.register_pmt_pid(prog['pmt_pid'])
                    
                    if pid == prog['pmt_pid'] and pusi:
                        self.parser._parse_pmt(packet, adapt, prog)

                # --- CPU 점유율 관리 ---
                if self.parser.packet_count % 5000 == 0:
                    time.sleep(0.001)
        
        # 스캔 종료 후 리포트 생성 및 저장
        self.report = self._generate_report()
        self._save_report_to_file()
        
        self.parser.last_log = "Scanner: Completed. Report Saved."
        self.completed = True
        self.running = False

    def _generate_report(self):
        """MTS-430 Style 종합 분석 리포트 생성"""
        total = self.parser.packet_count
        if total == 0: return ["No packets scanned."]
        
        lines = []
        lines.append(f"# MPEG2-TS Analysis Report")
        lines.append(f"- **Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **File**: {self.file_path}")
        lines.append(f"- **Total Packets**: {total:,}")
        lines.append(f"- **File Size**: {self.parser.file_size:,} bytes")
        
        # 전체 재생 시간 추정 (PCR 기반)
        duration = 0.0
        first_pcr = None
        last_pcr = None
        
        # 모든 PCR 데이터 중 가장 빠른것과 늦은것 찾기
        for pid, st in self.stats.items():
            if st['pcr_list']:
                curr_first = st['pcr_list'][0][1]
                curr_last = st['pcr_list'][-1][1]
                if first_pcr is None or curr_first < first_pcr: first_pcr = curr_first
                if last_pcr is None or curr_last > last_pcr: last_pcr = curr_last
        
        if first_pcr is not None and last_pcr is not None:
            duration = last_pcr - first_pcr
            lines.append(f"- **Estimated Duration**: {duration:.2f} sec")
            
            # Overall Bitrate
            if duration > 0:
                bps = (total * 188 * 8) / duration
                lines.append(f"- **Overall Bitrate**: {bps/1_000_000:.2f} Mbps")

                # Video/Audio Packets Summary
                v_pkts = 0
                a_pkts = 0
                for pid, count in self.parser.pid_counts.items():
                    desc = self.parser.pid_map.get(pid, {}).get('desc', '')
                    if 'Video' in desc: v_pkts += count
                    if 'Audio' in desc: a_pkts += count
                
                v_pps = v_pkts / duration
                a_pps = a_pkts / duration
                
                if v_pkts > 0: lines.append(f"- **Video Packets**: {v_pkts:,} ({v_pps:.1f} pps)")
                if a_pkts > 0: lines.append(f"- **Audio Packets**: {a_pkts:,} ({a_pps:.1f} pps)")

        lines.append("")
        
        # --- 1. Program Structure ---
        lines.append("## 1. Program Structure (PSI)")
        for prog_num, prog in self.parser.programs.items():
            lines.append(f"* **Program {prog_num}** (PMT PID: 0x{prog['pmt_pid']:04X})")
            pcr_pid = prog.get('pcr_pid_val', 0)
            lines.append(f"  - PCR PID: 0x{pcr_pid:04X}")
            for pid, info in prog['pids'].items():
                role = "PCR/Video" if pid == pcr_pid and "Video" in info['desc'] else info['desc']
                lines.append(f"  - PID 0x{pid:04X}: {role}")
        lines.append("")

        # --- 2. PID Statistics (Table) ---
        lines.append("## 2. PID Statistics & Errors")
        lines.append("| PID | Type | Count | Usage | Avg Intv (ms) | Avg PES Len | CC Err | Scrambled |")
        lines.append("|:---:|:---|---:|---:|---:|---:|:---:|:---:|")
        
        sorted_pids = sorted(self.parser.pid_counts.items(), key=lambda x: x[1], reverse=True)
        byte_rate = (self.parser.file_size / duration) if duration > 0 else 0

        for pid, count in sorted_pids:
            st = self.stats.get(pid, {})
            percent = (count / total) * 100
            
            # Packet Arrival Interval (Byte -> Time)
            avg_intv_ms_str = "-"
            if byte_rate > 0 and st.get('pkt_intervals_count', 0) > 0:
                avg_bytes = st['pkt_intervals_sum'] / st['pkt_intervals_count']
                avg_ms = (avg_bytes / byte_rate) * 1000
                avg_intv_ms_str = f"{avg_ms:.2f}"
            
            # Average PES Length
            pes_len_str = "-"
            if st.get('pes_count', 0) > 0:
                avg_len = st['pes_len_sum'] / st['pes_count']
                pes_len_str = f"{avg_len:.0f}"

            # Description
            desc = "Unknown"
            if pid == 0: desc = "PAT"
            elif pid == 0x1FFF: desc = "Null Packet"
            elif pid in self.parser.pid_map: desc = self.parser.pid_map[pid]['desc']
            for p in self.parser.programs.values():
                if p['pmt_pid'] == pid: desc = "PMT"
            
            cc_err = st.get('cc_errors', 0)
            scram = st.get('scrambled', 0)
            scram_str = "Yes" if scram > 0 else "No"
            
            # Highlight Errors
            cc_str = f"**{cc_err}**" if cc_err > 0 else "0"
            
            lines.append(f"| 0x{pid:04X} | {desc} | {count:,} | {percent:.1f}% | {avg_intv_ms_str} | {pes_len_str} | {cc_str} | {scram_str} |")
        lines.append("")

        # --- 3. PCR Analysis (Jitter & Interval) ---
        lines.append("## 3. PCR Analysis (Timing)")
        has_pcr = False
        
        for pid, st in self.stats.items():
            if not st['pcr_list']: continue
            has_pcr = True
            
            count = len(st['pcr_list'])
            intervals = st['pcr_intervals']
            
            lines.append(f"### PID 0x{pid:04X}")
            lines.append(f"- **Packet Count**: {count}")
            
            # Interval Stats
            if intervals:
                min_iv = min(intervals) * 1000
                max_iv = max(intervals) * 1000
                avg_iv = (sum(intervals) / len(intervals)) * 1000
                lines.append(f"- **Interval**: Min {min_iv:.2f}ms / Max {max_iv:.2f}ms / Avg {avg_iv:.2f}ms")
                if max_iv > 40: lines.append(f"  - ⚠️ Warning: Max Interval > 40ms (DVB recommended)")
            
            # Jitter Analysis (using TSJitterAnalyzer)
            if TSJitterAnalyzer and len(st['pcr_list']) > 10:
                analyzer = TSJitterAnalyzer()
                analyzer.raw_pcr_data = st['pcr_list'] # Inject Data
                analyzer.analyze_full() # Run Math
                
                j_min = analyzer.min_jitter
                j_max = analyzer.max_jitter
                bitrate = analyzer.bitrate
                align_max = getattr(analyzer, 'max_align_jitter', 0)
                
                lines.append(f"- **Calculated Bitrate**: {bitrate/1_000_000:.4f} Mbps")
                lines.append(f"- **Timing Jitter (PCR Accuracy)**:")
                lines.append(f"  - Min: {j_min:.0f} ns")
                lines.append(f"  - Max: {j_max:.0f} ns")
                if align_max > 0:
                    lines.append(f"- **Alignment Jitter**: Max {align_max:.0f} ns")
                
                if abs(j_max) > 500 or abs(j_min) > 500:
                    lines.append(f"  - ❌ **Fail**: Exceeds ISO limit (±500ns)")
                else:
                    lines.append(f"  - ✅ **Pass**: Within ISO limit")
            else:
                lines.append("- **Jitter**: Not enough samples or Analyzer module missing.")
            
            lines.append("")
            
        if not has_pcr: lines.append("No PCR packets found.")

        # --- 4. PTS Analysis (Frame Interval) ---
        lines.append("## 4. PTS Analysis (Presentation Timing)")
        has_pts = False
        for pid, st in self.stats.items():
            if not st['pts_intervals']: continue
            has_pts = True
            
            count = len(st['pts_intervals']) + 1
            intervals = st['pts_intervals']
            
            avg_sec = sum(intervals) / len(intervals)
            fps = 1.0 / avg_sec if avg_sec > 0 else 0
            
            desc = self.parser.pid_map.get(pid, {}).get('desc', 'Unknown')
            lines.append(f"* **PID 0x{pid:04X} ({desc})**")
            lines.append(f"  - Count: {count}")
            lines.append(f"  - Avg Interval: {avg_sec*1000:.2f} ms")
            
            # Video FPS estimation
            if "Video" in desc:
                lines.append(f"  - **Estimated FPS**: {fps:.2f}")
            
        if not has_pts: lines.append("No PTS found.")
        lines.append("")

        # --- 5. ETR-290 Analysis ---
        if self.etr290:
            # Finalize analysis (calculate intervals using duration)
            if duration > 0:
                self.etr290.finalize_analysis(duration, self.parser.file_size)
            
            # Merge Jitter Result (PCR Accuracy Error)
            # 가장 나쁜 Jitter 값을 찾아서 ETR290 결과에 반영
            max_jitter_ns = 0
            for pid, st in self.stats.items():
                if TSJitterAnalyzer and len(st['pcr_list']) > 10:
                    analyzer = TSJitterAnalyzer()
                    analyzer.raw_pcr_data = st['pcr_list']
                    analyzer.analyze_full()
                    if abs(analyzer.max_jitter) > max_jitter_ns: max_jitter_ns = abs(analyzer.max_jitter)
                    if abs(analyzer.min_jitter) > max_jitter_ns: max_jitter_ns = abs(analyzer.min_jitter)
            
            if max_jitter_ns > 500:
                self.etr290.errors['PCR_accuracy_error'] = 1 # Flag set
            
            etr_lines = self.etr290.get_report_markdown()
            lines.extend(etr_lines)
            
        return lines

    def _save_report_to_file(self):
        """리포트를 파일로 저장"""
        try:
            # 프로젝트 루트의 output 폴더 찾기 (현재 스크립트 위치 기준 상위 폴더 + output)
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(root_dir, "output")
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"BScan_Report_{timestamp}.md"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                for line in self.report:
                    f.write(line + "\n")
            
            # GUI 로그에도 표시하기 위해 parser log 업데이트 (선택 사항)
            # self.parser.last_log = f"Report saved: {filename}"
            
        except Exception as e:
            print(f"Failed to save report: {e}")
