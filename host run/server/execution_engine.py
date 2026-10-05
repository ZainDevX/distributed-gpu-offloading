"""
Execution Engine for Hardware-Accelerated Video Transcoding & Compute Tasks.
Executes FFmpeg with NVENC / CUDA / fallback encoders and streams real-time progress.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from common.config import RESOLUTIONS
from common.utils import calculate_sha256, format_duration, get_ffmpeg_binary, probe_media_file
from server.gpu_detector import GPUDetector
from server.task_queue import JobRecord

logger = logging.getLogger("ExecutionEngine")


class ExecutionEngine:
    """Manages execution of compute-heavy transcoding workloads on GPU/CPU."""

    def __init__(self, allow_cpu_fallback: bool = True):
        self.allow_cpu_fallback = allow_cpu_fallback
        self.ffmpeg_bin = get_ffmpeg_binary()

    def determine_encoder(self, requested_codec: str, log_callback: Optional[Callable[[str], None]] = None) -> Tuple[str, str]:
        """
        Determine actual encoder to use based on requested codec and hardware capability.
        Returns: (encoder_name, reason_description)
        """
        caps = GPUDetector.get_worker_capabilities()
        supported = caps.get("supported_codecs", {})
        nvenc_ok = caps.get("nvenc_operational", False)

        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        if requested_codec == "auto_detect":
            if nvenc_ok and supported.get("h264_nvenc"):
                log(f"[ENGINE] Auto-detect selected: NVIDIA NVENC Hardware Engine (h264_nvenc) on {caps['gpu_name']}")
                return "h264_nvenc", "Auto-detected NVIDIA NVENC"
            elif supported.get("h264_mf"):
                log(f"[ENGINE] Auto-detect selected: Hardware Acceleration (h264_mf) on {caps['gpu_name']}")
                return "h264_mf", "Auto-detected Windows Hardware Acceleration (MFT)"
            else:
                log("[ENGINE] Auto-detect selected: Software Encoder (libx264)")
                return "libx264", "Auto-detected Software Fallback"

        if requested_codec in ("h264_nvenc", "hevc_nvenc"):
            if nvenc_ok and supported.get(requested_codec):
                log(f"[ENGINE] Using requested NVIDIA NVENC encoder: {requested_codec} on {caps['gpu_name']}")
                return requested_codec, f"NVIDIA NVENC Hardware Engine ({caps['gpu_name']})"
            else:
                warning_reason = caps.get("nvenc_status_message", "Driver/Hardware incompatibility")
                log(f"[ENGINE] [WARNING] {requested_codec} requested, but NVENC is not ready: {warning_reason}")
                if self.allow_cpu_fallback:
                    fallback = "h264_mf" if supported.get("h264_mf") else "libx264"
                    log(f"[ENGINE] Gracefully switching to fallback encoder: {fallback}")
                    return fallback, f"Fallback to {fallback} ({warning_reason})"
                else:
                    raise RuntimeError(f"NVENC requested but unavailable: {warning_reason}")

        if requested_codec in supported and supported[requested_codec]:
            log(f"[ENGINE] Using specified encoder: {requested_codec}")
            return requested_codec, f"User-selected {requested_codec}"

        log(f"[ENGINE] Fallback to default software encoder: libx264")
        return "libx264", "Default software encoder"

    def execute_transcode(
        self,
        job: JobRecord,
        output_dir: Path,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """
        Execute FFmpeg transcoding with hardware acceleration and live progress streaming.
        Updates job status, progress dictionary, and verifies output integrity.
        """
        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        input_path = job.input_path
        if not input_path or not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Probe input file to get total duration for accurate percentage calculation
        media_info = probe_media_file(input_path)
        total_duration = media_info.get("duration_seconds", 0.0)
        log(f"[ENGINE] Input media probed: {input_path.name} | Duration: {format_duration(total_duration)} | "
            f"Res: {media_info.get('width')}x{media_info.get('height')} | FPS: {media_info.get('fps')}")

        # Determine target parameters
        cfg = job.config
        req_codec = cfg.get("codec", "auto_detect")
        actual_codec, codec_reason = self.determine_encoder(req_codec, log_callback)

        # Build output filename
        ext = ".mp4"
        out_name = f"rendered_{job.job_id}_{input_path.stem}{ext}"
        output_path = output_dir / out_name

        # Build FFmpeg command
        cmd = [self.ffmpeg_bin, "-y", "-loglevel", "error", "-nostats", "-i", str(input_path)]

        # Resolution scaling
        resolution_key = cfg.get("resolution", "Original")
        res_tuple = RESOLUTIONS.get(resolution_key)
        if res_tuple:
            w, h = res_tuple
            # Scale and pad to maintain aspect ratio
            vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            cmd.extend(["-vf", vf])
        else:
            cmd.extend(["-pix_fmt", "yuv420p"])

        # Codec & hardware parameters
        cmd.extend(["-c:v", actual_codec])

        # Bitrate configuration
        bitrate_str = cfg.get("bitrate", "Original / Auto")
        if bitrate_str and bitrate_str != "Original / Auto":
            clean_b = bitrate_str.replace("k", "").strip()
            cmd.extend(["-b:v", f"{clean_b}k"])

        # Presets
        preset = cfg.get("preset", "p4" if "nvenc" in actual_codec else "medium")
        if "nvenc" in actual_codec:
            cmd.extend(["-preset", preset if preset.startswith("p") else "p4"])
            cmd.extend(["-rc", "vbr"])
        elif actual_codec in ("libx264", "libx265"):
            cmd.extend(["-preset", preset if not preset.startswith("p") else "medium"])

        # Audio settings
        audio_opt = cfg.get("audio", "copy")
        if audio_opt == "mute":
            cmd.append("-an")
        elif audio_opt == "aac":
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-c:a", "copy"])

        # Add progress pipe flag (pipe:1 outputs key=value progress lines to stdout)
        cmd.extend(["-progress", "pipe:1", str(output_path)])

        log(f"[ENGINE] Starting FFmpeg process: {' '.join(cmd[:8])} ...")

        # Spawn FFmpeg subprocess
        start_time = time.time()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            errors="replace",
        )
        job.process_handle = proc

        # Progress tracking state
        current_stats: Dict[str, Any] = {
            "stage": f"Transcoding ({actual_codec})",
            "percent": 0.0,
            "frame": 0,
            "fps": 0.0,
            "speed": "0.0x",
            "bitrate": "0k",
            "out_time": "00:00:00.00",
            "elapsed_seconds": 0.0,
            "eta_seconds": 0.0,
            "encoder": actual_codec,
            "engine_note": codec_reason,
        }

        # Read progress from stdout
        last_callback_time = 0.0
        try:
            for line in proc.stdout:
                if job.cancel_requested:
                    log("[ENGINE] Job cancellation requested; terminating FFmpeg.")
                    proc.kill()
                    break

                line = line.strip()
                if not line or "=" not in line:
                    continue

                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()

                if key == "frame":
                    try:
                        current_stats["frame"] = int(val)
                    except ValueError:
                        pass
                elif key == "fps":
                    try:
                        current_stats["fps"] = float(val)
                    except ValueError:
                        pass
                elif key == "bitrate":
                    current_stats["bitrate"] = val
                elif key == "speed":
                    current_stats["speed"] = val
                elif key == "out_time":
                    current_stats["out_time"] = val
                elif key == "out_time_us":
                    try:
                        cur_sec = float(val) / 1_000_000.0
                        if total_duration > 0:
                            pct = min(99.0, (cur_sec / total_duration) * 100.0)
                            current_stats["percent"] = round(pct, 1)
                            # Estimate ETA based on speed
                            sp_match = re.search(r"([0-9.]+)x", current_stats["speed"])
                            if sp_match:
                                speed_mult = float(sp_match.group(1))
                                if speed_mult > 0:
                                    rem_time = (total_duration - cur_sec) / speed_mult
                                    current_stats["eta_seconds"] = max(0.0, rem_time)
                    except ValueError:
                        pass
                elif key == "progress" and val == "end":
                    current_stats["percent"] = 100.0
                    current_stats["stage"] = "Finalizing"

                # Throttle progress callbacks to ~10 times per second
                now = time.time()
                current_stats["elapsed_seconds"] = round(now - start_time, 2)
                if now - last_callback_time >= 0.1:
                    last_callback_time = now
                    if progress_callback:
                        progress_callback(dict(current_stats))

            proc.wait()
        except Exception as e:
            proc.kill()
            raise RuntimeError(f"FFmpeg execution failed: {e}") from e

        if job.cancel_requested:
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError("Transcoding cancelled by user.")

        if proc.returncode != 0:
            stderr_out = proc.stderr.read()
            # If NVENC failed at runtime despite probing, and fallback is allowed:
            if "nvenc" in actual_codec and self.allow_cpu_fallback:
                log(f"[ENGINE] NVENC failed during execution. Retrying with software fallback...")
                cfg["codec"] = "libx264"
                return self.execute_transcode(job, output_dir, progress_callback, log_callback)
            raise RuntimeError(f"FFmpeg exited with error code {proc.returncode}: {stderr_out[-500:]}")

        # Verification of generated output
        if not output_path.exists() or os.path.getsize(output_path) == 0:
            raise RuntimeError("FFmpeg completed but output file was not created or is empty.")

        duration_taken = time.time() - start_time
        out_size = os.path.getsize(output_path)
        out_sha256 = calculate_sha256(output_path)

        current_stats["percent"] = 100.0
        current_stats["stage"] = "Completed"
        current_stats["elapsed_seconds"] = round(duration_taken, 2)
        if progress_callback:
            progress_callback(dict(current_stats))

        job.output_path = output_path
        job.output_filename = out_name
        job.output_filesize = out_size
        job.output_sha256 = out_sha256

        log(f"[ENGINE] Transcode successfully finished! Time: {duration_taken:.2f}s | "
            f"Size: {out_size} B | SHA-256: {out_sha256[:12]}...")

        return output_path
