"""
Local Project Executor for Clipchamp Studio.
Renders projects locally on the client CPU for previewing and benchmark comparison.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from clipchamp_studio.engine.chunker import TimelineChunker
from clipchamp_studio.engine.ffmpeg_builder import FFmpegBuilder
from clipchamp_studio.model.project import ClipchampProject
from common.utils import calculate_sha256, get_ffmpeg_binary


class LocalProjectExecutor:
    """Executes Clipchamp rendering locally on Client CPU for baseline benchmarking."""

    def __init__(self, workdir: Optional[Path] = None):
        self.workdir = Path(workdir or Path(__file__).resolve().parent.parent / "temp_render")
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.builder = FFmpegBuilder()

    def render_project_locally(
        self,
        project: ClipchampProject,
        output_file: Path,
        use_chunking: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute full local render on CPU (libx264) and measure exact execution time.
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        def log(m: str):
            if log_callback:
                log_callback(m)

        log(f"[LOCAL CPU] Starting local benchmark render for '{project.project_name}'...")
        chunks = TimelineChunker.partition_project(
            project,
            chunk_duration=project.chunk_duration if use_chunking else project.total_duration,
        )
        total_chunks = len(chunks)
        chunk_files: List[Path] = []

        try:
            for idx, chunk in enumerate(chunks):
                chunk_out = self.workdir / f"local_chunk_{project.project_id}_{idx:03d}.mp4"
                chunk_files.append(chunk_out)

                log(f"[LOCAL CPU] Rendering chunk {idx + 1}/{total_chunks} ({chunk.duration:.1f}s) on CPU...")
                cmd = self.builder.build_chunk_render_cmd(
                    chunk=chunk,
                    output_file=chunk_out,
                    resolution=project.resolution,
                    fps=project.fps,
                    codec="libx264",
                    bitrate=project.export_bitrate,
                )

                # Spawn FFmpeg
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    errors="replace",
                )

                while True:
                    line = proc.stdout.readline()
                    if not line and proc.poll() is not None:
                        break
                    line = line.strip()
                    if "=" in line:
                        k, _, v = line.partition("=")
                        if k == "progress" and v == "end":
                            break

                proc.wait()
                if proc.stdout:
                    proc.stdout.close()
                if proc.returncode != 0:
                    raise RuntimeError(f"FFmpeg CPU render failed on chunk {idx + 1}")

                pct = round(((idx + 1) / total_chunks) * 100.0, 1)
                if progress_callback:
                    progress_callback({
                        "stage": f"Local CPU Render (Chunk {idx + 1}/{total_chunks})",
                        "percent": pct,
                        "current_chunk": idx + 1,
                        "total_chunks": total_chunks,
                    })

            # Lossless concatenation of chunks
            if total_chunks > 1:
                log("[LOCAL CPU] Concatenating rendered chunks...")
                manifest_path = self.workdir / f"concat_{project.project_id}.txt"
                self.builder.build_concat_manifest(chunk_files, manifest_path)
                concat_cmd = self.builder.build_concat_cmd(manifest_path, output_file)
                subprocess.run(concat_cmd, check=True, capture_output=True)
            else:
                import shutil
                shutil.copy2(chunk_files[0], output_file)

        finally:
            # Clean up temp chunks
            for cf in chunk_files:
                if cf.exists():
                    try:
                        cf.unlink()
                    except Exception:
                        pass

        duration = time.time() - start_time
        out_size = os.path.getsize(output_file) if output_file.exists() else 0
        sha = calculate_sha256(output_file) if output_file.exists() else ""

        log(f"[LOCAL CPU] Render complete in {duration:.2f}s | Size: {out_size} bytes")

        return {
            "status": "success",
            "output_file": str(output_file),
            "output_size_bytes": out_size,
            "execution_time_seconds": round(duration, 2),
            "sha256": sha,
            "engine": "CPU (libx264)",
        }
