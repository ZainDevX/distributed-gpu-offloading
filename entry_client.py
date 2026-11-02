"""
Entrypoint for compiling Standalone Client Executable.
"""
import os
import sys
from pathlib import Path

# Set base dir
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure imageio_ffmpeg uses bundled ffmpeg if frozen
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).parent
    bundled_ffmpeg = exe_dir / "ffmpeg.exe"
    if bundled_ffmpeg.exists():
        os.environ["IMAGEIO_FFMPEG_EXE"] = str(bundled_ffmpeg.resolve())

from clipchamp_studio.ui.editor_window import main

if __name__ == "__main__":
    main()

