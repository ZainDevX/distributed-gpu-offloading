"""
Server Launch Script for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing
Usage:
    python start_server.py         # Launches Modern Host Server GUI Dashboard
    python start_server.py --cli   # Runs headless background daemon
"""

import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    if "--cli" in sys.argv:
        from server.daemon import main as daemon_main
        daemon_main()
    else:
        from server.server_gui import main as gui_main
        gui_main()
