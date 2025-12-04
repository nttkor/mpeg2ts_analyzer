"""
MPEG2-TS ETR-290 Analysis Module
ETR 290 규격(Priority 1, 2, 3)에 기반한 에러 체크 및 통계 분석을 수행합니다.
"""
import struct

class TSETR290Analyzer:
    def __init__(self):
        # --- Error Counters (ETR 290 Definitions) ---
        self.errors = {
            # Priority 1
            'TS_sync_loss': 0,          # 1.1 (Not fully implementable in file scan, checked via sync byte)
            'Sync_byte_error': 0,       # 1.2
            'PAT_error': 0,             # 1.3 (PID 0 missing, Interval > 0.5s, TableID!=0, Scram!=0)
            'Continuity_count_error': 0,# 1.4 (Packet loss, Out of order)
            'PMT_error': 0,             # 1.5 (PMT PID missing, Interval > 0.5s, TableID!=2, Scram!=0)
            'PID_error': 0,             # 1.6 (Referred PID not found for > x sec) - optional
            
            # Priority 2
            'Transport_error': 0,       # 2.1 (TEI == 1)
            'CRC_error': 0,             # 2.2 (PSI Tables CRC fail) - optional
            'PCR_repetition_error': 0,  # 2.3a (Interval > 40ms)
            'PCR_discontinuity_error': 0, # 2.3b (Gap > 100ms)
            'PCR_accuracy_error': 0,    # 2.4 (Jitter > 500ns) - Calculated externally
            'PTS_error': 0,             # 2.5 (Interval > 700ms)
            'CAT_error': 0              # 2.6 (Scrambled but no CAT)
        }
        
        # --- Internal State Tracking ---
        # PID별 상태: { last_cc: int, duplicate_count: int }
        self.pid_state = {}
        
        # 이벤트 오프셋 기록 (Interval 분석용)
        # 리스트에 (byte_offset, extra_info) 저장
        self.events = {
            'pat': [],          # PAT offsets
            'pmt': {},          # { pmt_pid: [offset, ...] }
            'pcr': {},          # { pcr_pid: [offset, ...] }
            'pts': {},          # { pid: [offset, ...] }
        }
        
        self.valid_pmt_pids = set()
        
        # 측정된 통계값 저장 (Max Interval 등)
        self.error_stats = {}

    def report_section_error(self, pid, error_type):
        """외부 모듈(Core)에서 감지된 섹션 에러(CRC, Table ID 등) 보고"""
        if error_type == 'CRC_error':
            self.errors['CRC_error'] += 1
        elif error_type == 'Table_ID_error':
            # 1.3b PAT, 1.5b PMT Table ID Error
            if pid == 0: self.errors['PAT_error'] += 1
            elif pid in self.valid_pmt_pids: self.errors['PMT_error'] += 1

    def process_packet(self, packet, offset, pid, pusi, adapt, cnt):
        """
        개별 패킷을 검사하여 즉시 확인 가능한 에러(1.2, 1.4, 2.1)를 체크하고 상태를 기록함.
        """
        # 1.2 Sync_byte_error / 1.1 Sync loss (Check 0x47)
        if packet[0] != 0x47:
            self.errors['Sync_byte_error'] += 1
            return # Cannot parse further
            
        # Parse Header Flags
        header_val = struct.unpack('>I', packet[:4])[0]
        tei = (header_val >> 23) & 0x1
        scram = (header_val >> 6) & 0x3
        
        # 2.1 Transport_error
        if tei == 1:
            self.errors['Transport_error'] += 1
            
        # 1.4 Continuity_count_error (Ignore Null Packet 0x1FFF)
        if pid != 0x1FFF:
            self._check_cc_error(pid, cnt, adapt)
            
        # 1.3 PAT Error Logic (Collection)
        if pid == 0:
            # Scrambling check
            if scram != 0: self.errors['PAT_error'] += 1
            # Table ID check (PUSI=1일 때만 가능, 여기서는 단순 Offset 수집)
            if pusi: self.events['pat'].append(offset)
            
        # 1.5 PMT Error Logic (Collection)
        if pid in self.valid_pmt_pids:
            if scram != 0: self.errors['PMT_error'] += 1
            if pusi:
                if pid not in self.events['pmt']: self.events['pmt'][pid] = []
                self.events['pmt'][pid].append(offset)
                
        # 2.3 PCR Collection (Adaptation Field 존재 시)
        if (adapt & 0x2) and len(packet) >= 12:
            af_len = packet[4]
            if af_len > 0:
                flags = packet[5]
                pcr_flag = (flags >> 4) & 0x1
                if pcr_flag:
                    if pid not in self.events['pcr']: self.events['pcr'][pid] = []
                    self.events['pcr'][pid].append(offset)

        # 2.5 PTS Collection (PUSI=1)
        if pusi:
            # PES Header 간단 체크 (Start Code)
            off = 4
            if adapt & 0x2: off = 5 + packet[4]
            
            if off < 188 - 9: # Min header size
                prefix = (packet[off] << 16) | (packet[off+1] << 8) | packet[off+2]
                if prefix == 0x000001:
                    # Check PTS flag
                    flags_2 = packet[off+7]
                    pts_flag = (flags_2 >> 7) & 0x1
                    if pts_flag:
                        if pid not in self.events['pts']: self.events['pts'][pid] = []
                        self.events['pts'][pid].append(offset)

    def _check_cc_error(self, pid, curr_cc, adapt):
        """1.4 Continuity Count Check"""
        # Initialize state
        if pid not in self.pid_state:
            self.pid_state[pid] = {'last_cc': -1, 'dup_cnt': 0}
            # 첫 패킷은 에러 아님, 상태만 저장
            if adapt & 0x1: # Payload exists
                self.pid_state[pid]['last_cc'] = curr_cc
            return

        state = self.pid_state[pid]
        last_cc = state['last_cc']
        
        # Adaptation Field Control
        # 00: Reserved, 01: Payload, 10: Adapt, 11: Both
        has_payload = (adapt & 0x1)
        
        if has_payload:
            if last_cc == -1:
                state['last_cc'] = curr_cc
                return
                
            if curr_cc == last_cc:
                # Duplicate Packet (Allowed up to 2 times total i.e. 1 repetition)
                # ETR 290: "Packet sent twice" is OK, "more than twice" is error?
                # Usually CC should increment. Duplicate packets are for padding sometimes.
                # Here we implement basic discontinuity check.
                state['dup_cnt'] += 1
                pass 
            else:
                expected = (last_cc + 1) & 0xF
                if curr_cc != expected:
                    self.errors['Continuity_count_error'] += 1
                
                state['last_cc'] = curr_cc
                state['dup_cnt'] = 0
        else:
            # No payload (Adaptation only) -> CC should NOT increment
            # But if it increments, it's discontinuity?
            # Standard says: CC increments only if payload exists.
            # So for adapt-only, CC should be same as previous packet with payload.
            # But strictly ETR290 Continuity_count_error usually refers to Discontinuity indicator or Missing packets.
            # We stick to payload-based CC check for now.
            pass

    def register_pmt_pid(self, pid):
        """Scanner에서 PMT PID를 발견하면 등록 (1.5 에러 체크용)"""
        self.valid_pmt_pids.add(pid)

    def finalize_analysis(self, duration_sec, file_size):
        """
        전체 스캔 종료 후, 수집된 Offset 정보를 시간(Time)으로 변환하여 Interval 에러를 계산함.
        :param duration_sec: 전체 재생 시간 (초)
        :param file_size: 전체 파일 크기 (바이트)
        """
        if duration_sec <= 0 or file_size == 0:
            return

        # ByteRate (Bytes per second)
        byte_rate = file_size / duration_sec
        
        def check_interval(offsets, limit_sec, error_key, error_key_discont=None):
            if not offsets or len(offsets) < 2:
                # 데이터가 1개 이하면 Interval 계산 불가
                self.error_stats[error_key] = {'max_ms': 0.0, 'min_ms': 0.0, 'avg_ms': 0.0}
                return

            max_diff = 0.0
            min_diff = 999999.0
            sum_diff = 0.0
            count = 0
            
            last_offset = offsets[0]
            
            for i in range(1, len(offsets)):
                curr = offsets[i]
                diff_bytes = curr - last_offset
                diff_sec = diff_bytes / byte_rate
                
                # Stats update
                if diff_sec > max_diff: max_diff = diff_sec
                if diff_sec < min_diff: min_diff = diff_sec
                sum_diff += diff_sec
                count += 1

                # Repetition Error (너무 늦게 옴)
                if diff_sec > limit_sec:
                    self.errors[error_key] += 1
                    # 2.3 PCR의 경우 Discontinuity(100ms)와 Repetition(40ms)가 나뉨
                    if error_key_discont and diff_sec > 0.1: # 100ms
                        self.errors[error_key_discont] += 1
                
                last_offset = curr
            
            # Save Stats
            if count > 0:
                self.error_stats[error_key] = {
                    'max_ms': max_diff * 1000,
                    'min_ms': min_diff * 1000,
                    'avg_ms': (sum_diff / count) * 1000
                }
                
                # PCR Discontinuity 별도 저장
                if error_key_discont:
                     self.error_stats[error_key_discont] = self.error_stats[error_key]

        # 1.3 PAT Interval > 0.5s
        check_interval(self.events['pat'], 0.5, 'PAT_error')
        
        # 1.5 PMT Interval > 0.5s
        # 여러 PMT 중 가장 나쁜(Max) 값을 기록
        pmt_max_ms = 0
        pmt_err_count = 0
        for pid, offsets in self.events['pmt'].items():
            check_interval(offsets, 0.5, 'PMT_error')
            st = self.error_stats.get('PMT_error')
            if st and st['max_ms'] > pmt_max_ms: pmt_max_ms = st['max_ms']
        
        # 대표값 업데이트 (리포트용)
        if self.events['pmt']:
             self.error_stats['PMT_error'] = {'max_ms': pmt_max_ms}
            
        # 2.3 PCR Interval > 40ms (Repetition), > 100ms (Discontinuity)
        pcr_max_ms = 0
        for pid, offsets in self.events['pcr'].items():
            check_interval(offsets, 0.04, 'PCR_repetition_error', 'PCR_discontinuity_error')
            st = self.error_stats.get('PCR_repetition_error')
            if st and st['max_ms'] > pcr_max_ms: pcr_max_ms = st['max_ms']
        if self.events['pcr']:
             self.error_stats['PCR_repetition_error'] = {'max_ms': pcr_max_ms}
            
        # 2.5 PTS Interval > 700ms
        pts_max_ms = 0
        for pid, offsets in self.events['pts'].items():
            check_interval(offsets, 0.7, 'PTS_error')
            st = self.error_stats.get('PTS_error')
            if st and st['max_ms'] > pts_max_ms: pts_max_ms = st['max_ms']
        if self.events['pts']:
             self.error_stats['PTS_error'] = {'max_ms': pts_max_ms}

    def get_report_markdown(self):
        """Markdown 포맷 리포트 반환"""
        lines = []
        lines.append("## ETR-290 Analysis Report")
        
        def get_stat_str(key):
            if key in self.error_stats:
                st = self.error_stats[key]
                if 'max_ms' in st:
                    return f"(Max: {st['max_ms']:.2f}ms)"
            return ""

        # Priority 1
        lines.append("### Priority 1 (Critical)")
        p1_keys = ['TS_sync_loss', 'Sync_byte_error', 'PAT_error', 'Continuity_count_error', 'PMT_error', 'PID_error']
        
        has_p1_err = False
        for k in p1_keys:
            cnt = self.errors.get(k, 0)
            status = "✅ OK" if cnt == 0 else f"❌ **{cnt} Errors**"
            stat_info = get_stat_str(k)
            if cnt > 0: has_p1_err = True
            lines.append(f"- **{k}**: {status} {stat_info}")
            
        if not has_p1_err: lines.append("> **Result**: Stream is Decodable (No Priority 1 Errors)")
        else: lines.append("> **Result**: ⚠️ Stream may have decoding issues.")
        
        lines.append("")
        
        # Priority 2
        lines.append("### Priority 2 (Recommended)")
        p2_keys = ['Transport_error', 'CRC_error', 'PCR_repetition_error', 'PCR_discontinuity_error', 'PCR_accuracy_error', 'PTS_error', 'CAT_error']
        
        for k in p2_keys:
            cnt = self.errors.get(k, 0)
            # PCR Accuracy는 외부(Jitter Analyzer)에서 주입해주지 않으면 0일 수 있음
            status = "✅ OK" if cnt == 0 else f"⚠️ **{cnt} Errors**"
            stat_info = get_stat_str(k)
            lines.append(f"- **{k}**: {status} {stat_info}")
            
        
        # [추가] 상세 측정 통계 섹션
        lines.append("")
        lines.append("### Detailed Measurement Statistics")
        lines.append("| Type | Min (ms) | Max (ms) | Avg (ms) | Note |")
        lines.append("|:---|---:|---:|---:|:---|")
        
        # 표시할 항목들 정의
        stats_map = [
            ('PCR_repetition_error', 'PCR Interval'),
            ('PCR_discontinuity_error', 'PCR Discont Check'),
            ('PTS_error', 'PTS Interval'),
            ('PAT_error', 'PAT Interval'),
            ('PMT_error', 'PMT Interval'),
        ]
        
        for key, label in stats_map:
            st = self.error_stats.get(key)
            if st and 'min_ms' in st:
                lines.append(f"| {label} | {st['min_ms']:.2f} | {st['max_ms']:.2f} | {st['avg_ms']:.2f} | - |")
            else:
                lines.append(f"| {label} | - | - | - | No Data |")

        return lines
