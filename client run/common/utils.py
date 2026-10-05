"""
Utility functions for Distributed GPU Offloading System.
Checksum validation, formatting, network discovery, and media probing.
Course: CSC-334 Parallel and Distributed Computing
"""

import hashlib
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import imageio_ffmpeg


def calculate_sha256(file_path: Path, progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """
    Compute SHA-256 checksum of a file in chunks.
    Allows real-time verification progress tracking.
    """
    hasher = hashlib.sha256()
    total_bytes = os.path.getsize(file_path)
    read_bytes = 0
    buffer_size = 256 * 1024  # 256 KB read buffer

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(buffer_size)
            if not chunk:
                break
            hasher.update(chunk)
            read_bytes += len(chunk)
            if progress_callback:
                progress_callback(read_bytes, total_bytes)

    return hasher.hexdigest()


def format_bytes(num_bytes: float) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds into HH:MM:SS.SS or MM:SS."""
    if seconds < 0:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"
    return f"{int(m):02d}:{s:05.2f}"


def get_local_ip() -> str:
    """
    Attempt to find the preferred local IP address by connecting to an external socket.
    Falls back to 127.0.0.1 if disconnected.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting to a public UDP address doesn't send packets, but assigns the outbound interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_all_interfaces() -> List[Dict[str, str]]:
    """Return list of local IPv4 addresses and interface hostnames."""
    interfaces = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            interfaces.append({"ip": ip, "hostname": hostname})
    except Exception:
        pass
    if not interfaces:
        interfaces.append({"ip": "127.0.0.1", "hostname": "localhost"})
    return interfaces


def get_ffmpeg_binary() -> str:
    """Retrieve FFmpeg executable binary path from imageio_ffmpeg or system PATH."""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe_media_file(file_path: Path) -> Dict[str, Any]:
    """
    Probe video file metadata using FFmpeg output.
    Returns: duration_seconds, width, height, fps, bitrate_kbps, video_codec, audio_codec.
    """
    ffmpeg_bin = get_ffmpeg_binary()
    file_path_str = str(file_path)

    cmd = [ffmpeg_bin, "-i", file_path_str]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
    output = result.stderr

    info: Dict[str, Any] = {
        "file_name": os.path.basename(file_path),
        "file_size": os.path.getsize(file_path),
        "duration_seconds": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "bitrate_kbps": 0,
        "video_codec": "Unknown",
        "audio_codec": "None",
    }

    # Parse Duration: 00:00:05.00, start: 0.000000, bitrate: 1234 kb/s
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", output)
    if dur_match:
        hours = float(dur_match.group(1))
        minutes = float(dur_match.group(2))
        seconds = float(dur_match.group(3))
        info["duration_seconds"] = hours * 3600 + minutes * 60 + seconds

    bitrate_match = re.search(r"bitrate:\s*(\d+)\s*kb/s", output)
    if bitrate_match:
        info["bitrate_kbps"] = int(bitrate_match.group(1))

    # Parse Video stream: Stream #0:0: Video: h264 (...), yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], 30 fps
    video_match = re.search(r"Stream.*Video:\s*([a-zA-Z0-9_\-]+).*?,\s*(\d{3,5})x(\d{3,5})", output)
    if video_match:
        info["video_codec"] = video_match.group(1)
        info["width"] = int(video_match.group(2))
        info["height"] = int(video_match.group(3))

    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", output)
    if fps_match:
        info["fps"] = float(fps_match.group(1))

    # Parse Audio stream
    audio_match = re.search(r"Stream.*Audio:\s*([a-zA-Z0-9_\-]+)", output)
    if audio_match:
        info["audio_codec"] = audio_match.group(1)

    return info
