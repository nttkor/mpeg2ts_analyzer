# MPEG2-TS Analyzer

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![OpenCV](https://img.shields.io/badge/opencv-4.x-green.svg)

**MPEG2-TS Analyzer** is a professional-grade Transport Stream analysis tool written in Python.
It provides a GUI similar to hardware analyzers (e.g., Tektronix MTS430), allowing deep inspection of TS packets, PSI/SI tables, and Elementary Streams (PES).

## Key Features

- **Visual Analysis**:
  - **Tree View**: Hierarchical view of PAT, PMT, and Elementary Streams.
  - **Hex View**: Real-time binary dump of 188-byte packets.
  - **Detail View**: Comprehensive breakdown of TS Headers (PID, CC, PUSI, Scrambling, Adaptation).

- **Deep PES Inspection**:
  - **Audio/Video Parsing**: PTS/DTS extraction, Stream ID identification.
  - **Structure Analysis**: Detects Single/Multi-packet PES.
  - **Back-tracking**: Automatically traces back to the start of a PES packet from any continuation point.
  - **Audio Sync Check**: Scans for MP2/ADTS sync words (`0xFFF`) in payloads.

- **Smart Navigation**:
  - **PID Filtering**: Seek/Jump specifically within a selected PID stream.
  - **BScan (Background Scan)**: Full-file scanning in the background to generate usage statistics reports.

## Requirements

- Python 3.8+
- OpenCV (`opencv-python`)
- NumPy

```bash
pip install -r requirements.txt
```

## Usage

```bash
python scripts/ts_analyzer_gui.py [optional_file.ts]
```

### Controls
- **File**: Open TS files, View Recent Files.
- **BScan**: Toggle background scanning & View Report.
- **Play/Stop**: Control packet playback.
- **Tree View**: Click items to filter by Program or PID.
- **PES View**: Click "Parent PES Start" to jump to the beginning of a frame.

## Documentation
- [Project Overview](doc/mpeg2ts_parser.md)
- [GUI Manual](doc/ts_analyzer_gui.md)
- [Class Architecture](doc/class_plan.md)

## Architecture
The project is modularized for maintainability:
- `ts_analyzer_gui.py`: Main Controller & Entry point.
- `ts_ui_manager.py`: UI rendering & Input handling.
- `ts_parser_core.py`: Core parsing engine.
- `ts_models.py`: Data models (Packet, PSI, PES).
- `ts_scanner.py`: Background worker.



