"""
[파일 개요]
이 스크립트는 OpenCV(cv2)를 사용하여 HEVC(H.265)로 인코딩된 TS 파일을 재생합니다.
FFmpeg 백엔드를 사용하여 디코딩하며, 4K UHD 영상을 HD(1280x720) 크기로 리사이징하여 화면에 표시합니다.

[주요 기능]
1. TS 파일 로드 및 스트림 오픈 (cv2.CAP_FFMPEG 사용)
2. 초기 헤더(PPS/SPS) 탐색 실패 시 재시도 로직 (Search PPS...)
3. 화면 표시 윈도우 크기 조절 (1280x720)
4. 'q' 키 입력 시 종료

[사용법]
python scripts/play_ts_opencv.py
"""
import cv2
import os
import sys

# 파일 경로
ts_file_path = r"D:\git\mpeg2TS\TS\mama_uhd2.ts"

def main():
    if not os.path.exists(ts_file_path):
        print(f"Error: 파일을 찾을 수 없습니다 -> {ts_file_path}")
        return

    # FFMPEG 백엔드를 명시적으로 지정
    cap = cv2.VideoCapture(ts_file_path, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        print("Error: 비디오 스트림을 열 수 없습니다.")
        return

    print(f"재생 시작: {ts_file_path}")
    print("종료하려면 'q' 키를 누르세요.")
    
    # 윈도우 이름 설정
    window_name = 'MPEG2-TS Player'
    
    # 윈도우 생성 및 크기 조절 가능하도록 설정
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    # 윈도우 크기 강제 설정 (1280x720)
    # 4K 영상(3840x2160)은 너무 커서 모니터에 다 안 들어옴
    cv2.resizeWindow(window_name, 1280, 720)

    frame_count = 0
    fail_count = 0

    while True:
        ret, frame = cap.read()
        frame_count += 1

        if not ret:
            fail_count += 1
            # 로그가 너무 빠르게 흐르지 않게 제어
            if frame_count == 1 or fail_count % 100 == 0:
                 sys.stdout.write(f"\rSearch PPS... (Frame {frame_count}, Fail {fail_count})")
                 sys.stdout.flush()
            
            if fail_count > 2000:
                print("\n재생 실패: 초기 헤더를 찾지 못했거나 파일 끝에 도달했습니다.")
                break
            continue
        
        # 성공 시 카운트 초기화 및 성공 메시지 (한 번만 출력하거나 필요 시)
        if fail_count > 0:
            print(f"\n영상 신호 감지! (after {fail_count} skip)")
            fail_count = 0
        
        # 화면 표시
        cv2.imshow(window_name, frame)

        # q를 누르면 종료 (1ms 대기)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
