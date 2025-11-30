"""
[파일 개요]
MPEG2-TS 백그라운드 스캐너 (TSScanner)

[목적 및 필요성]
TSParser(Core)는 '패킷 단위 읽기'와 '헤더 파싱' 같은 기본 기능에 집중하고,
'파일 전체를 순회하며 통계를 내는 작업'은 별도 클래스로 분리하여 복잡도를 낮춥니다.
이 스캐너는 별도 스레드에서 동작하며, GUI가 멈추지 않게 하면서 파일의 전체 구조(PAT/PMT)와
PID별 패킷 개수, 오디오 상태 등을 지속적으로 업데이트합니다.
"""
import threading
import time
import os
import datetime

class TSScanner:
    """
    백그라운드에서 TS 파일을 처음부터 끝까지 읽으며 분석하는 클래스.
    TSParser 인스턴스를 참조하여 파싱 로직을 수행하고 결과를 공유합니다.
    """
    def __init__(self, parser_instance):
        self.parser = parser_instance       # 파싱 도구 및 데이터 저장소 공유 (TSParser 객체)
        self.running = False                # 스캔 루프 실행 여부 플래그
        self._thread = None                 # 백그라운드 작업 스레드
        self.file_path = parser_instance.file_path  # 분석할 파일 경로
        self.report = []                    # 분석 결과 리포트

    def start(self):
        """백그라운드 스캔 스레드 시작"""
        if self.running: return             # 이미 실행 중이면 무시
        
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
                pid, pusi, adapt, _ = self.parser.parse_header(packet)
                
                # PID별 패킷 수 카운팅 (딕셔너리 업데이트)
                self.parser.pid_counts[pid] = self.parser.pid_counts.get(pid, 0) + 1
                
                # --- PSI (Program Specific Information) 파싱 ---
                if pid == 0 and pusi: 
                    self.parser._parse_pat(packet, adapt)
                
                for prog in list(self.parser.programs.values()):
                    if pid == prog['pmt_pid'] and pusi:
                        self.parser._parse_pmt(packet, adapt, prog)

                # --- CPU 점유율 관리 ---
                if self.parser.packet_count % 5000 == 0:
                    time.sleep(0.001)
        
        # 스캔 종료 후 리포트 생성 및 저장
        self.report = self._generate_report()
        self._save_report_to_file()
        
        self.parser.last_log = "Scanner: Completed. Report Saved."
        self.running = False

    def _generate_report(self):
        """분석 결과 요약 리포트 생성"""
        total = self.parser.packet_count
        if total == 0: return ["No packets scanned."]
        
        lines = []
        lines.append(f"# MPEG2-TS Scan Report")
        lines.append(f"- Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- File: {self.file_path}")
        lines.append(f"- Total Packets: {total}")
        lines.append(f"- File Size: {self.parser.file_size} bytes")
        lines.append("")
        
        lines.append("## PID Usage Statistics")
        lines.append("| PID | Description | Count | Percentage |")
        lines.append("|---|---|---|---|")
        
        sorted_pids = sorted(self.parser.pid_counts.items(), key=lambda x: x[1], reverse=True)
        for pid, count in sorted_pids:
            percent = (count / total) * 100
            desc = "Unknown"
            if pid == 0: desc = "PAT (Program Association Table)"
            elif pid in self.parser.pid_map: desc = self.parser.pid_map[pid]['desc']
            # PMT PID 확인
            for p in self.parser.programs.values():
                if p['pmt_pid'] == pid: desc = "PMT (Program Map Table)"
            
            lines.append(f"| 0x{pid:04X} | {desc} | {count} | {percent:.2f}% |")
            
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
