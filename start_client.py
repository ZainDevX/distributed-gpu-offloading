"""
Client Desktop GUI Launch Script for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing
Usage:
    python start_client.py
"""

import sys
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from client.gui_app import main

if __name__ == "__main__":
    main()
