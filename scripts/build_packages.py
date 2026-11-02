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

    print("\n" + "=" * 70)
    print("✅ BUILD COMPLETE!")
    print(f"  • Host Package   : {host_pkg}")
    print(f"  • Client Package : {client_pkg}")
    print("=" * 70)


if __name__ == "__main__":
    build()
