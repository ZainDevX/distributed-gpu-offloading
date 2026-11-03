"""
Automated Build & Release Packaging Script.
Compiles standalone .exe executables for Client and Host without raw source code,
bundles runtime dependencies and ffmpeg, and creates clean distribution folders.
Course: CSC-334 Parallel and Distributed Computing
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def build():
    print("=" * 70)
    print("   DISTRIBUTED GPU OFFLOADING - STANDALONE EXECUTABLE BUILDER")
    print("=" * 70)

    # 1. Install PyInstaller if missing
    try:
        import PyInstaller
    except ImportError:
        print("[*] Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # 2. Get FFmpeg binary path
    import imageio_ffmpeg
    ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    print(f"[*] Discovered FFmpeg Binary: {ffmpeg_exe}")

    # 3. Build Host Executable
    print("\n[*] Compiling Host_GPU_Server.exe...")
    cmd_host = [
        "pyinstaller",
        "--name", "Host_GPU_Server",
        "--onedir",
        "--windowed",
        "--collect-all", "customtkinter",
        "--collect-all", "PIL",
        "--collect-all", "imageio_ffmpeg",
        "--noconfirm",
        str(BASE_DIR / "entry_host.py"),
    ]
    subprocess.run(cmd_host, cwd=str(BASE_DIR), check=True)

    # 4. Build Client Executable
    print("\n[*] Compiling Clipchamp_GPU_Client.exe...")
    cmd_client = [
        "pyinstaller",
        "--name", "Clipchamp_GPU_Client",
        "--onedir",
        "--windowed",
        "--collect-all", "customtkinter",
        "--collect-all", "PIL",
        "--collect-all", "imageio_ffmpeg",
        "--noconfirm",
        str(BASE_DIR / "entry_client.py"),
    ]
    subprocess.run(cmd_client, cwd=str(BASE_DIR), check=True)

    # 5. Populate Host_Package
    print("\n[*] Assembling Host_Package distribution...")
    host_pkg = BASE_DIR / "Host_Package"
    if host_pkg.exists():
        shutil.rmtree(host_pkg)
    shutil.copytree(BASE_DIR / "dist" / "Host_GPU_Server", host_pkg)

    # Copy ffmpeg
    shutil.copy2(ffmpeg_exe, host_pkg / "ffmpeg.exe")
    (host_pkg / "server_workspace" / "asset_cache").mkdir(parents=True, exist_ok=True)
    
    # Create Host launcher and instructions
    (host_pkg / "START_HOST.bat").write_text(
        "@echo off\r\ntitle Host GPU Server\r\ncd /d \"%~dp0\"\r\nstart Host_GPU_Server.exe\r\n",
        encoding="utf-8"
    )
    (host_pkg / "QUICKSTART_GUIDE.txt").write_text(
        "=== HOST GPU SERVER NODE (CSC-334) ===\n\n"
        "HOW TO RUN ON A FRESH PC:\n"
        "1. Double-click START_HOST.bat (or run Host_GPU_Server.exe).\n"
        "2. The server dashboard will open and auto-detect your GPU (NVIDIA GTX/RTX or Intel/AMD).\n"
        "3. Click 'Copy IP' in the top-right corner.\n"
        "4. Give that IP to the client so they can connect and offload video exports.\n\n"
        "No Python, no Git, and no external FFmpeg installation is required.\n",
        encoding="utf-8"
    )

    # 6. Populate Client_Package
    print("[*] Assembling Client_Package distribution...")
    client_pkg = BASE_DIR / "Client_Package"
    if client_pkg.exists():
        shutil.rmtree(client_pkg)
    shutil.copytree(BASE_DIR / "dist" / "Clipchamp_GPU_Client", client_pkg)

    # Copy ffmpeg and sample media
    shutil.copy2(ffmpeg_exe, client_pkg / "ffmpeg.exe")
    sample_dir = client_pkg / "sample_media"
    sample_dir.mkdir(parents=True, exist_ok=True)
    if (BASE_DIR / "test_media" / "test_clip_480p.mp4").exists():
        shutil.copy2(BASE_DIR / "test_media" / "test_clip_480p.mp4", sample_dir / "sample_clip.mp4")

    # Create Client launchers and instructions
    (client_pkg / "START_CLIENT.bat").write_text(
        "@echo off\r\ntitle Clipchamp Studio Video Editor\r\ncd /d \"%~dp0\"\r\nstart Clipchamp_GPU_Client.exe\r\n",
        encoding="utf-8"
    )
    (client_pkg / "START_TRANSCODER.bat").write_text(
        "@echo off\r\ntitle Single Video Transcoder Hub\r\ncd /d \"%~dp0\"\r\nstart Clipchamp_GPU_Client.exe --transcoder\r\n",
        encoding="utf-8"
    )
    (client_pkg / "QUICKSTART_GUIDE.txt").write_text(
        "=== CLIPCHAMP GPU CLIENT STUDIO (CSC-334) ===\n\n"
        "HOW TO RUN ON A FRESH PC:\n"
        "1. Double-click START_CLIENT.bat to open the Clipchamp Studio Video Editor.\n"
        "2. In the top bar, enter the Host IP address provided by the Host PC.\n"
        "3. Edit your video (cuts, text overlays, aesthetic filters, audio mixing).\n"
        "4. Click 'Export with Host GPU' to offload chunked video rendering to the Host GPU!\n\n"
        "To transcode single videos, double-click START_TRANSCODER.bat.\n"
        "No Python, no Git, and no external FFmpeg installation is required.\n",
        encoding="utf-8"
    )

    print("\n" + "=" * 70)
    print("[OK] BUILD COMPLETE!")
    print(f"  * Host Package   : {host_pkg}")
    print(f"  * Client Package : {client_pkg}")
    print("=" * 70)


if __name__ == "__main__":
    build()

