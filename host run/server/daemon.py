"""
Remote GPU Execution Engine Daemon.
Background service accepting render & compute jobs with real-time socket progress streaming.
Course: CSC-334 Parallel and Distributed Computing
"""

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import (
    CHUNK_SIZE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SERVER_WORKDIR,
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
from common.utils import calculate_sha256, format_bytes, get_all_interfaces, get_local_ip
from server.execution_engine import ExecutionEngine
from server.gpu_detector import GPUDetector
from server.task_queue import JobRecord, JobStatus, TaskQueueManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("GPUDaemon")


class WorkerDaemon:
    """Headless background daemon executing GPU-accelerated transcoding tasks."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        workdir: Path = SERVER_WORKDIR,
        max_concurrent: int = 1,
        allow_cpu_fallback: bool = True,
    ):
        self.host = host
        self.port = port
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.allow_cpu_fallback = allow_cpu_fallback
        self.task_queue = TaskQueueManager(max_concurrent=max_concurrent)
        self.execution_engine = ExecutionEngine(allow_cpu_fallback=allow_cpu_fallback)

        self.server_socket: Optional[socket.socket] = None
        self.is_running = False
        self.active_threads = []
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for offloading clients."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            self.is_running = True
        except Exception as e:
            logger.error(f"Failed to bind daemon on {self.host}:{self.port} - {e}")
            raise

        local_ip = get_local_ip()
        interfaces = get_all_interfaces()

        logger.info("=" * 68)
        logger.info("       DISTRIBUTED GPU OFFLOADING WORKER DAEMON (CSC-334)")
        logger.info("=" * 68)
        logger.info(f"[*] Worker Daemon Status   : ONLINE")
        logger.info(f"[*] Bound Address          : {self.host}:{self.port}")
        logger.info(f"[*] Primary IP             : {local_ip}")
        for iface in interfaces:
            logger.info(f"    - Interface Address    : {iface['ip']}")
        logger.info(f"[*] Workspace Directory    : {self.workdir.resolve()}")
        logger.info(f"[*] Max Concurrent Jobs    : {self.task_queue.max_concurrent}")
        logger.info(f"[*] Allow Fallback Encoder : {self.allow_cpu_fallback}")

        # Probe hardware status on launch
        caps = GPUDetector.get_worker_capabilities()
        logger.info(f"[*] Detected GPU           : {caps['gpu_name']} ({caps['vram_total_mb']} MB VRAM)")
        logger.info(f"[*] Driver / CUDA Version  : Driver {caps['driver_version']} | CUDA {caps['cuda_version']}")
        logger.info(f"[*] NVENC Operational      : {caps['nvenc_operational']} ({caps['nvenc_status_message']})")
        logger.info(f"[*] Preferred Encoder      : {caps['preferred_gpu_encoder']}")
        logger.info("=" * 68)
        logger.info("[*] Awaiting client offload requests...")

        try:
            while self.is_running:
                try:
                    client_sock, client_addr = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                logger.info(f"[+] Inbound client connection accepted from: {client_addr[0]}:{client_addr[1]}")
                # Spawn worker thread for each connected client
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    daemon=True,
                )
                t.start()
                with self._lock:
                    self.active_threads.append(t)
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully shut down the daemon."""
        if not self.is_running:
            return
        self.is_running = False
        logger.info("[*] Shutting down GPU Daemon...")
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple) -> None:
        """Handle individual client session lifecycle."""
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_sock.settimeout(SOCKET_TIMEOUT)
        addr_str = f"{client_addr[0]}:{client_addr[1]}"

        current_job: Optional[JobRecord] = None

        try:
            while self.is_running:
                try:
                    msg_type, flags, payload = recv_packet(client_sock)
                except (ConnectionClosedError, socket.timeout, ConnectionResetError, ConnectionAbortedError):
                    logger.info(f"[-] Client {addr_str} disconnected gracefully.")
                    break

                # 1. Latency Ping Handshake Check
                if msg_type == MSG_PING:
                    try:
                        import json
                        ping_data = json.loads(payload.decode("utf-8")) if payload else {}
                    except Exception:
                        ping_data = {}
                    # Reply immediately with PONG and current server epoch
                    pong_data = {
                        "client_send_time": ping_data.get("send_time", time.time()),
                        "server_time": time.time(),
                        "queue_depth": self.task_queue.get_queue_stats()["queued_jobs_count"],
                    }
                    send_json(client_sock, MSG_PONG, pong_data)

                # 2. Connection Handshake Protocol
                elif msg_type == MSG_HANDSHAKE_REQ:
                    logger.info(f"[*] Processing handshake request from {addr_str}")
                    caps = GPUDetector.get_worker_capabilities()
                    queue_stats = self.task_queue.get_queue_stats()
                    response = {
                        "status": "ready",
                        "server_version": "1.0.0",
                        "worker_name": socket.gethostname(),
                        "gpu_telemetry": caps,
                        "queue_stats": queue_stats,
                        "allow_cpu_fallback": self.allow_cpu_fallback,
                    }
                    send_json(client_sock, MSG_HANDSHAKE_RESP, response)
                    logger.info(f"[+] Handshake completed for {addr_str} (GPU: {caps['gpu_name']})")

                # 3. Job Submission
                elif msg_type == MSG_JOB_SUBMIT:
                    import json
                    job_spec = json.loads(payload.decode("utf-8"))
                    filename = os.path.basename(job_spec.get("filename", "input.mp4"))
                    filesize = int(job_spec.get("filesize", 0))
                    expected_sha256 = job_spec.get("sha256", "")
                    config = job_spec.get("config", {})

                    logger.info(f"[JOB] Received job submission for file '{filename}' ({format_bytes(filesize)})")
                    current_job = self.task_queue.create_job(
                        client_addr=addr_str,
                        config=config,
                        input_filename=filename,
                        input_filesize=filesize,
                        input_sha256=expected_sha256,
                    )
                    # Accept job and invite file upload
                    send_json(client_sock, MSG_JOB_ACCEPTED, {
                        "job_id": current_job.job_id,
                        "message": "Ready to receive media asset.",
                    })

                # 4. Inbound Media File Transfer
                elif msg_type == MSG_FILE_CHUNK:
                    if not current_job:
                        send_json(client_sock, MSG_ERROR, {"error": "No active job context for file transfer."})
                        continue

                    # Stream file upload into server workspace
                    temp_input = self.workdir / f"{current_job.job_id}_{current_job.input_filename}"
                    import hashlib
                    hasher = hashlib.sha256()
                    received_bytes = len(payload)
                    hasher.update(payload)

                    with open(temp_input, "wb") as f:
                        f.write(payload)
                        while received_bytes < current_job.input_filesize:
                            m_type, _, chunk = recv_packet(client_sock)
                            if m_type == MSG_CANCEL:
                                current_job.cancel_requested = True
                                break
                            if m_type == MSG_FILE_CHUNK:
                                f.write(chunk)
                                hasher.update(chunk)
                                received_bytes += len(chunk)
                            elif m_type == MSG_FILE_COMPLETE:
                                break

                    # Consume trailing MSG_FILE_COMPLETE if upload reached size before packet
                    if not current_job.cancel_requested and m_type != MSG_FILE_COMPLETE:
                        m_type, _, _ = recv_packet(client_sock)

                    if current_job.cancel_requested:
                        logger.info(f"[JOB] Transfer cancelled for job {current_job.job_id}")
                        if temp_input.exists():
                            temp_input.unlink()
                        continue

                    computed_sha256 = hasher.hexdigest()
                    logger.info(f"[JOB] Upload finished: {format_bytes(received_bytes)} | "
                                f"Expected: {current_job.input_sha256[:10]}... | Computed: {computed_sha256[:10]}...")

                    if computed_sha256.lower() != current_job.input_sha256.lower():
                        logger.error(f"[JOB] Checksum validation FAILED for {current_job.job_id}!")
                        send_json(client_sock, MSG_FILE_ACK, {
                            "status": "error",
                            "error": "Checksum validation failed: input file corrupted in transit.",
                        })
                        if temp_input.exists():
                            temp_input.unlink()
                        current_job = None
                        continue

                    # Checksum validated successfully
                    send_json(client_sock, MSG_FILE_ACK, {
                        "status": "ok",
                        "message": "File integrity verified (SHA-256 match).",
                    })

                    # Mark job ready in task queue
                    self.task_queue.mark_ready_for_processing(current_job.job_id, temp_input)

                    # Trigger GPU Transcoding Pipeline with live progress streaming back to client
                    self._run_transcode_and_stream(client_sock, current_job)

                # 5. Output Download Request
                elif msg_type == MSG_DOWNLOAD_REQ:
                    if not current_job or not current_job.output_path or not current_job.output_path.exists():
                        send_json(client_sock, MSG_ERROR, {"error": "Rendered output file not found on worker."})
                        continue

                    out_path = current_job.output_path
                    out_size = os.path.getsize(out_path)
                    out_sha256 = current_job.output_sha256 or calculate_sha256(out_path)

                    logger.info(f"[DOWNLOAD] Streaming rendered file {out_path.name} ({format_bytes(out_size)}) to client...")
                    send_json(client_sock, MSG_DOWNLOAD_START, {
                        "filename": out_path.name,
                        "filesize": out_size,
                        "sha256": out_sha256,
                    })

                    # Stream binary chunks
                    with open(out_path, "rb") as f:
                        while True:
                            chunk = f.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            send_packet(client_sock, MSG_FILE_CHUNK, chunk)

                    send_json(client_sock, MSG_FILE_COMPLETE, {"sha256": out_sha256})
                    logger.info(f"[DOWNLOAD] Completed streaming output file to client {addr_str}")

                # 6. Cancellation Request
                elif msg_type == MSG_CANCEL:
                    if current_job:
                        logger.info(f"[CANCEL] Client requested cancellation of job {current_job.job_id}")
                        self.task_queue.cancel_job(current_job.job_id)

                elif msg_type == MSG_FILE_ACK:
                    logger.info(f"[ACK] Client acknowledged file receipt: {payload.decode('utf-8', errors='ignore')}")

        except Exception as e:
            logger.error(f"[ERROR] Exception in client session {addr_str}: {e}", exc_info=True)
            try:
                send_json(client_sock, MSG_ERROR, {"error": str(e)})
            except Exception:
                pass
        finally:
            if current_job and current_job.status == JobStatus.TRANSCODING:
                self.task_queue.cancel_job(current_job.job_id)
            try:
                client_sock.close()
            except Exception:
                pass

    def _run_transcode_and_stream(self, client_sock: socket.socket, job: JobRecord) -> None:
        """Run transcode and stream asynchronous progress frames over socket."""
        sock_lock = threading.Lock()

        def on_progress(stats: Dict[str, Any]) -> None:
            self.task_queue.update_progress(job.job_id, stats)
            with sock_lock:
                try:
                    send_json(client_sock, MSG_PROGRESS, stats)
                except Exception:
                    pass

        def on_log(msg: str) -> None:
            with sock_lock:
                try:
                    send_json(client_sock, MSG_PROGRESS, {"stage": "Log", "log_line": msg})
                except Exception:
                    pass

        # Dequeue and execute
        dispatched_job = self.task_queue.acquire_next_job()
        if not dispatched_job:
            # Wait for execution slot if queued
            on_progress({"stage": "Waiting in Queue for GPU Slot", "percent": 0.0})
            while self.is_running and not job.cancel_requested:
                dispatched_job = self.task_queue.acquire_next_job()
                if dispatched_job:
                    break
                time.sleep(0.5)

        if not dispatched_job or job.cancel_requested:
            return

        try:
            output_file = self.execution_engine.execute_transcode(
                job=job,
                output_dir=self.workdir,
                progress_callback=on_progress,
                log_callback=on_log,
            )
            self.task_queue.release_job(job.job_id, success=True)

            # Send completion notification
            with sock_lock:
                send_json(client_sock, MSG_JOB_FINISHED, {
                    "job_id": job.job_id,
                    "status": "success",
                    "execution_time_seconds": job.duration_seconds(),
                    "output_filename": job.output_filename,
                    "output_filesize": job.output_filesize,
                    "output_sha256": job.output_sha256,
                    "encoder_used": job.progress.get("encoder", "Unknown"),
                })
        except Exception as e:
            logger.error(f"[ENGINE] Execution error on job {job.job_id}: {e}")
            self.task_queue.release_job(job.job_id, success=False, error=str(e))
            with sock_lock:
                send_json(client_sock, MSG_ERROR, {
                    "job_id": job.job_id,
                    "error": str(e),
                })


def main():
    parser = argparse.ArgumentParser(description="Distributed GPU Offloading Daemon (CSC-334)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 5050)")
    parser.add_argument("--workdir", default=str(SERVER_WORKDIR), help="Server working directory")
    parser.add_argument("--max-workers", type=int, default=1, help="Max concurrent GPU transcode jobs (default: 1)")
    parser.add_argument("--no-fallback", action="store_true", help="Disallow CPU fallback if NVENC fails")
    args = parser.parse_args()

    daemon = WorkerDaemon(
        host=args.host,
        port=args.port,
        workdir=Path(args.workdir),
        max_concurrent=args.max_workers,
        allow_cpu_fallback=not args.no_fallback,
    )

    def handle_signal(sig, frame):
        logger.info(f"Signal {sig} received, stopping daemon...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    daemon.start()


if __name__ == "__main__":
    main()
