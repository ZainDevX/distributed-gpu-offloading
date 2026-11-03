"""
Server-Side Chunked Project Execution Engine.
Executes parallel and fault-tolerant video chunk transcoding on Host GPU (NVENC / Hardware MFT),
with per-chunk progress streaming and instantaneous lossless concatenation.
"""

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from clipchamp_studio.engine.chunker import RenderChunk, TimelineChunker
from clipchamp_studio.engine.ffmpeg_builder import FFmpegBuilder
from clipchamp_studio.model.project import ClipchampProject
from common.utils import calculate_sha256, format_duration, get_ffmpeg_binary
from server.execution_engine import ExecutionEngine
from server.gpu_detector import GPUDetector

logger = logging.getLogger("ChunkedProjectEngine")


class ChunkedProjectEngine:
    """Renders Clipchamp projects using Host GPU hardware acceleration with chunking."""

    def __init__(self, allow_cpu_fallback: bool = True):
        self.allow_cpu_fallback = allow_cpu_fallback
        self.ffmpeg_bin = get_ffmpeg_binary()
        self.builder = FFmpegBuilder(self.ffmpeg_bin)
        self.exec_engine = ExecutionEngine(allow_cpu_fallback=allow_cpu_fallback)

    def execute_project(
        self,
        project_data: Dict[str, Any],
        asset_cache_dir: Path,
        output_dir: Path,
        job_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Execute full distributed chunked export on Host GPU:
        1. Resolve asset files in server cache.
        2. Detect optimal GPU encoder (NVENC / Hardware MFT).
        3. Partition timeline into chunks.
        4. Render chunks on GPU with live progress streaming.
        5. Losslessly concatenate into master output video.
        6. Compute cryptographic SHA-256 integrity hash.
        """
        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        def emit_progress(data: Dict[str, Any]):
            if progress_callback:
                progress_callback(data)

        start_time = time.time()
        project = ClipchampProject.from_dict(project_data)
        log(f"[CHUNK-ENGINE] Commencing GPU export for project: '{project.project_name}' (ID: {job_id})")

        # 1. Resolve Assets
        asset_resolver: Dict[str, str] = {}
        for asset in project_data.get("assets", []):
            sha = asset.get("sha256", "")
            fname = asset.get("filename", "")
            # Check potential cached filenames
            candidates = [
                asset_cache_dir / f"{sha}_{fname}",
                asset_cache_dir / fname,
                asset_cache_dir / f"{sha}.mp4",
                asset_cache_dir / f"{sha}.mp3",
            ]
            found_path = None
            for c in candidates:
                if c.exists():
                    found_path = str(c.resolve())
                    break

            if found_path:
                asset_resolver[sha] = found_path
                asset_resolver[fname] = found_path
                asset_resolver[asset.get("local_path", "")] = found_path
            else:
                log(f"[CHUNK-ENGINE] [WARNING] Asset not in cache: {fname} ({sha[:10]}...)")

        # 2. Determine Optimal GPU Hardware Encoder
        req_codec = project.export_codec
        actual_codec, codec_reason = self.exec_engine.determine_encoder(req_codec, log_callback)
        caps = GPUDetector.get_worker_capabilities()
        gpu_name = caps.get("gpu_name", "Host GPU")
        log(f"[CHUNK-ENGINE] GPU Hardware Acceleration: {actual_codec} ({codec_reason}) on {gpu_name}")

        # 3. Partition into Chunks
        chunk_dur = project.chunk_duration if project.use_chunking else project.total_duration
        chunks = TimelineChunker.partition_project(project, chunk_duration=chunk_dur)
        total_chunks = len(chunks)
        total_timeline_sec = max(0.1, project.total_duration)
        log(f"[CHUNK-ENGINE] Partitioned timeline ({total_timeline_sec:.2f}s) into {total_chunks} chunk(s) (chunk_size: {chunk_dur}s)")

        # Prepare chunk working directory
        chunk_dir = output_dir / f"chunks_{job_id}"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        rendered_chunk_files: List[Path] = []

        try:
            for idx, chunk in enumerate(chunks):
                if cancel_check and cancel_check():
                    raise RuntimeError("Export cancelled by client.")

                chunk_file = chunk_dir / f"chunk_{idx:04d}.mp4"
                rendered_chunk_files.append(chunk_file)

                log(f"[CHUNK-ENGINE] Rendering Chunk {idx + 1}/{total_chunks} (Window: {chunk.window_start:.1f}s - {chunk.window_end:.1f}s)...")

                cmd = self.builder.build_chunk_render_cmd(
                    chunk=chunk,
                    output_file=chunk_file,
                    resolution=project.resolution,
                    fps=project.fps,
                    codec=actual_codec,
                    bitrate=project.export_bitrate,
                    asset_path_resolver=asset_resolver,
                )

                chunk_start_t = time.time()
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    errors="replace",
                )

                stderr_lines: List[str] = []
                def _read_stderr():
                    try:
                        for err_line in iter(proc.stderr.readline, ""):
                            if err_line:
                                stderr_lines.append(err_line.strip())
                                if len(stderr_lines) > 25:
                                    stderr_lines.pop(0)
                    except Exception:
                        pass
                    finally:
                        if proc.stderr:
                            try:
                                proc.stderr.close()
                            except Exception:
                                pass

                import threading
                err_thread = threading.Thread(target=_read_stderr, daemon=True)
                err_thread.start()

                chunk_fps = 0.0
                chunk_speed = "1.0x"
                chunk_percent = 0.0

                while True:
                    if cancel_check and cancel_check():
                        proc.kill()
                        raise RuntimeError("Export cancelled by client.")

                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break

                    line = line.strip()
                    if not line or "=" not in line:
                        continue

                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip()

                    if k == "fps":
                        try:
                            chunk_fps = float(v)
                        except ValueError:
                            pass
                    elif k == "speed":
                        chunk_speed = v
                    elif k == "out_time_us":
                        try:
                            c_sec = float(v) / 1_000_000.0
                            if chunk.duration > 0:
                                chunk_percent = min(99.0, (c_sec / chunk.duration) * 100.0)
                        except ValueError:
                            pass
                    elif k == "progress" and v == "end":
                        chunk_percent = 100.0

                    # Overall progress calculation
                    completed_chunks_time = idx * chunk_dur
                    current_chunk_time = (chunk_percent / 100.0) * chunk.duration
                    overall_percent = min(99.0, ((completed_chunks_time + current_chunk_time) / total_timeline_sec) * 100.0)

                    emit_progress({
                        "stage": f"GPU Rendering Chunk {idx + 1}/{total_chunks}",
                        "current_chunk": idx + 1,
                        "total_chunks": total_chunks,
                        "chunk_percent": round(chunk_percent, 1),
                        "total_percent": round(overall_percent, 1),
                        "fps": chunk_fps,
                        "speed": chunk_speed,
                        "encoder": actual_codec,
                        "gpu_name": gpu_name,
                        "elapsed_seconds": round(time.time() - start_time, 2),
                    })

                proc.wait()
                if proc.stdout:
                    proc.stdout.close()
                err_thread.join(timeout=0.5)

                if proc.returncode != 0:
                    err_details = " | ".join(stderr_lines[-5:]) if stderr_lines else f"code {proc.returncode}"
                    log(f"[CHUNK-ENGINE] [ERROR] Chunk {idx + 1} failed: {err_details}")
                    # If NVENC failed, try software fallback for this chunk
                    if "nvenc" in actual_codec and self.allow_cpu_fallback:
                        log("[CHUNK-ENGINE] Retrying chunk with CPU fallback...")
                        cmd_fallback = self.builder.build_chunk_render_cmd(
                            chunk=chunk,
                            output_file=chunk_file,
                            resolution=project.resolution,
                            fps=project.fps,
                            codec="libx264",
                            bitrate=project.export_bitrate,
                            asset_path_resolver=asset_resolver,
                        )
                        subprocess.run(cmd_fallback, check=True)
                    else:
                        raise RuntimeError(f"FFmpeg failed while rendering chunk {idx + 1}: {err_details}")

                chunk_elapsed = time.time() - chunk_start_t
                log(f"[CHUNK-ENGINE] Chunk {idx + 1}/{total_chunks} completed in {chunk_elapsed:.2f}s")

            # 4. Seamless Lossless Concatenation
            emit_progress({
                "stage": "Stitching Chunks Losslessly",
                "total_percent": 99.0,
                "current_chunk": total_chunks,
                "total_chunks": total_chunks,
            })

            clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', project.project_name)
            final_filename = f"exported_{job_id}_{clean_name}.mp4"
            final_output_path = output_dir / final_filename

            if total_chunks > 1:
                log(f"[CHUNK-ENGINE] Assembling {total_chunks} chunks into final video: {final_filename}...")
                manifest_path = chunk_dir / "chunks_manifest.txt"
                self.builder.build_concat_manifest(rendered_chunk_files, manifest_path)
                concat_cmd = self.builder.build_concat_cmd(manifest_path, final_output_path)
                concat_res = subprocess.run(concat_cmd, capture_output=True, text=True)
                if concat_res.returncode != 0:
                    raise RuntimeError(f"Concatenation failed: {concat_res.stderr}")
            else:
                shutil.copy2(rendered_chunk_files[0], final_output_path)

        finally:
            # Clean up intermediate chunk parts to save disk space
            try:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            except Exception:
                pass

        total_exec_time = time.time() - start_time
        out_size = os.path.getsize(final_output_path)
        out_sha = calculate_sha256(final_output_path)

        emit_progress({
            "stage": "GPU Export Complete",
            "total_percent": 100.0,
            "current_chunk": total_chunks,
            "total_chunks": total_chunks,
            "elapsed_seconds": round(total_exec_time, 2),
        })

        log(f"[CHUNK-ENGINE] Export successfully assembled! Time: {total_exec_time:.2f}s | "
            f"Size: {out_size} bytes | SHA-256: {out_sha[:12]}...")

        return {
            "status": "success",
            "job_id": job_id,
            "output_path": str(final_output_path.resolve()),
            "output_filename": final_filename,
            "output_filesize": out_size,
            "output_sha256": out_sha,
            "execution_time_seconds": round(total_exec_time, 2),
            "chunks_rendered": total_chunks,
            "encoder_used": actual_codec,
            "gpu_name": gpu_name,
        }
