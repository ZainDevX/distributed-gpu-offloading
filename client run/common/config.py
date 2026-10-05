"""
Global configuration and default parameters for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing
"""

import os
from pathlib import Path

# Networking & Protocol Configuration
DEFAULT_HOST = "0.0.0.0"
DEFAULT_CLIENT_TARGET = "127.0.0.1"
DEFAULT_PORT = 5050

# Protocol Framing
MAGIC_BYTES = b"DGPO"  # Distributed GPU Offloading Magic Header
PROTOCOL_VERSION = 1

# Socket I/O
CHUNK_SIZE = 64 * 1024  # 64 KB per network packet chunk
SOCKET_TIMEOUT = 20.0   # 20 seconds timeout for general read/write
CONNECT_TIMEOUT = 5.0   # 5 seconds initial connection timeout
PING_TIMEOUT = 3.0      # 3 seconds latency ping timeout
HEARTBEAT_INTERVAL = 5.0 # Periodic keepalive interval

# Supported Video Codecs & Hardware Acceleration Flags
CODEC_H264_NVENC = "h264_nvenc"
CODEC_HEVC_NVENC = "hevc_nvenc"
CODEC_H264_MF = "h264_mf"
CODEC_LIBX264 = "libx264"
CODEC_LIBX265 = "libx265"
CODEC_AUTO = "auto_detect"

SUPPORTED_CODECS = [
    CODEC_AUTO,
    CODEC_H264_NVENC,
    CODEC_HEVC_NVENC,
    CODEC_H264_MF,
    CODEC_LIBX264,
    CODEC_LIBX265,
]

# Presets mapping for NVENC and CPU
NVENC_PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
CPU_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]

# Resolution definitions
RESOLUTIONS = {
    "Original": None,
    "480p (SD 854x480)": (854, 480),
    "720p (HD 1280x720)": (1280, 720),
    "1080p (FHD 1920x1080)": (1920, 1080),
    "1440p (2K 2560x1440)": (2560, 1440),
    "2160p (4K UHD 3840x2160)": (3840, 2160),
}

# Bitrate presets in kbps
BITRATE_PRESETS = [
    "Original / Auto",
    "1500k",
    "3000k",
    "5000k",
    "8000k",
    "12000k",
    "20000k",
    "35000k",
]

# Supported Input Containers
ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v"}

# Work Directories
BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_WORKDIR = BASE_DIR / "server_workspace"
CLIENT_OUTPUT_DIR = BASE_DIR / "client_outputs"
TEST_MEDIA_DIR = BASE_DIR / "test_media"

for directory in (SERVER_WORKDIR, CLIENT_OUTPUT_DIR, TEST_MEDIA_DIR):
    directory.mkdir(parents=True, exist_ok=True)
