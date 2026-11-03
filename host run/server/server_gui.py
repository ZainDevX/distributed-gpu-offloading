"""
Modern Desktop GUI Dashboard for Distributed GPU Offloading Host Server.
Provides full visual monitoring of remote GPU telemetry, task queues, connected clients,
and real-time render progress without needing any command-line interaction.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import messagebox
from typing import Any, Dict, List, Optional

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from common.config import DEFAULT_HOST, DEFAULT_PORT, SERVER_WORKDIR
from common.utils import format_bytes, get_all_interfaces, get_local_ip
from server.daemon import WorkerDaemon
from server.gpu_detector import GPUDetector

# Appearance configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger("HostServerGUI")


class HostServerGUI(ctk.CTk):
    """Modern Desktop GUI Server Manager for Host GPU Worker Node."""

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__()

        self.title("Host GPU Server Node Monitor — CSC-334")
        self.geometry("1120x820")
        self.minsize(980, 720)

        self.port = port
        self.daemon: Optional[WorkerDaemon] = None
        self.daemon_thread: Optional[threading.Thread] = None
        self.is_server_running = False

        # Metrics
        self.total_jobs_completed = 0
        self.total_chunks_processed = 0

        self._build_ui()
        self._start_telemetry_loop()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Log welcome message
        self.log("Host Server Node Dashboard initialized.")
        self.log("Click '▶ Start Server' or let auto-start begin listening for clients.")

    def _build_ui(self):
        # 1. Top Header Banner
        self.header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#181c24")
        self.header_frame.pack(fill="x", padx=16, pady=(12, 8))

        lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="⚡ DISTRIBUTED GPU HOST SERVER",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#38bdf8",
        )
        lbl_title.pack(side="left", padx=16, pady=10)

        lbl_subtitle = ctk.CTkLabel(
            self.header_frame,
            text="Worker Node Daemon & GPU Manager",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
        )
        lbl_subtitle.pack(side="left", padx=(0, 16), pady=10)

        # Server Status Badge
        self.lbl_server_status = ctk.CTkLabel(
            self.header_frame,
            text="● SERVER OFFLINE",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#f87171",
            fg_color="#331418",
            corner_radius=8,
            padx=14,
            pady=4,
        )
        self.lbl_server_status.pack(side="right", padx=16, pady=10)

        # 2. Main Scrollable Body
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=12, pady=4)

        # Section 1: Server Controls & Network Endpoints
        self._build_control_card()

        # Section 2: Live GPU Telemetry & VRAM Tracker
        self._build_gpu_telemetry_card()

        # Section 3: Active Job Queue & Progress Monitor
        self._build_queue_monitor_card()

        # Section 4: Workspace & Asset Cache Stats
        self._build_workspace_stats_card()

        # Section 5: Real-time Server Log Console
        self._build_console_card()

    def _build_control_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="1. SERVER DAEMON CONTROLS & NETWORK INTERFACES",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=14, pady=(10, 6))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(0, 8))

        # Port Input
        ctk.CTkLabel(row1, text="Listen Port:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.entry_port = ctk.CTkEntry(row1, width=80)
        self.entry_port.insert(0, str(self.port))
        self.entry_port.pack(side="left", padx=(0, 16))

        # Max Workers
        ctk.CTkLabel(row1, text="Concurrent Jobs:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.combo_workers = ctk.CTkComboBox(row1, values=["1 (Recommended for single GPU)", "2 (Multi-stream)", "4"], width=190)
        self.combo_workers.set("1 (Recommended for single GPU)")
        self.combo_workers.pack(side="left", padx=(0, 16))

        # Start / Stop Button
        self.btn_toggle_server = ctk.CTkButton(
            row1,
            text="▶ Start Server",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            width=150,
            command=self._toggle_server,
        )
        self.btn_toggle_server.pack(side="left", padx=(0, 16))

        # Network IPs Display
        ip_row = ctk.CTkFrame(card, fg_color="#141820", corner_radius=8)
        ip_row.pack(fill="x", padx=14, pady=(0, 10))

        primary_ip = get_local_ip()
        interfaces = get_all_interfaces()
        ip_list_str = " | ".join(f"{i['ip']}" for i in interfaces)

        self.lbl_ips = ctk.CTkLabel(
            ip_row,
            text=f"🌐 Primary IP: {primary_ip}  (Give this IP to Client Laptops)\n"
                 f"📡 Available Network Adapters: {ip_list_str}",
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left",
            text_color="#94a3b8",
        )
        self.lbl_ips.pack(side="left", padx=12, pady=8)

        btn_copy = ctk.CTkButton(
            ip_row,
            text="📋 Copy IP",
            width=90,
            height=28,
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: self._copy_ip(primary_ip),
        )
        btn_copy.pack(side="right", padx=12, pady=8)

    def _copy_ip(self, ip_str: str):
        self.clipboard_clear()
        self.clipboard_append(ip_str)
        messagebox.showinfo("Copied", f"Copied Host IP: {ip_str}\nEnter this IP on the Client Laptop.")

    def _build_gpu_telemetry_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="2. HOST GPU HARDWARE ACCELERATION & VRAM TELEMETRY",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=14, pady=(10, 6))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 10))

        # GPU Name & Driver
        col1 = ctk.CTkFrame(grid, fg_color="#141820", corner_radius=8)
        col1.pack(side="left", expand=True, fill="both", padx=(0, 6))
        self.lbl_gpu_name = ctk.CTkLabel(
            col1,
            text="GPU: Probing hardware...",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_gpu_name.pack(anchor="w", padx=12, pady=(8, 2))

        self.lbl_gpu_driver = ctk.CTkLabel(
            col1,
            text="Driver: -- | CUDA: --",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#94a3b8",
        )
        self.lbl_gpu_driver.pack(anchor="w", padx=12, pady=(0, 8))

        # VRAM Utilization Bar
        col2 = ctk.CTkFrame(grid, fg_color="#141820", corner_radius=8)
        col2.pack(side="left", expand=True, fill="both", padx=6)

        self.lbl_vram_title = ctk.CTkLabel(
            col2,
            text="VRAM Usage: -- MB / -- MB",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e2e8f0",
        )
        self.lbl_vram_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.pbar_vram = ctk.CTkProgressBar(col2, height=10, progress_color="#6366f1")
        self.pbar_vram.set(0.0)
        self.pbar_vram.pack(fill="x", padx=12, pady=(2, 8))

        # Hardware Encoder
        col3 = ctk.CTkFrame(grid, fg_color="#141820", corner_radius=8)
        col3.pack(side="left", expand=True, fill="both", padx=(6, 0))

        self.lbl_encoder = ctk.CTkLabel(
            col3,
            text="Active Encoder: --",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#34d399",
        )
        self.lbl_encoder.pack(anchor="w", padx=12, pady=(8, 2))

        self.lbl_encoder_desc = ctk.CTkLabel(
            col3,
            text="NVENC / MFT Hardware Acceleration",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#94a3b8",
        )
        self.lbl_encoder_desc.pack(anchor="w", padx=12, pady=(0, 8))

    def _build_queue_monitor_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="3. ACTIVE TASK QUEUE & WORKLOAD EXECUTION MONITOR",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=14, pady=(10, 6))

        # Active Job Info Box
        job_box = ctk.CTkFrame(card, fg_color="#141820", corner_radius=8)
        job_box.pack(fill="x", padx=14, pady=(0, 10))

        row_top = ctk.CTkFrame(job_box, fg_color="transparent")
        row_top.pack(fill="x", padx=12, pady=(8, 2))

        self.lbl_active_job = ctk.CTkLabel(
            row_top,
            text="Active Job: None (Awaiting client offload)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e2e8f0",
        )
        self.lbl_active_job.pack(side="left")

        self.lbl_job_stats = ctk.CTkLabel(
            row_top,
            text="Completed: 0 jobs | Chunks: 0",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#38bdf8",
        )
        self.lbl_job_stats.pack(side="right")

        # Progress bar
        self.pbar_job = ctk.CTkProgressBar(job_box, height=12, progress_color="#38bdf8")
        self.pbar_job.set(0.0)
        self.pbar_job.pack(fill="x", padx=12, pady=(4, 6))

        # Status & FPS row
        row_sub = ctk.CTkFrame(job_box, fg_color="transparent")
        row_sub.pack(fill="x", padx=12, pady=(0, 8))

        self.lbl_stage = ctk.CTkLabel(
            row_sub,
            text="Status: Idle",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        )
        self.lbl_stage.pack(side="left")

        self.lbl_fps_speed = ctk.CTkLabel(
            row_sub,
            text="FPS: 0 | Speed: 0.0x",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#a5b4fc",
        )
        self.lbl_fps_speed.pack(side="right")

    def _build_workspace_stats_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="4. SERVER WORKSPACE & ASSET DEDUPLICATION CACHE",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=14, pady=(10, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_cache_stats = ctk.CTkLabel(
            row,
            text="Workspace: server_workspace | Cached Assets: 0",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#94a3b8",
        )
        self.lbl_cache_stats.pack(side="left", padx=(0, 14))

        btn_open_ws = ctk.CTkButton(
            row,
            text="📂 Open Workspace",
            width=140,
            height=28,
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_workspace_folder,
        )
        btn_open_ws.pack(side="left", padx=4)

        btn_clear_cache = ctk.CTkButton(
            row,
            text="🧹 Clear Cache",
            width=110,
            height=28,
            fg_color="#334155",
            hover_color="#ef4444",
            command=self._clear_cache,
        )
        btn_clear_cache.pack(side="left", padx=4)

    def _build_console_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="5. REAL-TIME SERVER EVENT LOGS & SOCKET TRAFFIC",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=14, pady=(10, 6))

        self.txt_console = ctk.CTkTextbox(
            card,
            height=160,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#090b10",
            text_color="#cbd5e1",
        )
        self.txt_console.pack(fill="x", padx=14, pady=(0, 10))

    def log(self, msg: str):
        t_str = time.strftime("%H:%M:%S")
        self.after(0, lambda: self._append_log(f"[{t_str}] {msg}"))

    def _append_log(self, full_line: str):
        self.txt_console.insert("end", full_line + "\n")
        self.txt_console.see("end")

    # -------------------------------------------------------------
    # Server Lifecycle Management
    # -------------------------------------------------------------
    def _toggle_server(self):
        if self.is_server_running:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        try:
            port_val = int(self.entry_port.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be an integer (e.g. 5050)")
            return

        workers_str = self.combo_workers.get()
        max_w = 2 if "2" in workers_str else 4 if "4" in workers_str else 1

        self.daemon = WorkerDaemon(
            host=DEFAULT_HOST,
            port=port_val,
            workdir=SERVER_WORKDIR,
            max_concurrent=max_w,
            allow_cpu_fallback=True,
        )

        self.daemon_thread = threading.Thread(target=self._run_daemon_worker, daemon=True)
        self.daemon_thread.start()

        self.is_server_running = True
        self.btn_toggle_server.configure(text="⏹ Stop Server", fg_color="#ef4444", hover_color="#dc2626")
        self.lbl_server_status.configure(
            text=f"● SERVER ONLINE ({port_val})",
            text_color="#34d399",
            fg_color="#064e3b",
        )
        self.entry_port.configure(state="disabled")
        self.log(f"Host Worker Server started on port {port_val} (Max Workers: {max_w}).")

    def _run_daemon_worker(self):
        try:
            self.daemon.start()
        except Exception as e:
            self.log(f"Daemon error: {e}")
            self.after(0, self._stop_server)

    def _stop_server(self):
        if self.daemon:
            self.daemon.stop()
            self.daemon = None

        self.is_server_running = False
        self.btn_toggle_server.configure(text="▶ Start Server", fg_color="#059669", hover_color="#047857")
        self.lbl_server_status.configure(
            text="● SERVER OFFLINE",
            text_color="#f87171",
            fg_color="#331418",
        )
        self.entry_port.configure(state="normal")
        self.log("Host Worker Server stopped.")

    def _on_window_close(self):
        """Cleanly unbind sockets and stop worker daemon before exit."""
        if self.is_server_running:
            self._stop_server()
        self.destroy()

    # -------------------------------------------------------------
    # Periodic Telemetry & Queue Polling
    # -------------------------------------------------------------
    def _start_telemetry_loop(self):
        threading.Thread(target=self._telemetry_worker, daemon=True).start()

    def _telemetry_worker(self):
        while True:
            try:
                caps = GPUDetector.get_worker_capabilities()
                smi = caps.get("nvidia_smi", {})
                v_total = caps.get("vram_total_mb", 0)
                v_used = smi.get("vram_used_mb", 0)
                v_pct = (v_used / v_total) if v_total > 0 else 0.0

                gpu_name = caps.get("gpu_name", "None")
                driver = caps.get("driver_version", "N/A")
                cuda = caps.get("cuda_version", "N/A")
                pref_encoder = caps.get("preferred_gpu_encoder", "libx264")

                # Update UI
                self.after(0, lambda: self._update_telemetry_display(
                    gpu_name, driver, cuda, v_used, v_total, v_pct, pref_encoder
                ))

                # Update Queue Stats if server running
                if self.daemon and self.is_server_running:
                    stats = self.daemon.task_queue.get_queue_stats()
                    self.after(0, lambda: self._update_queue_display(stats))

                # Update Cache Stats
                self.after(0, self._update_cache_display)

            except Exception:
                pass
            time.sleep(1.5)

    def _update_telemetry_display(self, gpu_name, driver, cuda, v_used, v_total, v_pct, encoder):
        self.lbl_gpu_name.configure(text=f"GPU: {gpu_name}")
        self.lbl_gpu_driver.configure(text=f"Driver: {driver} | CUDA: {cuda}")
        self.lbl_vram_title.configure(text=f"VRAM Usage: {v_used} MB / {v_total} MB ({int(v_pct * 100)}%)")
        self.pbar_vram.set(v_pct)
        self.lbl_encoder.configure(text=f"Preferred Engine: {encoder}")

    def _update_queue_display(self, stats: Dict[str, Any]):
        active_list = stats.get("active_jobs", [])
        if active_list:
            job = active_list[0]
            prog = job.get("progress", {})
            pct = prog.get("total_percent", prog.get("percent", 0.0))
            stage = prog.get("stage", "Processing")
            fps = prog.get("fps", 0.0)
            speed = prog.get("speed", "1.0x")

            self.lbl_active_job.configure(text=f"Active Job: {job.get('job_id')} ({job.get('input_filename')})")
            self.pbar_job.set(pct / 100.0)
            self.lbl_stage.configure(text=f"Stage: {stage} ({pct:.1f}%)")
            self.lbl_fps_speed.configure(text=f"FPS: {fps} | Speed: {speed}")
        else:
            self.lbl_active_job.configure(text="Active Job: None (Awaiting client offload)")
            self.pbar_job.set(0.0)
            self.lbl_stage.configure(text="Status: Idle / Ready")
            self.lbl_fps_speed.configure(text="FPS: 0 | Speed: 0.0x")

        tot_completed = stats.get("completed_jobs_count", 0)
        self.lbl_job_stats.configure(text=f"Completed: {tot_completed} jobs")

    def _update_cache_display(self):
        cache_dir = SERVER_WORKDIR / "asset_cache"
        count = 0
        total_size = 0
        if cache_dir.exists():
            for f in cache_dir.glob("*"):
                if f.is_file():
                    count += 1
                    total_size += f.stat().st_size
        self.lbl_cache_stats.configure(
            text=f"Workspace: {SERVER_WORKDIR.name} | Cached Assets: {count} ({format_bytes(total_size)})"
        )

    def _open_workspace_folder(self):
        if SERVER_WORKDIR.exists():
            os.startfile(SERVER_WORKDIR)

    def _clear_cache(self):
        cache_dir = SERVER_WORKDIR / "asset_cache"
        if cache_dir.exists():
            for f in cache_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
            self.log("Asset deduplication cache cleared.")
            self._update_cache_display()


def main():
    app = HostServerGUI()
    # Auto-start server for 1-click convenience
    app.after(500, app._start_server)
    app.mainloop()


if __name__ == "__main__":
    main()

