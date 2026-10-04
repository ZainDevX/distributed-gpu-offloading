"""
Test Media Generator Utility.
Generates synthetic high-motion test videos for benchmarking without external assets.
Course: CSC-334 Parallel and Distributed Computing
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import TEST_MEDIA_DIR
from common.utils import get_ffmpeg_binary


def generate_synthetic_video(
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    duration_seconds: int = 5,
    fps: int = 30,
) -> Path:
    """
    Generate synthetic test pattern video with testsrc filter.
    Includes moving clock, color pattern, and test sound.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = get_ffmpeg_binary()

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_seconds}:size={width}x{height}:rate={fps}",
        "-f", "lavfi",
        "-i", f"sine=frequency=1000:duration={duration_seconds}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to generate synthetic video: {res.stderr}")

    return output_path


def generate_benchmark_suite(target_dir: Path = TEST_MEDIA_DIR) -> dict:
    """Generate standardized test assets for evaluation: 480p, 720p, 1080p."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    suite = {
        "480p": (854, 480, 5),
        "720p": (1280, 720, 5),
        "1080p": (1920, 1080, 5),
    }

    generated = {}
    for name, (w, h, dur) in suite.items():
        file_path = target_dir / f"test_clip_{name}.mp4"
        if not file_path.exists() or file_path.stat().st_size == 0:
            generate_synthetic_video(file_path, width=w, height=h, duration_seconds=dur)
        generated[name] = file_path

    return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic test media")
    parser.add_argument("--res", default="1080p", choices=["480p", "720p", "1080p", "4k"])
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    res_map = {
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "4k": (3840, 2160),
    }
    w, h = res_map[args.res]
    dest = Path(args.out) if args.out else TEST_MEDIA_DIR / f"test_clip_{args.res}.mp4"
    print(f"Generating {args.res} ({w}x{h}, {args.duration}s) -> {dest}")
    generate_synthetic_video(dest, width=w, height=h, duration_seconds=args.duration)
    print("Done! File generated:", dest, "Size:", dest.stat().st_size, "bytes")
