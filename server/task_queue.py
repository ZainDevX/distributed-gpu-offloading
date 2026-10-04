"""
Thread-safe Task Queue Manager for Distributed GPU Offloading.
Manages job lifecycle, prioritization, execution dispatch, and status tracking.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TaskQueue")


class JobStatus(str, Enum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    QUEUED = "QUEUED"
    TRANSCODING = "TRANSCODING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class JobRecord:
    job_id: str
    client_addr: str
    config: Dict[str, Any]
    input_filename: str
    input_filesize: int
    input_sha256: str
    input_path: Optional[Path] = None
    output_filename: Optional[str] = None
    output_path: Optional[Path] = None
    output_filesize: int = 0
    output_sha256: Optional[str] = None
    status: JobStatus = JobStatus.PENDING_UPLOAD
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error_message: Optional[str] = None
    progress: Dict[str, Any] = field(default_factory=lambda: {
        "stage": "Initialized",
        "percent": 0.0,
        "frame": 0,
        "fps": 0.0,
        "speed": "0.0x",
        "bitrate": "0k",
        "eta_seconds": 0.0,
    })
    cancel_requested: bool = False
    process_handle: Optional[Any] = None

    def duration_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end_t = self.finished_at or time.time()
        return max(0.0, end_t - self.started_at)


class TaskQueueManager:
    """Manages submitted compute jobs and coordinates worker concurrency."""

    def __init__(self, max_concurrent: int = 1):
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._jobs: Dict[str, JobRecord] = {}
        self._queue: List[str] = []  # List of job_ids waiting for processing
        self._active_jobs: Dict[str, JobRecord] = {}

    def create_job(self, client_addr: str, config: Dict[str, Any], input_filename: str,
                   input_filesize: int, input_sha256: str) -> JobRecord:
        """Create and register a new job in PENDING_UPLOAD status."""
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        job = JobRecord(
            job_id=job_id,
            client_addr=client_addr,
            config=config,
            input_filename=input_filename,
            input_filesize=input_filesize,
            input_sha256=input_sha256,
        )
        with self._lock:
            self._jobs[job_id] = job
        logger.info(f"Created job {job_id} for client {client_addr} (File: {input_filename}, {input_filesize} B)")
        return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Look up job record by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def mark_ready_for_processing(self, job_id: str, input_path: Path) -> bool:
        """Called once file upload and SHA-256 verification is complete."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.cancel_requested:
                return False
            job.input_path = input_path
            job.status = JobStatus.QUEUED
            self._queue.append(job_id)
            logger.info(f"Job {job_id} queued for execution. Queue length: {len(self._queue)}")
            return True

    def acquire_next_job(self) -> Optional[JobRecord]:
        """Atomically fetch next job from queue if under concurrency limit."""
        with self._lock:
            if len(self._active_jobs) >= self.max_concurrent:
                return None
            while self._queue:
                job_id = self._queue.pop(0)
                job = self._jobs.get(job_id)
                if job and not job.cancel_requested:
                    job.status = JobStatus.TRANSCODING
                    job.started_at = time.time()
                    self._active_jobs[job_id] = job
                    logger.info(f"Dispatched job {job_id} to GPU execution engine.")
                    return job
            return None

    def release_job(self, job_id: str, success: bool, error: Optional[str] = None) -> None:
        """Mark job finished and release worker slot."""
        with self._lock:
            job = self._active_jobs.pop(job_id, None) or self._jobs.get(job_id)
            if job:
                job.finished_at = time.time()
                if job.cancel_requested:
                    job.status = JobStatus.CANCELLED
                    job.error_message = "Cancelled by user"
                elif success:
                    job.status = JobStatus.COMPLETED
                else:
                    job.status = JobStatus.FAILED
                    job.error_message = error
                logger.info(f"Job {job_id} finished with status: {job.status.value} in {job.duration_seconds():.2f}s")

    def update_progress(self, job_id: str, progress_data: Dict[str, Any]) -> None:
        """Update live progress statistics for a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress.update(progress_data)

    def cancel_job(self, job_id: str) -> bool:
        """Request cancellation of a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            job.cancel_requested = True
            if job.process_handle:
                try:
                    job.process_handle.kill()
                except Exception:
                    pass
            if job_id in self._queue:
                self._queue.remove(job_id)
                job.status = JobStatus.CANCELLED
            logger.info(f"Job {job_id} cancelled.")
            return True

    def get_queue_stats(self) -> Dict[str, Any]:
        """Summary of queue state for telemetry."""
        with self._lock:
            return {
                "active_jobs_count": len(self._active_jobs),
                "queued_jobs_count": len(self._queue),
                "total_jobs_tracked": len(self._jobs),
            }
