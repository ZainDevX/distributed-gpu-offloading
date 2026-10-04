"""
Server Launch Script for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing
Usage:
    python start_server.py [--host 0.0.0.0] [--port 5050] [--max-workers 1]
"""

import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.daemon import main

if __name__ == "__main__":
    main()
