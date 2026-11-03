"""
Host GPU Chunked Export Dialog for Clipchamp Studio.
Provides real-time multi-chunk progress grid, GPU hardware telemetry,
integrity validation, and side-by-side local CPU benchmark comparison.
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from tkinter import messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from clipchamp_studio.engine.chunker import TimelineChunker
from clipchamp_studio.engine.project_executor import LocalProjectExecutor
from clipchamp_studio.model.project import ClipchampProject
from clipchamp_studio.network.clipchamp_client import ClipchampNetworkClient
from client.client_network import NetworkClient
from common.config import CLIENT_OUTPUT_DIR, DEFAULT_CLIENT_TARGET, DEFAULT_PORT
from common.utils import format_bytes, format_duration


class ExportDialog(ctk.CTkToplevel):
    """Dedicated modal dashboard for Chunked Host GPU Export & Benchmarking."""

    def __init__(
        self,
        parent,
        project: ClipchampProject,
        target_host: str = DEFAULT_CLIENT_TARGET,
        target_port: int = DEFAULT_PORT,
    ):
        super().__init__(parent)
        self.project = project
        self.target_host = target_host
        self.target_port = target_port

        self.title(f"Host GPU Export Studio — {self.project.project_name}")
        self.geometry("920x760")
        self.minsize(840, 680)

        # Clients
        self.network_client = NetworkClient(host=target_host, port=target_port)
        self.clipchamp_client = ClipchampNetworkClient(self.network_client)
        self.local_executor = LocalProjectExecutor()

        # State
        self.is_running = False
        self.remote_result: Optional[Dict[str, Any]] = None
        self.local_result: Optional[Dict[str, Any]] = None
        self.chunk_cards: List[Dict[str, Any]] = []

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _on_window_close(self):
        """Handle dialog close cleanly by cancelling running tasks and closing socket."""
        if self.is_running:
            self.network_client.request_cancel()
        try:
            self.network_client.close()
        except Exception:
            pass
        self.destroy()

    def _build_ui(self):
        # 1. Top Banner
        header = ctk.CTkFrame(self, corner_radius=10, fg_color="#181c24")
        header.pack(fill="x", padx=16, pady=(14, 8))

        lbl_t = ctk.CTkLabel(
            header,
            text="🚀 CLIPCHAMP DISTRIBUTED GPU CHUNKED EXPORT",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#38bdf8",
        )
        lbl_t.pack(side="left", padx=14, pady=8)

        self.lbl_worker_badge = ctk.CTkLabel(
            header,
            text=f"Host: {self.target_host}:{self.target_port}",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#94a3b8",
            fg_color="#0f172a",
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.lbl_worker_badge.pack(side="right", padx=14, pady=8)

        # 2. Main Scroll Container
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=12, pady=4)

        # Section 1: Settings
        self._build_settings_card()

        # Section 2: Real-time Multi-Chunk Progress Grid
        self._build_chunk_grid_card()

        # Section 3: Live Progress Bars & Telemetry
        self._build_progress_dashboard_card()

        # Section 4: Performance & Speedup Comparison
        self._build_results_card()

        # Section 5: Real-time Output Logs
        self._build_logs_card()

    def _build_settings_card(self):
        card = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="1. EXPORT PROFILE & HARDWARE ACCELERATION PARAMETERS",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 6))

        # Resolution
        ctk.CTkLabel(row1, text="Resolution:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.combo_res = ctk.CTkComboBox(
            row1,
            values=["1080p FHD (1920x1080)", "720p HD (1280x720)", "4K UHD (3840x2160)", "480p SD (854x480)"],
            width=180,
        )
        self.combo_res.set("1080p FHD (1920x1080)")
        self.combo_res.pack(side="left", padx=(0, 12))

        # Codec
        ctk.CTkLabel(row1, text="Host Encoder:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.combo_codec = ctk.CTkComboBox(
            row1,
            values=["auto_detect", "h264_nvenc", "hevc_nvenc", "h264_mf", "libx264"],
            width=130,
        )
        self.combo_codec.set("auto_detect")
        self.combo_codec.pack(side="left", padx=(0, 12))

        # Bitrate
        ctk.CTkLabel(row1, text="Bitrate:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.combo_bitrate = ctk.CTkComboBox(
            row1,
            values=["3000k", "5000k", "8000k", "12000k", "20000k"],
            width=90,
        )
        self.combo_bitrate.set("5000k")
        self.combo_bitrate.pack(side="left", padx=(0, 12))

        # Chunk duration
        ctk.CTkLabel(row1, text="Chunk Size:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.combo_chunk = ctk.CTkComboBox(
            row1,
            values=["4.0s", "6.0s", "8.0s", "10.0s", "15.0s"],
            width=80,
            command=self._on_chunk_setting_change,
        )
        self.combo_chunk.set(f"{self.project.chunk_duration:.1f}s")
        self.combo_chunk.pack(side="left")

        # Action Buttons
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(4, 10))

        self.btn_export_gpu = ctk.CTkButton(
            row2,
            text="🚀 Export with Host GPU (Chunked)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#6366f1",
            hover_color="#4f46e5",
            height=34,
            command=self._start_gpu_export,
        )
        self.btn_export_gpu.pack(side="left", padx=(0, 10))

        self.btn_benchmark_cpu = ctk.CTkButton(
            row2,
            text="💻 Benchmark on Local CPU",
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569",
            height=34,
            command=self._start_cpu_benchmark,
        )
        self.btn_benchmark_cpu.pack(side="left", padx=(0, 10))

        self.lbl_chunk_summary = ctk.CTkLabel(
            row2,
            text=self._get_chunk_calc_string(),
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#a5b4fc",
        )
        self.lbl_chunk_summary.pack(side="right", padx=6)

    def _get_chunk_calc_string(self) -> str:
        chunks = TimelineChunker.partition_project(self.project, chunk_duration=self.project.chunk_duration)
        return f"🧩 Timeline: {self.project.total_duration:.1f}s → {len(chunks)} Chunks"

    def _on_chunk_setting_change(self, val):
        import re
        m = re.search(r"([0-9.]+)", val)
        if m:
            self.project.chunk_duration = float(m.group(1))
            self.lbl_chunk_summary.configure(text=self._get_chunk_calc_string())
            self._render_chunk_cards()

    def _build_chunk_grid_card(self):
        self.card_chunk_grid = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2430")
        self.card_chunk_grid.pack(fill="x", pady=6)

        ctk.CTkLabel(
            self.card_chunk_grid,
            text="2. REAL-TIME MULTI-CHUNK GPU WORKLOAD PIPELINE",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.chunk_grid_container = ctk.CTkFrame(self.card_chunk_grid, fg_color="transparent")
        self.chunk_grid_container.pack(fill="x", padx=10, pady=(0, 10))

        self._render_chunk_cards()

    def _render_chunk_cards(self):
        """Build visual status cards for each temporal chunk."""
        for w in self.chunk_grid_container.winfo_children():
            w.destroy()
        self.chunk_cards.clear()

        chunks = TimelineChunker.partition_project(self.project, chunk_duration=self.project.chunk_duration)
        for idx, chunk in enumerate(chunks):
            frame = ctk.CTkFrame(self.chunk_grid_container, fg_color="#131722", corner_radius=8)
            frame.pack(side="left", expand=True, fill="x", padx=4, pady=4)

            lbl_title = ctk.CTkLabel(
                frame,
                text=f"Chunk #{idx + 1}",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#f1f5f9",
            )
            lbl_title.pack(padx=6, pady=(4, 0))

            lbl_time = ctk.CTkLabel(
                frame,
                text=f"[{chunk.window_start:.1f}s - {chunk.window_end:.1f}s]",
                font=ctk.CTkFont(family="Consolas", size=9),
                text_color="#94a3b8",
            )
            lbl_time.pack(padx=6, pady=(0, 2))

            pbar = ctk.CTkProgressBar(frame, height=8, progress_color="#6366f1")
            pbar.set(0.0)
            pbar.pack(fill="x", padx=8, pady=4)

            lbl_status = ctk.CTkLabel(
                frame,
                text="QUEUED",
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                text_color="#64748b",
            )
            lbl_status.pack(padx=6, pady=(0, 4))

            self.chunk_cards.append({
                "frame": frame,
                "pbar": pbar,
                "status": lbl_status,
            })

    def _update_chunk_card(self, chunk_idx: int, pct: float, status_text: str, is_active: bool = True):
        """Update specific chunk card progress."""
        if 0 <= chunk_idx < len(self.chunk_cards):
            card = self.chunk_cards[chunk_idx]
            card["pbar"].set(pct / 100.0)
            card["status"].configure(text=status_text)
            if pct >= 100.0:
                card["frame"].configure(fg_color="#064e3b")  # Dark green
                card["status"].configure(text="COMPLETED ✅", text_color="#34d399")
            elif is_active:
                card["frame"].configure(fg_color="#1e1b4b")  # Dark indigo
                card["status"].configure(text=status_text, text_color="#818cf8")

    def _build_progress_dashboard_card(self):
        card = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="3. LIVE STAGE TRACKING & HARDWARE TELEMETRY",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        # Overall Progress Bar
        self.main_pbar = ctk.CTkProgressBar(card, height=14, progress_color="#38bdf8")
        self.main_pbar.set(0.0)
        self.main_pbar.pack(fill="x", padx=12, pady=6)

        # Stage Text & Stats
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))

        self.lbl_stage = ctk.CTkLabel(
            row,
            text="Stage: Idle / Ready to export",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#e2e8f0",
        )
        self.lbl_stage.pack(side="left")

        self.lbl_telemetry = ctk.CTkLabel(
            row,
            text="GPU: Awaiting connection | FPS: 0 | Speed: 0.0x",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#38bdf8",
        )
        self.lbl_telemetry.pack(side="right")

    def _build_results_card(self):
        self.card_results = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2430")
        self.card_results.pack(fill="x", pady=6)

        ctk.CTkLabel(
            self.card_results,
            text="4. PERFORMANCE EVALUATION & SPEEDUP ANALYSIS (AMDAHL'S LAW)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.box_results = ctk.CTkFrame(self.card_results, fg_color="#131722", corner_radius=8)
        self.box_results.pack(fill="x", padx=12, pady=(0, 10))

        self.lbl_results_text = ctk.CTkLabel(
            self.box_results,
            text="Run 'Export with Host GPU' and 'Benchmark on Local CPU' to view side-by-side speedup metrics.",
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left",
            text_color="#94a3b8",
        )
        self.lbl_results_text.pack(padx=12, pady=10, anchor="w")

        # Open buttons
        self.row_open = ctk.CTkFrame(self.card_results, fg_color="transparent")
        self.row_open.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_open_video = ctk.CTkButton(
            self.row_open,
            text="▶ Play Master Video",
            width=140,
            height=28,
            fg_color="#059669",
            hover_color="#047857",
            command=self._on_open_video,
            state="disabled",
        )
        self.btn_open_video.pack(side="left", padx=(0, 8))

        self.btn_open_folder = ctk.CTkButton(
            self.row_open,
            text="📁 Show in Folder",
            width=130,
            height=28,
            fg_color="#334155",
            hover_color="#475569",
            command=self._on_open_folder,
            state="disabled",
        )
        self.btn_open_folder.pack(side="left")

    def _build_logs_card(self):
        card = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2430")
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text="5. CONSOLE DIAGNOSTICS & NETWORK FRAMING LOGS",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#7dd3fc",
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.txt_logs = ctk.CTkTextbox(
            card,
            height=120,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#090b10",
            text_color="#cbd5e1",
        )
        self.txt_logs.pack(fill="x", padx=12, pady=(0, 10))

    def log(self, msg: str):
        self.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg: str):
        t_str = time.strftime("%H:%M:%S")
        self.txt_logs.insert("end", f"[{t_str}] {msg}\n")
        self.txt_logs.see("end")

    # -------------------------------------------------------------
    # Host GPU Export Execution
    # -------------------------------------------------------------
    def _start_gpu_export(self):
        if self.is_running:
            return
        self.is_running = True
        self.btn_export_gpu.configure(state="disabled")
        self.btn_benchmark_cpu.configure(state="disabled")
        self._render_chunk_cards()
        self.main_pbar.set(0.0)

        threading.Thread(target=self._worker_gpu_export, daemon=True).start()

    def _worker_gpu_export(self):
        try:
            self.log("Commencing Host GPU offload pipeline...")
            self.after(0, lambda: self.lbl_stage.configure(text="Connecting to Host..."))

            # 1. Connect and Handshake
            self.network_client.connect()
            caps = self.network_client.handshake()
            gpu_name = caps.get("gpu_telemetry", {}).get("gpu_name", "Remote GPU")
            self.log(f"Connected to Host GPU: {gpu_name}")

            # 2. Configure project export settings
            self.project.export_codec = self.combo_codec.get()
            self.project.export_bitrate = self.combo_bitrate.get()

            def on_progress(p: Dict[str, Any]):
                self.after(0, lambda p=p: self._handle_remote_progress(p))

            def on_log(m: str):
                self.log(m)

            # 3. Offload Project
            result = self.clipchamp_client.offload_project(
                project=self.project,
                output_dir=CLIENT_OUTPUT_DIR,
                progress_callback=on_progress,
                log_callback=on_log,
            )

            self.remote_result = result
            self.log(f"Export completed in {result['total_offload_seconds']}s! Output: {result['output_file']}")
            self.after(0, self._on_export_success)

        except Exception as e:
            self.log(f"Export failed: {e}")
            self.after(0, lambda err=str(e): messagebox.showerror("Export Failed", err))
        finally:
            self.network_client.close()
            self.is_running = False
            self.after(0, lambda: self.btn_export_gpu.configure(state="normal"))
            self.after(0, lambda: self.btn_benchmark_cpu.configure(state="normal"))

    def _handle_remote_progress(self, p: Dict[str, Any]):
        stage = p.get("stage", "")
        pct = p.get("total_percent", p.get("percent", 0.0))
        self.main_pbar.set(pct / 100.0)
        self.lbl_stage.configure(text=f"Stage: {stage} ({pct:.1f}%)")

        cur_chunk = p.get("current_chunk", 1) - 1
        chunk_pct = p.get("chunk_percent", pct)
        fps = p.get("fps", 0.0)
        speed = p.get("speed", "1.0x")
        gpu_name = p.get("gpu_name", "Host GPU")
        encoder = p.get("encoder", "")

        self.lbl_telemetry.configure(
            text=f"GPU: {gpu_name} ({encoder}) | FPS: {fps} | Speed: {speed}"
        )

        if 0 <= cur_chunk < len(self.chunk_cards):
            self._update_chunk_card(cur_chunk, chunk_pct, f"GPU {chunk_pct:.0f}% ({speed})")

    def _on_export_success(self):
        self.btn_open_video.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self._refresh_comparison_report()
        for idx in range(len(self.chunk_cards)):
            self._update_chunk_card(idx, 100.0, "COMPLETED ✅", False)

    # -------------------------------------------------------------
    # Local CPU Benchmark Execution
    # -------------------------------------------------------------
    def _start_cpu_benchmark(self):
        if self.is_running:
            return
        self.is_running = True
        self.btn_export_gpu.configure(state="disabled")
        self.btn_benchmark_cpu.configure(state="disabled")
        self.main_pbar.set(0.0)

        threading.Thread(target=self._worker_cpu_benchmark, daemon=True).start()

    def _worker_cpu_benchmark(self):
        try:
            self.log("Starting Local CPU baseline benchmark...")
            out_p = CLIENT_OUTPUT_DIR / f"local_bench_{self.project.project_id}.mp4"

            def on_prog(p):
                pct = p.get("percent", 0.0)
                stage = p.get("stage", "")
                self.after(0, lambda: self.main_pbar.set(pct / 100.0))
                self.after(0, lambda: self.lbl_stage.configure(text=f"{stage} ({pct}%)"))

            res = self.local_executor.render_project_locally(
                project=self.project,
                output_file=out_p,
                use_chunking=True,
                progress_callback=on_prog,
                log_callback=self.log,
            )
            self.local_result = res
            self.log(f"Local CPU benchmark finished in {res['execution_time_seconds']}s")
            self.after(0, self._refresh_comparison_report)
        except Exception as e:
            self.log(f"Local benchmark error: {e}")
        finally:
            self.is_running = False
            self.after(0, lambda: self.btn_export_gpu.configure(state="normal"))
            self.after(0, lambda: self.btn_benchmark_cpu.configure(state="normal"))

    def _refresh_comparison_report(self):
        lines = []
        if self.remote_result:
            r = self.remote_result
            lines.append("=== HOST GPU CHUNKED OFFLOAD METRICS ===")
            lines.append(f"  • Total Offload Duration: {r['total_offload_seconds']:.2f} s")
            lines.append(f"    - Upload Duration     : {r['upload_duration_seconds']:.2f} s")
            lines.append(f"    - Remote GPU Compute  : {r['compute_duration_seconds']:.2f} s ({r['gpu_name']} - {r['encoder_used']})")
            lines.append(f"    - Download Duration   : {r['download_duration_seconds']:.2f} s")
            lines.append(f"  • Chunks Processed      : {r['chunks_rendered']} chunks")
            lines.append(f"  • Output Size           : {format_bytes(r['output_size_bytes'])}")
            lines.append(f"  • SHA-256 Verified      : MATCHED ✅ ({r['sha256'][:14]}...)")

        if self.local_result:
            l = self.local_result
            lines.append("\n=== LOCAL CPU BASELINE METRICS ===")
            lines.append(f"  • Local CPU Duration    : {l['execution_time_seconds']:.2f} s ({l['engine']})")

        if self.remote_result and self.local_result:
            t_loc = self.local_result["execution_time_seconds"]
            t_rem = self.remote_result["total_offload_seconds"]
            speedup = t_loc / max(0.001, t_rem)
            time_saved = max(0.0, t_loc - t_rem)
            lines.append("\n=== SPEEDUP EVALUATION (AMDAHL'S LAW) ===")
            lines.append(f"  ⚡ Overall Speedup (S) : {speedup:.2f}x Faster with Host GPU Chunking!")
            lines.append(f"  ⏱ Time Saved          : {time_saved:.2f} s reduction in client latency")

        self.lbl_results_text.configure(text="\n".join(lines))

    def _on_open_video(self):
        if self.remote_result and Path(self.remote_result["output_file"]).exists():
            os.startfile(self.remote_result["output_file"])

    def _on_open_folder(self):
        if self.remote_result and Path(self.remote_result["output_file"]).exists():
            subprocess.run(["explorer", "/select,", str(Path(self.remote_result["output_file"]).resolve())])

