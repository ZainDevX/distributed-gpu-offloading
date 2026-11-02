"""
Media Pool & Asset Bin Widget for Clipchamp Studio.
Allows importing local video clips, audio tracks, generating synthetic media,
and adding clips to the multi-track timeline.
"""

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, List, Optional

import customtkinter as ctk

from clipchamp_studio.model.project import ClipchampProject
from common.config import ALLOWED_EXTENSIONS, TEST_MEDIA_DIR
from common.utils import format_bytes, format_duration, probe_media_file
from scripts.generate_test_media import generate_synthetic_video


class MediaPoolWidget(ctk.CTkFrame):
    """Left-side media drawer for importing assets and adding clips to timeline."""

    def __init__(
        self,
        master,
        project: ClipchampProject,
        on_clip_added: Optional[Callable[[], None]] = None,
        get_playhead_time: Optional[Callable[[], float]] = None,
        **kwargs,
    ):
        super().__init__(master, corner_radius=12, fg_color="#181e29", **kwargs)
        self.project = project
        self.on_clip_added = on_clip_added
        self.get_playhead_time = get_playhead_time or (lambda: 0.0)

        # Asset inventory
        self.pool_files: List[Path] = []

        self._build_ui()
        self._load_default_media()

    def _build_ui(self):
        # 1. Header
        lbl = ctk.CTkLabel(
            self,
            text="📁 MEDIA LIBRARY & ASSETS",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        )
        lbl.pack(anchor="w", padx=12, pady=(10, 6))

        # 2. Action Buttons
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(fill="x", padx=8, pady=(0, 6))

        self.btn_import_video = ctk.CTkButton(
            btn_box,
            text="🎬 Import Video...",
            height=28,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._on_import_video,
        )
        self.btn_import_video.pack(fill="x", pady=2)

        self.btn_import_audio = ctk.CTkButton(
            btn_box,
            text="🎵 Import Audio...",
            height=28,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._on_import_audio,
        )
        self.btn_import_audio.pack(fill="x", pady=2)

        self.btn_add_text = ctk.CTkButton(
            btn_box,
            text="🔤 Add Title Overlay",
            height=28,
            fg_color="#f59e0b",
            hover_color="#d97706",
            command=self._on_add_text_overlay,
        )
        self.btn_add_text.pack(fill="x", pady=2)

        self.btn_gen_samples = ctk.CTkButton(
            btn_box,
            text="⚡ Generate Sample Clips",
            height=26,
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._on_generate_sample_clips,
        )
        self.btn_gen_samples.pack(fill="x", pady=2)

        # 3. Asset Cards Scrollable Container
        lbl_list = ctk.CTkLabel(
            self,
            text="Available Assets in Pool:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8",
        )
        lbl_list.pack(anchor="w", padx=12, pady=(4, 2))

        self.list_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_container.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    def _load_default_media(self):
        """Pre-populate pool with any media found in test_media/."""
        if TEST_MEDIA_DIR.exists():
            for f in TEST_MEDIA_DIR.glob("*.mp4"):
                if f not in self.pool_files:
                    self.pool_files.append(f)
        self.refresh_list()

    def set_project(self, project: ClipchampProject):
        self.project = project
        self.refresh_list()

    def refresh_list(self):
        """Render asset cards in the media pool list."""
        for w in self.list_container.winfo_children():
            w.destroy()

        if not self.pool_files:
            ctk.CTkLabel(
                self.list_container,
                text="No assets loaded.\nClick 'Import Video' or 'Generate Sample Clips' above.",
                font=ctk.CTkFont(size=11),
                text_color="#64748b",
                justify="center",
            ).pack(pady=20)
            return

        for p in self.pool_files:
            card = ctk.CTkFrame(self.list_container, fg_color="#131722", corner_radius=8)
            card.pack(fill="x", pady=3)

            meta = probe_media_file(p)
            dur = meta.get("duration_seconds", 0.0)
            res = f"{meta.get('width')}x{meta.get('height')}" if meta.get("width") else "Audio"

            # Info text
            ctk.CTkLabel(
                card,
                text=p.name,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#f1f5f9",
            ).pack(anchor="w", padx=8, pady=(4, 0))

            ctk.CTkLabel(
                card,
                text=f"{res} | {format_duration(dur)} | {format_bytes(p.stat().st_size)}",
                font=ctk.CTkFont(family="Consolas", size=9),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=8, pady=(0, 4))

            # Add to timeline button
            btn_add = ctk.CTkButton(
                card,
                text="➕ Add to Timeline",
                height=24,
                fg_color="#334155",
                hover_color="#6366f1",
                command=lambda f=p: self._add_asset_to_timeline(f),
            )
            btn_add.pack(fill="x", padx=8, pady=(0, 6))

    def _on_import_video(self):
        filetypes = [
            ("Video Files", "*.mp4 *.mkv *.mov *.avi *.webm *.ts"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(title="Select Video to Import", filetypes=filetypes)
        if chosen:
            p = Path(chosen)
            if p not in self.pool_files:
                self.pool_files.append(p)
            self._add_asset_to_timeline(p)
            self.refresh_list()

    def _on_import_audio(self):
        filetypes = [
            ("Audio Files", "*.mp3 *.wav *.aac *.m4a *.flac"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(title="Select Audio to Import", filetypes=filetypes)
        if chosen:
            p = Path(chosen)
            if p not in self.pool_files:
                self.pool_files.append(p)
            self.project.add_audio_clip_from_file(p, timeline_start=self.get_playhead_time())
            if self.on_clip_added:
                self.on_clip_added()
            self.refresh_list()

    def _on_add_text_overlay(self):
        playhead = self.get_playhead_time()
        self.project.add_text_overlay(
            text="CLIPCHAMP TITLE",
            timeline_start=playhead,
            duration=3.5,
            position="bottom_subtitle",
        )
        if self.on_clip_added:
            self.on_clip_added()

    def _on_generate_sample_clips(self):
        try:
            p = generate_synthetic_video("720p", duration_sec=5, out_dir=TEST_MEDIA_DIR)
            if p not in self.pool_files:
                self.pool_files.append(p)
            self._add_asset_to_timeline(p)
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("Sample Generator Error", str(e))

    def _add_asset_to_timeline(self, p: Path):
        meta = probe_media_file(p)
        if meta.get("width", 0) > 0:
            self.project.add_video_clip_from_file(p)
        else:
            self.project.add_audio_clip_from_file(p)
        if self.on_clip_added:
            self.on_clip_added()
