"""
Modern Desktop GUI Application for Distributed GPU Offloading.
Built with CustomTkinter for sleek dark-mode aesthetics and responsive interaction.
Course: CSC-334 Parallel and Distributed Computing
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, Optional

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from client.client_network import NetworkClient
from client.local_engine import LocalBenchmarkEngine
from common.config import (
    BITRATE_PRESETS,
    CLIENT_OUTPUT_DIR,
    DEFAULT_CLIENT_TARGET,
    DEFAULT_PORT,
    RESOLUTIONS,
    TEST_MEDIA_DIR,
)
from common.utils import format_bytes, format_duration, probe_media_file
from scripts.generate_test_media import generate_synthetic_video

# Appearance configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger("ClientGUI")


class DistributedOffloadGUI(ctk.CTk):
    """Main Application Window for Distributed GPU Offloading System."""

    def __init__(self):
        super().__init__()

        self.title("Distributed GPU Offloading System — CSC-334")
        self.geometry("1180x880")
        self.minsize(1050, 780)

        # Network and execution clients
        self.network_client = NetworkClient()
        self.local_engine = LocalBenchmarkEngine()

        # State variables
        self.selected_file: Optional[Path] = None
        self.media_info: Dict[str, Any] = {}
        self.is_processing = False
        self.active_worker_thread: Optional[threading.Thread] = None

        # Benchmark comparison caches
        self.last_remote_result: Optional[Dict[str, Any]] = None
        self.last_local_result: Optional[Dict[str, Any]] = None

        # Build UI components
        self._build_ui()

        # Log greeting
        self.log_to_terminal("System initialized. Welcome to CSC-334 Distributed GPU Offloading Client.")
        self.log_to_terminal("Ready to connect to remote GPU worker daemon or run local benchmarks.")

    def _build_ui(self):
        """Construct the complete multi-card dashboard layout."""
        # Top Header Banner
        self.header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#181c24")
        self.header_frame.pack(fill="x", padx=16, pady=(12, 8))

        header_title = ctk.CTkLabel(
            self.header_frame,
            text="⚡ DISTRIBUTED GPU OFFLOADING SYSTEM",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#38bdf8",
        )
        header_title.pack(side="left", padx=16, pady=10)

        subtitle = ctk.CTkLabel(
            self.header_frame,
            text="CSC-334: Parallel and Distributed Computing",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
        )
        subtitle.pack(side="left", padx=(0, 16), pady=10)

        # Connection status badge
        self.badge_status = ctk.CTkLabel(
            self.header_frame,
            text="● WORKER DISCONNECTED",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#f87171",
            fg_color="#331418",
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self.badge_status.pack(side="right", padx=16, pady=10)

        # Main scrollable body container
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=12, pady=4)

        # Section 1: Worker Connection & GPU Telemetry
        self._build_connection_card()

        # Section 2: Input Media Picker & Transcode Parameters
        self._build_input_and_config_card()

        # Section 3: Execution Controls & Multi-Stage Real-Time Progress
        self._build_progress_and_actions_card()

        # Section 4: Speedup Comparison & Output Summary
        self._build_results_summary_card()

        # Section 5: Integrated Real-Time Console Terminal
        self._build_terminal_card()

    def _build_connection_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        title = ctk.CTkLabel(
            card,
            text="1. REMOTE WORKER NODE CONFIGURATION & HANDSHAKE",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        )
        title.pack(anchor="w", padx=14, pady=(10, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))

        # Server IP
        lbl_ip = ctk.CTkLabel(row, text="Worker IP:", font=ctk.CTkFont(size=12))
        lbl_ip.pack(side="left", padx=(0, 6))

        self.entry_ip = ctk.CTkEntry(row, width=140, placeholder_text="127.0.0.1")
        self.entry_ip.insert(0, DEFAULT_CLIENT_TARGET)
        self.entry_ip.pack(side="left", padx=(0, 14))

        # Server Port
        lbl_port = ctk.CTkLabel(row, text="Port:", font=ctk.CTkFont(size=12))
        lbl_port.pack(side="left", padx=(0, 6))

        self.entry_port = ctk.CTkEntry(row, width=80, placeholder_text="5050")
        self.entry_port.insert(0, str(DEFAULT_PORT))
        self.entry_port.pack(side="left", padx=(0, 16))

        # Ping & Handshake Button
        self.btn_connect = ctk.CTkButton(
            row,
            text="🔗 Handshake & Ping Check",
            command=self._on_click_handshake,
            fg_color="#0284c7",
            hover_color="#0369a1",
            width=180,
        )
        self.btn_connect.pack(side="left", padx=(0, 16))

        # Ping Latency indicator
        self.lbl_latency = ctk.CTkLabel(
            row,
            text="Latency: -- ms",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#94a3b8",
        )
        self.lbl_latency.pack(side="left", padx=(0, 16))

        # GPU Telemetry Badge
        self.lbl_gpu_info = ctk.CTkLabel(
            row,
            text="GPU: Not Connected",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#cbd5e1",
        )
        self.lbl_gpu_info.pack(side="right", padx=(0, 8))

    def _build_input_and_config_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        title = ctk.CTkLabel(
            card,
            text="2. INPUT MEDIA ASSET & TRANSCODING CONFIGURATION",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        )
        title.pack(anchor="w", padx=14, pady=(10, 6))

        # File Selection Row
        file_row = ctk.CTkFrame(card, fg_color="transparent")
        file_row.pack(fill="x", padx=14, pady=(0, 8))

        self.entry_filepath = ctk.CTkEntry(
            file_row,
            placeholder_text="Select input video file (.mp4, .mkv, .mov, .avi)...",
            height=32,
        )
        self.entry_filepath.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_browse = ctk.CTkButton(
            file_row,
            text="📂 Browse...",
            width=110,
            command=self._on_click_browse,
        )
        self.btn_browse.pack(side="left", padx=(0, 8))

        self.btn_gen_test = ctk.CTkButton(
            file_row,
            text="🎬 Generate Sample Video",
            width=170,
            fg_color="#334155",
            hover_color="#475569",
            command=self._on_click_generate_test_sample,
        )
        self.btn_gen_test.pack(side="left")

        # Media Info Bar
        self.info_row = ctk.CTkFrame(card, fg_color="#141820", corner_radius=6)
        self.info_row.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_media_meta = ctk.CTkLabel(
            self.info_row,
            text="No video selected. Choose an existing file or click 'Generate Sample Video' above.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
        )
        self.lbl_media_meta.pack(anchor="w", padx=10, pady=6)

        # Transcoding Parameters Grid
        param_grid = ctk.CTkFrame(card, fg_color="transparent")
        param_grid.pack(fill="x", padx=14, pady=(0, 12))

        # 1. Acceleration Engine
        col1 = ctk.CTkFrame(param_grid, fg_color="transparent")
        col1.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(col1, text="Hardware Engine:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.cmb_engine = ctk.CTkComboBox(
            col1,
            values=[
                "auto_detect (Auto Hardware Detect)",
                "h264_nvenc (NVIDIA GPU)",
                "hevc_nvenc (NVIDIA HEVC)",
                "h264_mf (Windows Hardware MFT)",
                "libx264 (Software CPU)",
            ],
            width=210,
        )
        self.cmb_engine.set("auto_detect (Auto Hardware Detect)")
        self.cmb_engine.pack(anchor="w", pady=(2, 0))

        # 2. Target Resolution
        col2 = ctk.CTkFrame(param_grid, fg_color="transparent")
        col2.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(col2, text="Target Resolution:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.cmb_res = ctk.CTkComboBox(
            col2,
            values=list(RESOLUTIONS.keys()),
            width=180,
        )
        self.cmb_res.set("720p (HD 1280x720)")
        self.cmb_res.pack(anchor="w", pady=(2, 0))

        # 3. Target Bitrate
        col3 = ctk.CTkFrame(param_grid, fg_color="transparent")
        col3.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(col3, text="Target Bitrate:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.cmb_bitrate = ctk.CTkComboBox(
            col3,
            values=BITRATE_PRESETS,
            width=150,
        )
        self.cmb_bitrate.set("3000k")
        self.cmb_bitrate.pack(anchor="w", pady=(2, 0))

        # 4. Preset
        col4 = ctk.CTkFrame(param_grid, fg_color="transparent")
        col4.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(col4, text="Quality Preset:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.cmb_preset = ctk.CTkComboBox(
            col4,
            values=["p1 (Fastest)", "p4 (Balanced)", "p7 (Slowest / High Quality)", "fast", "medium", "slow"],
            width=150,
        )
        self.cmb_preset.set("p4 (Balanced)")
        self.cmb_preset.pack(anchor="w", pady=(2, 0))

    def _build_progress_and_actions_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        title = ctk.CTkLabel(
            card,
            text="3. WORKLOAD EXECUTION & REAL-TIME PROGRESS TRACKING",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        )
        title.pack(anchor="w", padx=14, pady=(10, 6))

        # Action Buttons Row
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_offload = ctk.CTkButton(
            action_row,
            text="🚀 Offload to Remote GPU",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=36,
            command=self._on_click_start_offload,
        )
        self.btn_offload.pack(side="left", padx=(0, 12))

        self.btn_benchmark_local = ctk.CTkButton(
            action_row,
            text="💻 Run Local CPU Benchmark",
            font=ctk.CTkFont(size=13),
            fg_color="#3b82f6",
            hover_color="#2563eb",
            height=36,
            command=self._on_click_start_local,
        )
        self.btn_benchmark_local.pack(side="left", padx=(0, 12))

        self.btn_cancel = ctk.CTkButton(
            action_row,
            text="⛔ Cancel",
            font=ctk.CTkFont(size=13),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            height=36,
            state="disabled",
            command=self._on_click_cancel,
        )
        self.btn_cancel.pack(side="left")

        # Multi-stage Breadcrumbs
        self.stage_row = ctk.CTkFrame(card, fg_color="#141820", corner_radius=6)
        self.stage_row.pack(fill="x", padx=14, pady=(0, 10))

        stages = [
            ("s1", "1. Handshake"),
            ("s2", "2. Uploading"),
            ("s3", "3. GPU Transcoding"),
            ("s4", "4. Downloading"),
            ("s5", "5. Checksum Verify"),
            ("s6", "6. Completed"),
        ]
        self.stage_labels = {}
        for key, text in stages:
            lbl = ctk.CTkLabel(
                self.stage_row,
                text=text,
                font=ctk.CTkFont(size=11),
                text_color="#64748b",
            )
            lbl.pack(side="left", expand=True, padx=4, pady=6)
            self.stage_labels[key] = lbl

        # Animated Progress Bar
        self.progress_bar = ctk.CTkProgressBar(card, height=14, progress_color="#38bdf8")
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=14, pady=(0, 6))

        # Real-time Metrics Readout Bar
        stats_frame = ctk.CTkFrame(card, fg_color="transparent")
        stats_frame.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_stage_desc = ctk.CTkLabel(
            stats_frame,
            text="Status: Ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_stage_desc.pack(side="left")

        self.lbl_live_metrics = ctk.CTkLabel(
            stats_frame,
            text="Progress: 0.0% | Speed: -- | FPS: -- | Elapsed: 00:00 | ETA: --",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#94a3b8",
        )
        self.lbl_live_metrics.pack(side="right")

    def _build_results_summary_card(self):
        self.summary_card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#182230")
        self.summary_card.pack(fill="x", pady=6)

        title = ctk.CTkLabel(
            self.summary_card,
            text="4. PERFORMANCE EVALUATION & SPEEDUP ANALYSIS",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        )
        title.pack(anchor="w", padx=14, pady=(10, 6))

        metrics_grid = ctk.CTkFrame(self.summary_card, fg_color="transparent")
        metrics_grid.pack(fill="x", padx=14, pady=(0, 8))

        # Box 1: Local CPU Time
        self.box_local = ctk.CTkFrame(metrics_grid, fg_color="#141a24", corner_radius=6)
        self.box_local.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(self.box_local, text="Local CPU Time (T_local):", font=ctk.CTkFont(size=11)).pack(pady=(4, 0))
        self.val_local_time = ctk.CTkLabel(self.box_local, text="-- s", font=ctk.CTkFont(size=14, weight="bold"), text_color="#cbd5e1")
        self.val_local_time.pack(pady=(0, 4))

        # Box 2: Remote GPU Offload Time
        self.box_remote = ctk.CTkFrame(metrics_grid, fg_color="#141a24", corner_radius=6)
        self.box_remote.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(self.box_remote, text="Remote Offload Time (T_total):", font=ctk.CTkFont(size=11)).pack(pady=(4, 0))
        self.val_remote_time = ctk.CTkLabel(self.box_remote, text="-- s", font=ctk.CTkFont(size=14, weight="bold"), text_color="#38bdf8")
        self.val_remote_time.pack(pady=(0, 4))

        # Box 3: Speedup Factor
        self.box_speedup = ctk.CTkFrame(metrics_grid, fg_color="#141a24", corner_radius=6)
        self.box_speedup.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(self.box_speedup, text="Calculated Speedup (S):", font=ctk.CTkFont(size=11)).pack(pady=(4, 0))
        self.val_speedup = ctk.CTkLabel(self.box_speedup, text="-- x", font=ctk.CTkFont(size=16, weight="bold"), text_color="#4ade80")
        self.val_speedup.pack(pady=(0, 4))

        # Box 4: Network Overhead
        self.box_overhead = ctk.CTkFrame(metrics_grid, fg_color="#141a24", corner_radius=6)
        self.box_overhead.pack(side="left", expand=True, fill="x", padx=4)
        ctk.CTkLabel(self.box_overhead, text="Network Overhead:", font=ctk.CTkFont(size=11)).pack(pady=(4, 0))
        self.val_overhead = ctk.CTkLabel(self.box_overhead, text="-- %", font=ctk.CTkFont(size=14, weight="bold"), text_color="#fbbf24")
        self.val_overhead.pack(pady=(0, 4))

        # Output File actions row
        out_row = ctk.CTkFrame(self.summary_card, fg_color="transparent")
        out_row.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_output_file = ctk.CTkLabel(
            out_row,
            text="Rendered Output: None",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
        )
        self.lbl_output_file.pack(side="left")

        self.btn_open_file = ctk.CTkButton(
            out_row,
            text="▶ Play Video",
            width=110,
            state="disabled",
            command=self._on_click_open_output,
        )
        self.btn_open_file.pack(side="right", padx=(8, 0))

        self.btn_open_folder = ctk.CTkButton(
            out_row,
            text="📁 Open Folder",
            width=120,
            fg_color="#334155",
            hover_color="#475569",
            command=self._on_click_open_folder,
        )
        self.btn_open_folder.pack(side="right")

    def _build_terminal_card(self):
        card = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color="#181c24")
        card.pack(fill="both", expand=True, pady=6)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(8, 4))

        title = ctk.CTkLabel(
            header,
            text="5. REAL-TIME LOG TERMINAL & PROTOCOL DIAGNOSTICS",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#7dd3fc",
        )
        title.pack(side="left")

        btn_clear = ctk.CTkButton(
            header,
            text="Clear",
            width=70,
            height=24,
            fg_color="#27272a",
            hover_color="#3f3f46",
            command=self._clear_terminal,
        )
        btn_clear.pack(side="right")

        # Scrollable console text box
        self.txt_terminal = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0d1117",
            text_color="#e2e8f0",
            height=180,
            wrap="word",
        )
        self.txt_terminal.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    # -------------------------------------------------------------------------
    # UI Helpers & Terminal Logging
    # -------------------------------------------------------------------------
    def log_to_terminal(self, message: str):
        """Append log line with timestamp to the integrated console terminal."""
        def _append():
            timestamp = time.strftime("%H:%M:%S")
            self.txt_terminal.insert("end", f"[{timestamp}] {message}\n")
            self.txt_terminal.see("end")
        self.after(0, _append)

    def _clear_terminal(self):
        self.txt_terminal.delete("1.0", "end")

    def _set_stage_active(self, active_key: Optional[str]):
        """Highlight current active pipeline stage breadcrumb."""
        for key, lbl in self.stage_labels.items():
            if key == active_key:
                lbl.configure(text_color="#38bdf8", font=ctk.CTkFont(size=11, weight="bold"))
            else:
                lbl.configure(text_color="#64748b", font=ctk.CTkFont(size=11))

    # -------------------------------------------------------------------------
    # Handshake & Networking Callbacks
    # -------------------------------------------------------------------------
    def _on_click_handshake(self):
        """Run handshake and latency check in a worker thread."""
        ip = self.entry_ip.get().strip() or DEFAULT_CLIENT_TARGET
        try:
            port = int(self.entry_port.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be an integer (e.g. 5050)")
            return

        self.btn_connect.configure(state="disabled")
        self.badge_status.configure(text="● CONNECTING...", text_color="#facc15", fg_color="#3a2f05")
        self.log_to_terminal(f"Connecting to worker node at {ip}:{port}...")

        def _worker():
            try:
                self.network_client.host = ip
                self.network_client.port = port
                self.network_client.connect()

                # Ping latency check
                latency = self.network_client.ping()

                # Handshake protocol
                handshake_resp = self.network_client.handshake()
                gpu_telemetry = handshake_resp.get("gpu_telemetry", {})
                worker_name = handshake_resp.get("worker_name", "Unknown")
                gpu_name = gpu_telemetry.get("gpu_name", "Unknown GPU")
                vram_free = gpu_telemetry.get("vram_free_mb", 0)
                preferred_codec = gpu_telemetry.get("preferred_gpu_encoder", "libx264")

                def _update_success():
                    self.badge_status.configure(
                        text=f"● ONLINE: {ip}:{port}",
                        text_color="#4ade80",
                        fg_color="#052e16",
                    )
                    self.lbl_latency.configure(
                        text=f"Latency: {latency:.2f} ms",
                        text_color="#4ade80" if latency < 10 else "#facc15",
                    )
                    self.lbl_gpu_info.configure(
                        text=f"GPU: {gpu_name} ({vram_free} MB Free) | Eng: {preferred_codec}"
                    )
                    self.btn_connect.configure(state="normal")
                    self.log_to_terminal(f"[HANDSHAKE SUCCESS] Worker '{worker_name}' online. Latency: {latency:.2f} ms.")
                    self.log_to_terminal(f"[TELEMETRY] GPU: {gpu_name} | VRAM: {vram_free} MB | Codec: {preferred_codec}")

                self.after(0, _update_success)

            except Exception as e:
                def _update_fail():
                    self.badge_status.configure(text="● WORKER OFFLINE", text_color="#f87171", fg_color="#331418")
                    self.lbl_latency.configure(text="Latency: N/A", text_color="#94a3b8")
                    self.lbl_gpu_info.configure(text="GPU: Not Connected")
                    self.btn_connect.configure(state="normal")
                    self.log_to_terminal(f"[CONNECTION ERROR] Failed to connect to {ip}:{port}: {e}")
                    messagebox.showwarning(
                        "Connection Failed",
                        f"Could not connect to worker at {ip}:{port}.\n\nPlease ensure the daemon is running:\npython server/daemon.py",
                    )

                self.after(0, _update_fail)

        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------------------------
    # File Selection & Test Media Generation
    # -------------------------------------------------------------------------
    def _on_click_browse(self):
        f = filedialog.askopenfilename(
            title="Select Video File for Transcoding",
            filetypes=[
                ("Video Files", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.ts"),
                ("All Files", "*.*"),
            ],
        )
        if f:
            self._set_selected_file(Path(f))

    def _on_click_generate_test_sample(self):
        """Generate a synthetic test clip in background."""
        self.btn_gen_test.configure(state="disabled")
        self.log_to_terminal("Generating synthetic 720p test clip for benchmarking...")

        def _gen():
            try:
                dest = TEST_MEDIA_DIR / f"sample_{int(time.time())}.mp4"
                generate_synthetic_video(dest, width=1280, height=720, duration_seconds=5)
                self.after(0, lambda: self._set_selected_file(dest))
                self.log_to_terminal(f"Synthetic video generated: {dest.name} ({format_bytes(dest.stat().st_size)})")
            except Exception as e:
                self.log_to_terminal(f"Failed to generate test sample: {e}")
            finally:
                self.after(0, lambda: self.btn_gen_test.configure(state="normal"))

        threading.Thread(target=_gen, daemon=True).start()

    def _set_selected_file(self, file_path: Path):
        self.selected_file = file_path
        self.entry_filepath.delete(0, "end")
        self.entry_filepath.insert(0, str(file_path))

        # Probe metadata
        try:
            self.media_info = probe_media_file(file_path)
            meta_str = (
                f"File: {file_path.name} | Size: {format_bytes(self.media_info['file_size'])} | "
                f"Duration: {format_duration(self.media_info['duration_seconds'])} | "
                f"Resolution: {self.media_info['width']}x{self.media_info['height']} | "
                f"FPS: {self.media_info['fps']} | Codec: {self.media_info['video_codec']} / {self.media_info['audio_codec']}"
            )
            self.lbl_media_meta.configure(text=meta_str, text_color="#cbd5e1")
            self.log_to_terminal(f"Loaded media file: {file_path.name}")
        except Exception as e:
            self.lbl_media_meta.configure(text=f"File selected, but probing failed: {e}", text_color="#f87171")

    def _get_transcode_config(self) -> Dict[str, Any]:
        """Read selected options from GUI comboboxes."""
        eng_raw = self.cmb_engine.get().split()[0]
        return {
            "codec": eng_raw,
            "resolution": self.cmb_res.get(),
            "bitrate": self.cmb_bitrate.get(),
            "preset": self.cmb_preset.get().split()[0],
            "audio": "copy",
        }

    # -------------------------------------------------------------------------
    # Distributed GPU Offloading Pipeline
    # -------------------------------------------------------------------------
    def _on_click_start_offload(self):
        """Trigger distributed task offloading."""
        if not self.selected_file or not self.selected_file.exists():
            messagebox.showwarning("File Missing", "Please select a valid input video file first.")
            return

        ip = self.entry_ip.get().strip() or DEFAULT_CLIENT_TARGET
        port = int(self.entry_port.get().strip() or DEFAULT_PORT)
        config = self._get_transcode_config()

        self._set_ui_processing_state(True)
        self.progress_bar.set(0.0)
        self.lbl_stage_desc.configure(text="Status: Initializing Distributed Offload...")
        self.log_to_terminal(f"Beginning offload to remote GPU worker ({ip}:{port})...")

        def _worker():
            try:
                # Ensure connection
                if not self.network_client.is_connected:
                    self.network_client.host = ip
                    self.network_client.port = port
                    self.after(0, lambda: self._set_stage_active("s1"))
                    self.network_client.connect()
                    self.network_client.handshake()

                def on_progress(stats: Dict[str, Any]):
                    def _update():
                        stage = stats.get("stage", "")
                        pct = stats.get("percent", 0.0)
                        self.progress_bar.set(pct / 100.0)

                        if "Hashing" in stage:
                            self._set_stage_active("s1")
                        elif "Uploading" in stage:
                            self._set_stage_active("s2")
                        elif "Transcoding" in stage:
                            self._set_stage_active("s3")
                        elif "Downloading" in stage:
                            self._set_stage_active("s4")
                        elif "Verifying" in stage:
                            self._set_stage_active("s5")
                        elif "Completed" in stage:
                            self._set_stage_active("s6")

                        fps = stats.get("fps", 0)
                        speed = stats.get("speed", "--")
                        el = format_duration(stats.get("elapsed_seconds", 0))
                        eta = format_duration(stats.get("eta_seconds", 0)) if "eta_seconds" in stats else "--"

                        self.lbl_stage_desc.configure(text=f"Status: {stage}")
                        self.lbl_live_metrics.configure(
                            text=f"Progress: {pct:.1f}% | Speed: {speed} | FPS: {fps} | Elapsed: {el} | ETA: {eta}"
                        )
                    self.after(0, _update)

                def on_log(msg: str):
                    self.log_to_terminal(msg)

                result = self.network_client.offload_task(
                    input_file=self.selected_file,
                    config=config,
                    progress_callback=on_progress,
                    log_callback=on_log,
                )

                self.last_remote_result = result

                def _on_finish():
                    self._set_stage_active("s6")
                    self.progress_bar.set(1.0)
                    self.lbl_stage_desc.configure(text="Status: Offload Completed Successfully!")
                    self._update_comparison_display()
                    self.log_to_terminal(
                        f"[SUCCESS] Remote offload finished! Total: {result['total_offload_seconds']}s "
                        f"(Compute: {result['compute_duration_seconds']}s, Net Overhead: {result['network_overhead_seconds']}s)"
                    )
                    messagebox.showinfo(
                        "Offload Complete",
                        f"Distributed GPU Offloading Complete!\n\n"
                        f"Total Offload Time: {result['total_offload_seconds']}s\n"
                        f"GPU Compute Time : {result['compute_duration_seconds']}s\n"
                        f"Network Overhead : {result['network_overhead_seconds']}s ({result['network_overhead_pct']}%)\n\n"
                        f"Output File: {os.path.basename(result['output_file'])}\n"
                        f"Integrity Check: SHA-256 Verified",
                    )

                self.after(0, _on_finish)

            except Exception as e:
                def _on_err():
                    self.lbl_stage_desc.configure(text=f"Status: Error - {e}")
                    self.log_to_terminal(f"[ERROR] Offload failed: {e}")
                    messagebox.showerror("Offload Failed", f"Remote offload failed:\n{e}")
                self.after(0, _on_err)
            finally:
                self.after(0, lambda: self._set_ui_processing_state(False))

        self.active_worker_thread = threading.Thread(target=_worker, daemon=True)
        self.active_worker_thread.start()

    # -------------------------------------------------------------------------
    # Local CPU Benchmark Execution
    # -------------------------------------------------------------------------
    def _on_click_start_local(self):
        """Run transcode locally on client CPU for direct baseline comparison."""
        if not self.selected_file or not self.selected_file.exists():
            messagebox.showwarning("File Missing", "Please select a valid input video file first.")
            return

        config = self._get_transcode_config()
        self._set_ui_processing_state(True)
        self.progress_bar.set(0.0)
        self.lbl_stage_desc.configure(text="Status: Running Local CPU Benchmark...")
        self.log_to_terminal(f"Running local CPU baseline transcode on {self.selected_file.name}...")

        def _worker():
            try:
                def on_progress(stats: Dict[str, Any]):
                    def _update():
                        pct = stats.get("percent", 0.0)
                        self.progress_bar.set(pct / 100.0)
                        speed = stats.get("speed", "--")
                        fps = stats.get("fps", 0)
                        el = format_duration(stats.get("elapsed_seconds", 0))
                        eta = format_duration(stats.get("eta_seconds", 0)) if "eta_seconds" in stats else "--"
                        self.lbl_stage_desc.configure(text="Status: Local CPU Transcoding (libx264)")
                        self.lbl_live_metrics.configure(
                            text=f"Progress: {pct:.1f}% | Speed: {speed} | FPS: {fps} | Elapsed: {el} | ETA: {eta}"
                        )
                    self.after(0, _update)

                def on_log(msg: str):
                    self.log_to_terminal(msg)

                res = self.local_engine.run_local_transcode(
                    input_path=self.selected_file,
                    config=config,
                    progress_callback=on_progress,
                    log_callback=on_log,
                )

                self.last_local_result = res

                def _on_finish():
                    self.progress_bar.set(1.0)
                    self.lbl_stage_desc.configure(text="Status: Local CPU Benchmark Completed!")
                    self._update_comparison_display()
                    self.log_to_terminal(f"[LOCAL SUCCESS] Finished in {res['execution_time_seconds']}s")

                self.after(0, _on_finish)

            except Exception as e:
                self.after(0, lambda: self.log_to_terminal(f"[ERROR] Local execution failed: {e}"))
            finally:
                self.after(0, lambda: self._set_ui_processing_state(False))

        self.active_worker_thread = threading.Thread(target=_worker, daemon=True)
        self.active_worker_thread.start()

    # -------------------------------------------------------------------------
    # Cancellation & State Controls
    # -------------------------------------------------------------------------
    def _on_click_cancel(self):
        """Handle cancellation click."""
        self.log_to_terminal("Cancellation requested by user...")
        self.network_client.request_cancel()
        self.local_engine.cancel()
        self.btn_cancel.configure(state="disabled")

    def _set_ui_processing_state(self, processing: bool):
        self.is_processing = processing
        state = "disabled" if processing else "normal"
        self.btn_offload.configure(state=state)
        self.btn_benchmark_local.configure(state=state)
        self.btn_browse.configure(state=state)
        self.btn_gen_test.configure(state=state)
        self.btn_cancel.configure(state="normal" if processing else "disabled")

    def _update_comparison_display(self):
        """Update the side-by-side performance comparison metrics."""
        t_local = self.last_local_result.get("execution_time_seconds") if self.last_local_result else None
        t_remote = self.last_remote_result.get("total_offload_seconds") if self.last_remote_result else None

        if t_local is not None:
            self.val_local_time.configure(text=f"{t_local:.2f} s")
        if t_remote is not None:
            self.val_remote_time.configure(text=f"{t_remote:.2f} s")

        if t_local is not None and t_remote is not None and t_remote > 0:
            speedup = t_local / t_remote
            self.val_speedup.configure(
                text=f"{speedup:.2f} x",
                text_color="#4ade80" if speedup >= 1.0 else "#f87171",
            )

        if self.last_remote_result:
            oh_pct = self.last_remote_result.get("network_overhead_pct", 0)
            self.val_overhead.configure(text=f"{oh_pct:.1f} %")

            out_file = self.last_remote_result.get("output_file")
            if out_file:
                self.lbl_output_file.configure(
                    text=f"Rendered Output: {os.path.basename(out_file)} ({format_bytes(os.path.getsize(out_file))})"
                )
                self.btn_open_file.configure(state="normal")
                self.btn_open_folder.configure(state="normal")

    def _on_click_open_output(self):
        if not self.last_remote_result or not self.last_remote_result.get("output_file"):
            return
        out_path = self.last_remote_result["output_file"]
        if os.path.exists(out_path):
            os.startfile(out_path)

    def _on_click_open_folder(self):
        folder = CLIENT_OUTPUT_DIR
        if os.path.exists(folder):
            os.startfile(folder)


def main():
    app = DistributedOffloadGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
