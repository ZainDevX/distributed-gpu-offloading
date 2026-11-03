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

from common.config import DEFAULT_CLIENT_TARGET, DEFAULT_PORT

if __name__ == "__main__":
    if "--transcoder" in sys.argv:
        from client.gui_app import main as transcoder_main
        target_ip = None
        if "--ip" in sys.argv:
            try:
                target_ip = sys.argv[sys.argv.index("--ip") + 1]
            except IndexError:
                pass
        transcoder_main(target_ip=target_ip)
    else:
        target_host = DEFAULT_CLIENT_TARGET
        target_port = DEFAULT_PORT
        if "--host" in sys.argv:
            try:
                target_host = sys.argv[sys.argv.index("--host") + 1]
            except IndexError:
                pass
        if "--port" in sys.argv:
            try:
                target_port = int(sys.argv[sys.argv.index("--port") + 1])
            except (IndexError, ValueError):
                pass
        from clipchamp_studio.ui.editor_window import ClipchampEditorWindow
        app = ClipchampEditorWindow(target_host=target_host, target_port=target_port)
        app.mainloop()

