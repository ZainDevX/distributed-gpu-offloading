"""
Launch Script for Microsoft Windows 11 Clipchamp Video Editor Studio.
Features Multi-Track Timeline, Aesthetic Filters, Cuts, and Distributed GPU Chunked Export.
Course: CSC-334 Parallel and Distributed Computing

Usage:
    python start_editor.py [--host 127.0.0.1] [--port 5050]
"""

import argparse
import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clipchamp_studio.ui.editor_window import ClipchampEditorWindow
from common.config import DEFAULT_CLIENT_TARGET, DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(description="Microsoft Windows 11 Clipchamp Studio Video Editor")
    parser.add_argument("--host", default=DEFAULT_CLIENT_TARGET, help="Host GPU worker address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Host GPU worker port")
    args = parser.parse_args()

    app = ClipchampEditorWindow(target_host=args.host, target_port=args.port)
    app.mainloop()


if __name__ == "__main__":
    main()

