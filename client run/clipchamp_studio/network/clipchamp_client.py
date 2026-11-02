"""
Specialized Network Client for Clipchamp Studio.
Handles asset deduplication, chunked project submission, real-time GPU progress streaming,
and verified lossless output retrieval.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from clipchamp_studio.model.project import ClipchampProject
from common.config import CHUNK_SIZE, CLIENT_OUTPUT_DIR, DEFAULT_PORT
from common.protocol import (
    MSG_ASSET_CHECK_REQ,
    MSG_ASSET_CHECK_RESP,
    MSG_ASSET_UPLOAD_START,
    MSG_CHUNK_PROGRESS,
    MSG_DOWNLOAD_REQ,
    MSG_DOWNLOAD_START,
    MSG_ERROR,
    MSG_FILE_ACK,
    MSG_FILE_CHUNK,
    MSG_FILE_COMPLETE,
    MSG_JOB_ACCEPTED,
    MSG_JOB_FINISHED,
    MSG_PROGRESS,
    MSG_PROJECT_SUBMIT,
    ProtocolError,
    recv_json,
    recv_packet,
    send_json,
    send_packet,
)
from common.utils import calculate_sha256, format_bytes

logger = logging.getLogger("ClipchampClient")


class ClipchampNetworkClient:
    """Orchestrates asset sync, chunked offload execution, and download validation."""

    def __init__(self, base_network_client):
        self.client = base_network_client

    @property
    def sock(self):
        return self.client.sock

    @property
    def is_connected(self) -> bool:
        return self.client.is_connected

    def sync_assets(
        self,
        project: ClipchampProject,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> float:
        """
        Synchronize project assets with Host Worker node.
        Only uploads files that are not already present in the Host's asset cache.
        Returns total upload time in seconds.
        """
        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        def emit(prog: Dict[str, Any]):
            if progress_callback:
                progress_callback(prog)

        assets = project.get_required_assets()
        if not assets:
            return 0.0

        log(f"[CLIENT] Checking Host GPU cache for {len(assets)} project asset(s)...")
        emit({"stage": "Checking Remote Asset Cache", "percent": 0.0, "details": f"Querying {len(assets)} assets..."})

        # Query Host cache
        send_json(self.sock, MSG_ASSET_CHECK_REQ, {"assets": assets})
        msg_type, _, resp = recv_json(self.sock)
        if msg_type == MSG_ERROR:
            raise RuntimeError(f"Host rejected asset check: {resp.get('error')}")

        existing = set(resp.get("existing", []))
        missing_assets = [a for a in assets if a["sha256"] not in existing]

        log(f"[CLIENT] Host Asset Cache: {len(existing)} cached, {len(missing_assets)} need upload.")

        if not missing_assets:
            log("[CLIENT] [CACHE] All assets already cached on Host! Zero network upload needed!")
            emit({"stage": "Assets Synchronized", "percent": 100.0, "details": "All assets cached on Host."})
            return 0.0

        # Upload missing assets
        total_upload_bytes = sum(a["size_bytes"] for a in missing_assets)
        uploaded_bytes_total = 0
        start_t = time.time()

        for idx, asset in enumerate(missing_assets):
            p = Path(asset["local_path"])
            fname = asset["filename"]
            fsize = asset["size_bytes"]
            sha = asset["sha256"]

            log(f"[CLIENT] Uploading asset {idx + 1}/{len(missing_assets)}: '{fname}' ({format_bytes(fsize)})...")
            send_json(self.sock, MSG_ASSET_UPLOAD_START, {
                "filename": fname,
                "filesize": fsize,
                "sha256": sha,
            })

            m_type, _, ack = recv_json(self.sock)
            if m_type == MSG_ERROR:
                raise RuntimeError(f"Server rejected asset upload: {ack.get('error')}")

            with open(p, "rb") as f:
                sent = 0
                while sent < fsize:
                    if self.client.cancel_requested:
                        raise RuntimeError("Upload cancelled by user.")
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    send_packet(self.sock, MSG_FILE_CHUNK, chunk)
                    sent += len(chunk)
                    uploaded_bytes_total += len(chunk)

                    pct = round((uploaded_bytes_total / total_upload_bytes) * 100.0, 1)
                    emit({
                        "stage": f"Uploading Asset {idx + 1}/{len(missing_assets)}",
                        "percent": pct,
                        "details": f"{format_bytes(uploaded_bytes_total)} / {format_bytes(total_upload_bytes)}",
                    })

            send_json(self.sock, MSG_FILE_COMPLETE, {"sha256": sha})

            m_type, _, file_ack = recv_json(self.sock)
            if m_type == MSG_ERROR or file_ack.get("status") != "ok":
                raise RuntimeError(f"Failed to verify asset '{fname}' upload: {file_ack.get('error')}")

            log(f"[CLIENT] Asset '{fname}' verified on Host GPU!")

        upload_time = time.time() - start_t
        avg_speed = (total_upload_bytes / (1024 * 1024)) / max(0.001, upload_time)
        log(f"[CLIENT] All assets uploaded in {upload_time:.2f}s ({avg_speed:.2f} MB/s)")
        return upload_time

    def offload_project(
        self,
        project: ClipchampProject,
        output_dir: Path = CLIENT_OUTPUT_DIR,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute full Clipchamp project offload with Host GPU chunked rendering:
        1. Sync media assets (deduplication & selective upload).
        2. Submit project JSON manifest.
        3. Stream real-time per-chunk rendering progress from Host GPU.
        4. Download concatenated master video.
        5. Verify output checksum.
        """
        if not self.is_connected or not self.sock:
            raise ConnectionError("Not connected to Host GPU Worker.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        def emit(prog: Dict[str, Any]):
            if progress_callback:
                progress_callback(prog)

        log(f"[CLIENT] Initiating Host GPU Export for '{project.project_name}'...")

        # -------------------------------------------------------------
        # Phase 1: Asset Synchronization & Deduplication
        # -------------------------------------------------------------
        upload_duration = self.sync_assets(project, progress_callback, log_callback)

        # -------------------------------------------------------------
        # Phase 2: Submit Project Manifest
        # -------------------------------------------------------------
        emit({"stage": "Submitting Project Manifest", "percent": 0.0, "details": "Registering composition with Host GPU..."})
        proj_dict = project.to_dict()
        send_json(self.sock, MSG_PROJECT_SUBMIT, proj_dict)

        msg_type, _, job_ack = recv_json(self.sock)
        if msg_type == MSG_ERROR:
            raise RuntimeError(f"Host rejected project: {job_ack.get('error')}")
        if msg_type != MSG_JOB_ACCEPTED:
            raise ProtocolError(f"Unexpected response to project submit: {msg_type}")

        job_id = job_ack.get("job_id")
        log(f"[CLIENT] Project accepted by Host as ID: {job_id}")

        # -------------------------------------------------------------
        # Phase 3: Stream Chunked GPU Transcoding Progress
        # -------------------------------------------------------------
        log(f"[CLIENT] Host GPU executing chunked video rendering...")
        compute_start_time = time.time()
        job_result_meta = None

        while True:
            if self.client.cancel_requested:
                self.client.request_cancel()
                raise RuntimeError("Export cancelled by user.")

            msg_type, flags, payload = recv_packet(self.sock)

            if msg_type == MSG_CHUNK_PROGRESS or msg_type == MSG_PROGRESS:
                try:
                    prog_info = json.loads(payload.decode("utf-8"))
                    if "log_line" in prog_info:
                        log(prog_info["log_line"])
                    else:
                        emit(prog_info)
                except Exception:
                    pass

            elif msg_type == MSG_JOB_FINISHED:
                job_result_meta = json.loads(payload.decode("utf-8"))
                break

            elif msg_type == MSG_ERROR:
                err = json.loads(payload.decode("utf-8")) if payload else {}
                raise RuntimeError(f"Host GPU execution error: {err.get('error')}")

        compute_duration = time.time() - compute_start_time
        log(f"[CLIENT] Host GPU rendering completed in {compute_duration:.2f}s! ({job_result_meta.get('chunks_rendered', 1)} chunks)")

        # -------------------------------------------------------------
        # Phase 4: Download Assembled Master Output Video
        # -------------------------------------------------------------
        emit({"stage": "Downloading Master Render", "percent": 0.0, "details": "Requesting assembled master video..."})
        send_json(self.sock, MSG_DOWNLOAD_REQ, {"job_id": job_id})

        msg_type, _, dl_meta = recv_json(self.sock)
        if msg_type == MSG_ERROR:
            raise RuntimeError(f"Host download error: {dl_meta.get('error')}")
        if msg_type != MSG_DOWNLOAD_START:
            raise ProtocolError(f"Expected DOWNLOAD_START, got {msg_type}")

        out_fname = dl_meta.get("filename", "clipchamp_master.mp4")
        expected_size = int(dl_meta.get("filesize", 0))
        expected_sha = dl_meta.get("sha256", "")
        dest_path = output_dir / out_fname

        log(f"[CLIENT] Receiving {format_bytes(expected_size)} from Host -> {dest_path.name}...")
        dl_start_time = time.time()
        received_bytes = 0
        hasher = hashlib.sha256()

        with open(dest_path, "wb") as f:
            while received_bytes < expected_size:
                if self.client.cancel_requested:
                    raise RuntimeError("Download cancelled by user.")
                m_type, _, chunk = recv_packet(self.sock)
                if m_type == MSG_FILE_CHUNK:
                    f.write(chunk)
                    hasher.update(chunk)
                    received_bytes += len(chunk)

                    pct = round((received_bytes / expected_size) * 100.0, 1)
                    now = time.time()
                    elapsed = max(0.001, now - dl_start_time)
                    dl_mbps = (received_bytes / (1024 * 1024)) / elapsed
                    emit({
                        "stage": "Downloading Master Render",
                        "percent": pct,
                        "details": f"{format_bytes(received_bytes)} / {format_bytes(expected_size)} ({dl_mbps:.2f} MB/s)",
                        "download_speed_mbps": round(dl_mbps, 2),
                    })
                elif m_type == MSG_FILE_COMPLETE:
                    break

        # Consume trailing complete if needed
        if m_type != MSG_FILE_COMPLETE and received_bytes >= expected_size:
            m_type, _, _ = recv_packet(self.sock)

        download_duration = time.time() - dl_start_time
        avg_dl_mbps = (expected_size / (1024 * 1024)) / max(0.001, download_duration)
        log(f"[CLIENT] Download completed in {download_duration:.2f}s ({avg_dl_mbps:.2f} MB/s)")

        # -------------------------------------------------------------
        # Phase 5: Cryptographic Integrity Verification
        # -------------------------------------------------------------
        emit({"stage": "Verifying Output Integrity", "percent": 99.0, "details": "Verifying SHA-256..."})
        downloaded_sha = hasher.hexdigest()
        if downloaded_sha.lower() != expected_sha.lower():
            if dest_path.exists():
                dest_path.unlink()
            raise RuntimeError(f"Output checksum mismatch! Expected: {expected_sha}, Got: {downloaded_sha}")

        send_json(self.sock, MSG_FILE_ACK, {"status": "ok", "message": "Master video verified."})
        log(f"[CLIENT] Output SHA-256 checksum validated: MATCH! [OK]")

        total_offload_time = upload_duration + compute_duration + download_duration
        emit({
            "stage": "Offload Completed",
            "percent": 100.0,
            "details": f"Total export time: {total_offload_time:.2f}s",
        })

        return {
            "status": "success",
            "project_name": project.project_name,
            "output_file": str(dest_path.resolve()),
            "output_size_bytes": expected_size,
            "upload_duration_seconds": round(upload_duration, 2),
            "compute_duration_seconds": round(compute_duration, 2),
            "download_duration_seconds": round(download_duration, 2),
            "total_offload_seconds": round(total_offload_time, 2),
            "chunks_rendered": job_result_meta.get("chunks_rendered", 1),
            "gpu_name": job_result_meta.get("gpu_name", "Host GPU"),
            "encoder_used": job_result_meta.get("encoder_used", "Unknown"),
            "sha256": downloaded_sha,
            "sha256_verified": True,
        }
