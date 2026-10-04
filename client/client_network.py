"""
Client Network Interface for Distributed GPU Offloading.
Handles connection handshake, latency pinging, chunked streaming, checksums, and recovery.
Course: CSC-334 Parallel and Distributed Computing
"""

import hashlib
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import (
    CHUNK_SIZE,
    CLIENT_OUTPUT_DIR,
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    PING_TIMEOUT,
    SOCKET_TIMEOUT,
)
from common.protocol import (
    ConnectionClosedError,
    MSG_CANCEL,
    MSG_DOWNLOAD_REQ,
    MSG_DOWNLOAD_START,
    MSG_ERROR,
    MSG_FILE_ACK,
    MSG_FILE_CHUNK,
    MSG_FILE_COMPLETE,
    MSG_HANDSHAKE_REQ,
    MSG_HANDSHAKE_RESP,
    MSG_JOB_ACCEPTED,
    MSG_JOB_FINISHED,
    MSG_JOB_SUBMIT,
    MSG_PING,
    MSG_PONG,
    MSG_PROGRESS,
    ProtocolError,
    recv_json,
    recv_packet,
    send_json,
    send_packet,
)
from common.utils import calculate_sha256, format_bytes

logger = logging.getLogger("ClientNetwork")


class NetworkClient:
    """Manages socket communication and data offloading to remote GPU worker daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.is_connected = False
        self.last_latency_ms = 0.0
        self.worker_info: Dict[str, Any] = {}
        self.cancel_requested = False

    def connect(self, timeout: float = CONNECT_TIMEOUT) -> bool:
        """Establish TCP connection with worker node."""
        self.close()
        self.cancel_requested = False
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(SOCKET_TIMEOUT)
            self.is_connected = True
            logger.info(f"Connected to GPU Worker at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.is_connected = False
            self.sock = None
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            raise ConnectionError(f"Could not connect to worker at {self.host}:{self.port} - {e}")

    def close(self) -> None:
        """Close socket connection."""
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def request_cancel(self) -> None:
        """Request immediate job cancellation."""
        self.cancel_requested = True
        if self.sock and self.is_connected:
            try:
                send_packet(self.sock, MSG_CANCEL, b"")
            except Exception:
                pass

    def ping(self, timeout: float = PING_TIMEOUT) -> float:
        """
        Perform round-trip latency ping check.
        Returns: round-trip latency in milliseconds.
        """
        if not self.is_connected or not self.sock:
            raise ConnectionError("Not connected to worker node.")

        orig_timeout = self.sock.gettimeout()
        self.sock.settimeout(timeout)
        try:
            start_t = time.perf_counter()
            send_json(self.sock, MSG_PING, {"send_time": time.time()})
            msg_type, flags, payload = recv_packet(self.sock)
            rtt_ms = (time.perf_counter() - start_t) * 1000.0

            if msg_type != MSG_PONG:
                raise ProtocolError(f"Expected PONG response, received msg_type {msg_type}")

            self.last_latency_ms = round(rtt_ms, 2)
            return self.last_latency_ms
        finally:
            if self.sock:
                self.sock.settimeout(orig_timeout)

    def handshake(self) -> Dict[str, Any]:
        """
        Execute handshake protocol with worker daemon to retrieve GPU status & capabilities.
        """
        if not self.is_connected or not self.sock:
            raise ConnectionError("Not connected to worker node.")

        client_meta = {
            "client_name": socket.gethostname(),
            "client_os": os.name,
            "timestamp": time.time(),
        }
        send_json(self.sock, MSG_HANDSHAKE_REQ, client_meta)
        msg_type, flags, data = recv_json(self.sock)

        if msg_type == MSG_ERROR:
            raise ProtocolError(f"Worker rejected handshake: {data.get('error')}")
        if msg_type != MSG_HANDSHAKE_RESP:
            raise ProtocolError(f"Unexpected handshake response type: {msg_type}")

        self.worker_info = data
        return data

    def offload_task(
        self,
        input_file: Path,
        config: Dict[str, Any],
        output_dir: Path = CLIENT_OUTPUT_DIR,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full distributed offloading lifecycle:
        1. Checksum input asset.
        2. Submit job configuration.
        3. Upload media in chunks over LAN/Wi-Fi.
        4. Receive streaming transcode progress from worker GPU.
        5. Download rendered output file.
        6. Validate output checksum.
        Returns: Performance and offload summary metrics dictionary.
        """
        if not self.is_connected or not self.sock:
            raise ConnectionError("Not connected to worker node.")

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

        file_size = os.path.getsize(input_file)
        log(f"[CLIENT] Commencing offload for: {input_file.name} ({format_bytes(file_size)})")

        # -------------------------------------------------------------
        # Phase 1: Local Integrity Hashing (SHA-256)
        # -------------------------------------------------------------
        emit_progress({"stage": "Hashing Input", "percent": 0.0, "details": "Computing SHA-256..."})
        log(f"[CLIENT] Calculating local SHA-256 checksum for {input_file.name}...")

        def on_hash_progress(read_bytes: int, total_bytes: int):
            pct = round((read_bytes / total_bytes) * 100.0, 1)
            emit_progress({"stage": "Hashing Input", "percent": pct, "details": f"{format_bytes(read_bytes)} / {format_bytes(total_bytes)}"})

        input_sha256 = calculate_sha256(input_file, on_hash_progress)
        log(f"[CLIENT] Input SHA-256: {input_sha256[:16]}...")

        # -------------------------------------------------------------
        # Phase 2: Submit Job Specification
        # -------------------------------------------------------------
        emit_progress({"stage": "Submitting Job", "percent": 0.0, "details": "Registering with remote worker..."})
        job_spec = {
            "filename": input_file.name,
            "filesize": file_size,
            "sha256": input_sha256,
            "config": config,
        }
        send_json(self.sock, MSG_JOB_SUBMIT, job_spec)

        msg_type, _, ack_data = recv_json(self.sock)
        if msg_type == MSG_ERROR:
            raise RuntimeError(f"Server rejected job: {ack_data.get('error')}")
        if msg_type != MSG_JOB_ACCEPTED:
            raise ProtocolError(f"Unexpected response to job submit: {msg_type}")

        job_id = ack_data.get("job_id")
        log(f"[CLIENT] Job accepted by worker as ID: {job_id}")

        # -------------------------------------------------------------
        # Phase 3: Upload Binary Media File
        # -------------------------------------------------------------
        emit_progress({"stage": "Uploading to Worker", "percent": 0.0, "details": "Initiating network transfer..."})
        log(f"[CLIENT] Uploading {format_bytes(file_size)} to worker...")

        upload_start_time = time.time()
        bytes_sent = 0

        with open(input_file, "rb") as f:
            while bytes_sent < file_size:
                if self.cancel_requested:
                    self.request_cancel()
                    raise RuntimeError("Offload cancelled by user during upload.")

                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                send_packet(self.sock, MSG_FILE_CHUNK, chunk)
                bytes_sent += len(chunk)

                now = time.time()
                elapsed = max(0.001, now - upload_start_time)
                speed_mbps = (bytes_sent / (1024 * 1024)) / elapsed
                pct = round((bytes_sent / file_size) * 100.0, 1)

                emit_progress({
                    "stage": "Uploading to Worker",
                    "percent": pct,
                    "details": f"{format_bytes(bytes_sent)} / {format_bytes(file_size)} ({speed_mbps:.2f} MB/s)",
                    "upload_speed_mbps": round(speed_mbps, 2),
                })

        send_json(self.sock, MSG_FILE_COMPLETE, {"sha256": input_sha256})
        upload_duration = time.time() - upload_start_time
        avg_upload_mbps = (file_size / (1024 * 1024)) / max(0.001, upload_duration)
        log(f"[CLIENT] Upload completed in {upload_duration:.2f}s ({avg_upload_mbps:.2f} MB/s)")

        # Verify upload ack from server
        msg_type, _, file_ack = recv_json(self.sock)
        if msg_type == MSG_ERROR or file_ack.get("status") != "ok":
            raise RuntimeError(f"Server reported file upload verification failed: {file_ack.get('error')}")

        log(f"[CLIENT] Server verified input file integrity: SHA-256 match!")

        # -------------------------------------------------------------
        # Phase 4: Await Remote GPU Transcoding & Stream Live Progress
        # -------------------------------------------------------------
        log(f"[CLIENT] Remote GPU Worker executing hardware transcoding...")
        emit_progress({"stage": "Remote GPU Transcoding", "percent": 0.0, "details": "Worker starting render engine..."})

        compute_start_time = time.time()
        job_result_meta = None

        while True:
            if self.cancel_requested:
                self.request_cancel()
                raise RuntimeError("Offload cancelled by user during GPU processing.")

            msg_type, flags, payload = recv_packet(self.sock)

            if msg_type == MSG_PROGRESS:
                try:
                    prog_info = json.loads(payload.decode("utf-8"))
                    if "log_line" in prog_info:
                        log(prog_info["log_line"])
                    else:
                        prog_info["stage"] = "Remote GPU Transcoding"
                        emit_progress(prog_info)
                except Exception:
                    pass

            elif msg_type == MSG_JOB_FINISHED:
                job_result_meta = json.loads(payload.decode("utf-8"))
                break

            elif msg_type == MSG_ERROR:
                err_data = json.loads(payload.decode("utf-8")) if payload else {}
                raise RuntimeError(f"Remote worker encountered an execution error: {err_data.get('error')}")

            elif msg_type == MSG_PONG:
                continue

            else:
                logger.warning(f"Unexpected packet during transcode wait: {msg_type}")

        compute_duration = time.time() - compute_start_time
        log(f"[CLIENT] Remote GPU transcoding complete in {compute_duration:.2f}s!")
        log(f"[CLIENT] Encoder used: {job_result_meta.get('encoder_used')} | Output: {job_result_meta.get('output_filename')}")

        # -------------------------------------------------------------
        # Phase 5: Download Rendered Output File
        # -------------------------------------------------------------
        emit_progress({"stage": "Downloading Rendered Output", "percent": 0.0, "details": "Requesting output stream..."})
        send_json(self.sock, MSG_DOWNLOAD_REQ, {"job_id": job_id})

        msg_type, _, dl_meta = recv_json(self.sock)
        if msg_type == MSG_ERROR:
            raise RuntimeError(f"Server download error: {dl_meta.get('error')}")
        if msg_type != MSG_DOWNLOAD_START:
            raise ProtocolError(f"Expected DOWNLOAD_START, got {msg_type}")

        out_filename = dl_meta.get("filename", "output.mp4")
        expected_out_size = int(dl_meta.get("filesize", 0))
        expected_out_sha256 = dl_meta.get("sha256", "")
        dest_path = output_dir / out_filename

        log(f"[CLIENT] Receiving {format_bytes(expected_out_size)} from worker -> {dest_path.name}...")

        download_start_time = time.time()
        received_bytes = 0
        hasher = hashlib.sha256()

        with open(dest_path, "wb") as f:
            while received_bytes < expected_out_size:
                if self.cancel_requested:
                    self.request_cancel()
                    raise RuntimeError("Download cancelled by user.")

                m_type, _, chunk = recv_packet(self.sock)
                if m_type == MSG_FILE_CHUNK:
                    f.write(chunk)
                    hasher.update(chunk)
                    received_bytes += len(chunk)

                    now = time.time()
                    elapsed = max(0.001, now - download_start_time)
                    dl_speed_mbps = (received_bytes / (1024 * 1024)) / elapsed
                    pct = round((received_bytes / expected_out_size) * 100.0, 1)

                    emit_progress({
                        "stage": "Downloading Rendered Output",
                        "percent": pct,
                        "details": f"{format_bytes(received_bytes)} / {format_bytes(expected_out_size)} ({dl_speed_mbps:.2f} MB/s)",
                        "download_speed_mbps": round(dl_speed_mbps, 2),
                    })
                elif m_type == MSG_FILE_COMPLETE:
                    break

        # Consume trailing MSG_FILE_COMPLETE if not reached inside loop
        if not self.cancel_requested and m_type != MSG_FILE_COMPLETE:
            m_type, _, _ = recv_packet(self.sock)

        download_duration = time.time() - download_start_time
        avg_dl_mbps = (expected_out_size / (1024 * 1024)) / max(0.001, download_duration)
        log(f"[CLIENT] Download complete in {download_duration:.2f}s ({avg_dl_mbps:.2f} MB/s)")

        # -------------------------------------------------------------
        # Phase 6: Verify Download Integrity
        # -------------------------------------------------------------
        emit_progress({"stage": "Verifying Output Integrity", "percent": 99.0, "details": "Verifying SHA-256..."})
        downloaded_sha256 = hasher.hexdigest()

        if downloaded_sha256.lower() != expected_out_sha256.lower():
            if dest_path.exists():
                dest_path.unlink()
            raise RuntimeError(f"Output checksum mismatch! Expected {expected_out_sha256}, got {downloaded_sha256}")

        # Acknowledge receipt to worker
        send_json(self.sock, MSG_FILE_ACK, {"status": "ok", "message": "Download verified successfully."})
        log(f"[CLIENT] Output SHA-256 checksum matched successfully!")

        total_offload_duration = upload_duration + compute_duration + download_duration

        emit_progress({
            "stage": "Offload Completed",
            "percent": 100.0,
            "details": f"Total time: {total_offload_duration:.2f}s",
        })

        summary: Dict[str, Any] = {
            "status": "success",
            "input_file": str(input_file),
            "output_file": str(dest_path),
            "input_size_bytes": file_size,
            "output_size_bytes": expected_out_size,
            "upload_duration_seconds": round(upload_duration, 2),
            "compute_duration_seconds": round(compute_duration, 2),
            "download_duration_seconds": round(download_duration, 2),
            "total_offload_seconds": round(total_offload_duration, 2),
            "upload_speed_mbps": round(avg_upload_mbps, 2),
            "download_speed_mbps": round(avg_dl_mbps, 2),
            "network_overhead_seconds": round(upload_duration + download_duration, 2),
            "network_overhead_pct": round(((upload_duration + download_duration) / total_offload_duration) * 100.0, 1),
            "gpu_name": self.worker_info.get("gpu_telemetry", {}).get("gpu_name", "Remote GPU"),
            "encoder_used": job_result_meta.get("encoder_used", "Unknown"),
            "sha256_verified": True,
        }

        return summary
