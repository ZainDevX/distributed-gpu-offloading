"""
GPU and System Hardware Capability Detector.
Probes NVIDIA GPU status, VRAM availability, driver version, and hardware encoder capabilities.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from common.utils import get_ffmpeg_binary

logger = logging.getLogger("GPUDetector")


class GPUDetector:
    """Detects and monitors GPU hardware and FFmpeg encoder capabilities."""

    @staticmethod
    def get_nvidia_smi_info() -> Dict[str, Any]:
        """Query nvidia-smi for GPU name, driver version, memory, and utilization."""
        info: Dict[str, Any] = {
            "has_nvidia_gpu": False,
            "gpu_name": "None",
            "driver_version": "N/A",
            "cuda_version": "N/A",
            "vram_total_mb": 0,
            "vram_free_mb": 0,
            "vram_used_mb": 0,
            "gpu_utilization_pct": 0,
            "temperature_c": 0,
        }

        smi_path = shutil.which("nvidia-smi")
        if not smi_path:
            return info

        try:
            # Query detailed CSV data
            cmd = [
                smi_path,
                "--query-gpu=name,driver_version,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 7:
                    info["has_nvidia_gpu"] = True
                    info["gpu_name"] = parts[0]
                    info["driver_version"] = parts[1]
                    info["vram_total_mb"] = int(float(parts[2]))
                    info["vram_free_mb"] = int(float(parts[3]))
                    info["vram_used_mb"] = int(float(parts[4]))
                    info["gpu_utilization_pct"] = int(float(parts[5])) if parts[5] != "[Not Supported]" else 0
                    info["temperature_c"] = int(float(parts[6])) if parts[6] != "[Not Supported]" else 0

            # Query CUDA version
            res_full = subprocess.run([smi_path], capture_output=True, text=True, timeout=3)
            cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", res_full.stdout)
            if cuda_match:
                info["cuda_version"] = cuda_match.group(1)

        except Exception as e:
            logger.warning(f"Error querying nvidia-smi: {e}")

        return info

    @staticmethod
    def get_supported_ffmpeg_encoders() -> List[str]:
        """Query FFmpeg binary for available video encoders."""
        ffmpeg_bin = get_ffmpeg_binary()
        encoders = []
        try:
            res = subprocess.run([ffmpeg_bin, "-encoders"], capture_output=True, text=True, timeout=5, errors="ignore")
            output = res.stdout
            for line in output.splitlines():
                if line.startswith(" V"):
                    parts = line.split()
                    if len(parts) >= 2:
                        encoders.append(parts[1])
        except Exception as e:
            logger.warning(f"Error probing FFmpeg encoders: {e}")
        return encoders

    @staticmethod
    def test_nvenc_operational() -> Dict[str, Any]:
        """
        Perform a 1-frame micro-transcode test with h264_nvenc to verify that the
        installed NVIDIA driver actually supports the NVENC API version required by FFmpeg.
        """
        ffmpeg_bin = get_ffmpeg_binary()
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=0.1:size=256x256:rate=10",
            "-c:v", "h264_nvenc",
            "-f", "null",
            "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return {"nvenc_available": True, "error": None}
            else:
                error_msg = res.stderr
                # Look for lines mentioning nvenc or driver version
                specific_lines = []
                for line in error_msg.splitlines():
                    low = line.lower()
                    if "nvenc" in low or "driver" in low or "minimum required" in low:
                        specific_lines.append(line.strip())
                msg = " | ".join(specific_lines[:2]) if specific_lines else "NVENC initialization failed."
                return {"nvenc_available": False, "error": msg}
        except Exception as e:
            return {"nvenc_available": False, "error": str(e)}

    @classmethod
    def get_worker_capabilities(cls) -> Dict[str, Any]:
        """
        Aggregate complete hardware profile of worker node.
        Sent to client during connection handshake.
        """
        smi = cls.get_nvidia_smi_info()
        encoders = cls.get_supported_ffmpeg_encoders()
        nvenc_test = cls.test_nvenc_operational()

        has_nvenc = "h264_nvenc" in encoders and nvenc_test["nvenc_available"]
        has_mf = "h264_mf" in encoders
        has_x264 = "libx264" in encoders

        return {
            "has_nvidia_gpu": smi["has_nvidia_gpu"],
            "gpu_name": smi["gpu_name"],
            "driver_version": smi["driver_version"],
            "cuda_version": smi["cuda_version"],
            "vram_total_mb": smi["vram_total_mb"],
            "vram_free_mb": smi["vram_free_mb"],
            "vram_used_mb": smi["vram_used_mb"],
            "gpu_utilization_pct": smi["gpu_utilization_pct"],
            "temperature_c": smi["temperature_c"],
            "nvenc_operational": nvenc_test["nvenc_available"],
            "nvenc_status_message": "Operational" if nvenc_test["nvenc_available"] else nvenc_test.get("error", "Unavailable"),
            "supported_codecs": {
                "h264_nvenc": "h264_nvenc" in encoders,
                "hevc_nvenc": "hevc_nvenc" in encoders,
                "h264_mf": has_mf,
                "libx264": has_x264,
                "libx265": "libx265" in encoders,
            },
            "preferred_gpu_encoder": "h264_nvenc" if has_nvenc else ("h264_mf" if has_mf else "libx264"),
        }
