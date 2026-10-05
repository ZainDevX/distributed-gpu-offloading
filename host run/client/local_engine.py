"""
Local CPU Benchmark Execution Engine.
Executes transcoding locally on client CPU for speedup factor evaluation.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import CLIENT_OUTPUT_DIR, RESOLUTIONS
from common.utils import calculate_sha256, format_duration, get_ffmpeg_binary, probe_media_file

logger = logging.getLogger("LocalEngine")


class LocalBenchmarkEngine:
    """Executes media transcoding locally on the client's CPU."""

    def __init__(self):
        self.ffmpeg_bin = get_ffmpeg_binary()
        self.cancel_requested = False
        self.current_process: Optional[subprocess.Popen] = None

    def cancel(self):
        self.cancel_requested = True
        if self.current_process:
            try:
                self.current_process.kill()
            except Exception:
                pass

    def run_local_transcode(
        self,
        input_path: Path,
        config: Dict[str, Any],
        output_dir: Path = CLIENT_OUTPUT_DIR,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Run transcode locally on client CPU using libx264.
        Returns execution metrics dictionary.
        """
        self.cancel_requested = False
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        def emit_progress(data: Dict[str, Any]):
            if progress_callback:
                progress_callback(data)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        media_info = probe_media_file(input_path)
        total_duration = media_info.get("duration_seconds", 0.0)
        log(f"[LOCAL CPU] Starting local benchmark for: {input_path.name} | Duration: {format_duration(total_duration)}")

        out_name = f"local_cpu_{input_path.stem}.mp4"
        output_path = output_dir / out_name

        cmd = [self.ffmpeg_bin, "-y", "-loglevel", "error", "-nostats", "-i", str(input_path)]

        # Resolution scaling
        res_key = config.get("resolution", "Original")
        res_tuple = RESOLUTIONS.get(res_key)
        if res_tuple:
            w, h = res_tuple
            vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            cmd.extend(["-vf", vf])
        else:
            cmd.extend(["-pix_fmt", "yuv420p"])

        # Force software CPU encoder for client baseline
        cmd.extend(["-c:v", "libx264", "-preset", "medium"])

        # Bitrate
        bitrate_str = config.get("bitrate", "Original / Auto")
        if bitrate_str and bitrate_str != "Original / Auto":
            clean_b = bitrate_str.replace("k", "").strip()
            cmd.extend(["-b:v", f"{clean_b}k"])

        # Audio
        audio_opt = config.get("audio", "copy")
        if audio_opt == "mute":
            cmd.append("-an")
        elif audio_opt == "aac":
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-c:a", "copy"])

        cmd.extend(["-progress", "pipe:1", str(output_path)])

        start_time = time.time()
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            errors="replace",
        )

        current_stats: Dict[str, Any] = {
            "stage": "Local CPU Transcoding",
            "percent": 0.0,
            "frame": 0,
            "fps": 0.0,
            "speed": "0.0x",
            "bitrate": "0k",
            "elapsed_seconds": 0.0,
            "eta_seconds": 0.0,
            "encoder": "libx264 (Software CPU)",
        }

        last_cb = 0.0
        try:
            for line in self.current_process.stdout:
                if self.cancel_requested:
                    self.current_process.kill()
                    break

                line = line.strip()
                if not line or "=" not in line:
                    continue

                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()

                if k == "frame":
                    try:
                        current_stats["frame"] = int(v)
                    except ValueError:
                        pass
                elif k == "fps":
                    try:
                        current_stats["fps"] = float(v)
                    except ValueError:
                        pass
                elif k == "speed":
                    current_stats["speed"] = v
                elif k == "out_time_us":
                    try:
                        cur_sec = float(v) / 1_000_000.0
                        if total_duration > 0:
                            pct = min(99.0, (cur_sec / total_duration) * 100.0)
                            current_stats["percent"] = round(pct, 1)
                            sp_m = re.search(r"([0-9.]+)x", current_stats["speed"])
                            if sp_m:
                                sp_val = float(sp_m.group(1))
                                if sp_val > 0:
                                    current_stats["eta_seconds"] = max(0.0, (total_duration - cur_sec) / sp_val)
                    except ValueError:
                        pass

                now = time.time()
                current_stats["elapsed_seconds"] = round(now - start_time, 2)
                if now - last_cb >= 0.1:
                    last_cb = now
                    emit_progress(dict(current_stats))

            self.current_process.wait()
        finally:
            self.current_process = None

        if self.cancel_requested:
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError("Local CPU transcode cancelled by user.")

        total_time = time.time() - start_time
        out_size = os.path.getsize(output_path) if output_path.exists() else 0
        sha256_hash = calculate_sha256(output_path) if output_path.exists() else ""

        current_stats["percent"] = 100.0
        current_stats["stage"] = "Local Completed"
        emit_progress(dict(current_stats))

        log(f"[LOCAL CPU] Completed in {total_time:.2f}s | Output: {out_name} ({out_size} bytes)")

        return {
            "status": "success",
            "type": "local_cpu",
            "execution_time_seconds": round(total_time, 2),
            "output_path": str(output_path),
            "output_size_bytes": out_size,
            "output_sha256": sha256_hash,
            "encoder": "libx264 (Local CPU)",
        }
