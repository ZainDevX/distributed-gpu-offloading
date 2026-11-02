"""
Property Inspector Widget for Clipchamp Studio.
Allows interactive editing of Clip trims, playback speeds, filters, audio volume,
rotation, and title overlays.
"""

from typing import Any, Callable, Dict, Optional

import customtkinter as ctk

from clipchamp_studio.model.filters import get_all_filter_names
from clipchamp_studio.model.project import ASPECT_RATIOS, ClipchampProject


class InspectorWidget(ctk.CTkFrame):
    """Right-side properties inspector for selected clip or global project."""

    def __init__(
        self,
        master,
        project: ClipchampProject,
        on_project_modified: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, corner_radius=12, fg_color="#181e29", **kwargs)
        self.project = project
        self.on_project_modified = on_project_modified
        self.selected_item = None
        self.selected_type = None

        self._build_ui()

    def _build_ui(self):
        # Header
        self.lbl_header = ctk.CTkLabel(
            self,
            text="⚙️ PROPERTIES & CONTROLS",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_header.pack(anchor="w", padx=12, pady=(10, 6))

        # Dynamic Content Container
        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Default: Show Project Settings
        self.show_project_settings()

    def set_project(self, project: ClipchampProject):
        self.project = project
        self.show_project_settings()

    def select_item(self, item_id: Optional[str], item_type: Optional[str]):
        """Load selected clip or overlay into inspector."""
        if not item_id:
            self.show_project_settings()
            return

        item = self.project.find_item_by_id(item_id)
        if not item:
            self.show_project_settings()
            return

        self.selected_item = item
        self.selected_type = item_type

        # Clear container
        for w in self.container.winfo_children():
            w.destroy()

        if item_type == "video":
            self._build_video_clip_controls(item)
        elif item_type == "text":
            self._build_text_overlay_controls(item)
        elif item_type == "audio":
            self._build_audio_clip_controls(item)

    def show_project_settings(self):
        """Display overall project composition settings when nothing is selected."""
        self.selected_item = None
        self.selected_type = None

        for w in self.container.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self.container,
            text="📽 Project Composition",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e2e8f0",
        ).pack(anchor="w", pady=(4, 2))

        # Project Name
        ctk.CTkLabel(self.container, text="Project Name:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.entry_pname = ctk.CTkEntry(self.container, height=28)
        self.entry_pname.insert(0, self.project.project_name)
        self.entry_pname.pack(fill="x", pady=(0, 8))
        self.entry_pname.bind("<KeyRelease>", self._on_name_change)

        # Aspect Ratio
        ctk.CTkLabel(self.container, text="Aspect Ratio:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.combo_ratio = ctk.CTkComboBox(
            self.container,
            values=list(ASPECT_RATIOS.keys()),
            command=self._on_ratio_change,
        )
        self.combo_ratio.set(self.project.aspect_ratio_name)
        self.combo_ratio.pack(fill="x", pady=(0, 8))

        # Chunk Duration
        ctk.CTkLabel(self.container, text="Temporal Chunk Size:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.combo_chunks = ctk.CTkComboBox(
            self.container,
            values=["4.0s (Fast parallel)", "6.0s (Recommended)", "8.0s", "10.0s", "15.0s"],
            command=self._on_chunk_dur_change,
        )
        self.combo_chunks.set(f"{self.project.chunk_duration:.1f}s")
        self.combo_chunks.pack(fill="x", pady=(0, 10))

        # Summary Metrics Box
        summary = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        summary.pack(fill="x", pady=6)

        tot_dur = self.project.total_duration
        c_count = max(1, int((tot_dur + self.project.chunk_duration - 0.01) // self.project.chunk_duration)) if self.project.use_chunking else 1

        ctk.CTkLabel(
            summary,
            text=f"⏱ Total Timeline : {tot_dur:.2f}s\n"
                 f"🎞 Video Clips   : {len(self.project.video_clips)}\n"
                 f"🔤 Title Overlays: {len(self.project.text_overlays)}\n"
                 f"🎵 Audio Tracks  : {len(self.project.audio_clips)}\n"
                 f"🧩 Host Chunks   : {c_count} Chunk(s)",
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left",
            text_color="#94a3b8",
        ).pack(padx=10, pady=8, anchor="w")

    def _on_name_change(self, event):
        self.project.project_name = self.entry_pname.get()

    def _on_ratio_change(self, choice):
        self.project.set_aspect_ratio(choice)
        if self.on_project_modified:
            self.on_project_modified()

    def _on_chunk_dur_change(self, choice):
        import re
        m = re.search(r"([0-9.]+)", choice)
        if m:
            self.project.chunk_duration = float(m.group(1))

    # -------------------------------------------------------------
    # Video Clip Controls
    # -------------------------------------------------------------
    def _build_video_clip_controls(self, clip):
        ctk.CTkLabel(
            self.container,
            text=f"🎬 Video Clip: {clip.name}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#818cf8",
        ).pack(anchor="w", pady=(0, 6))

        # 1. Trimming
        trim_card = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        trim_card.pack(fill="x", pady=4)
        ctk.CTkLabel(trim_card, text="✂️ Trim Start (In) & End (Out):", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))

        # Trim in
        ctk.CTkLabel(trim_card, text=f"Start: {clip.trim_start:.2f}s", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=8)
        s_in = ctk.CTkSlider(
            trim_card, from_=0.0, to=max(0.1, clip.trim_end - 0.2),
            command=lambda v: self._update_trim_start(clip, float(v)),
        )
        s_in.set(clip.trim_start)
        s_in.pack(fill="x", padx=8, pady=(0, 4))

        # Trim out
        ctk.CTkLabel(trim_card, text=f"End: {clip.trim_end:.2f}s (Source: {clip.source_duration:.2f}s)", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=8)
        s_out = ctk.CTkSlider(
            trim_card, from_=clip.trim_start + 0.2, to=max(0.5, clip.source_duration),
            command=lambda v: self._update_trim_end(clip, float(v)),
        )
        s_out.set(clip.trim_end)
        s_out.pack(fill="x", padx=8, pady=(0, 6))

        # 2. Playback Speed Multiplier
        speed_card = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        speed_card.pack(fill="x", pady=4)
        ctk.CTkLabel(speed_card, text="⚡ Playback Speed:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))

        row_sp = ctk.CTkFrame(speed_card, fg_color="transparent")
        row_sp.pack(fill="x", padx=6, pady=(0, 6))
        for sp in [0.5, 1.0, 1.5, 2.0]:
            btn = ctk.CTkButton(
                row_sp, text=f"{sp}x", width=42, height=24,
                fg_color="#6366f1" if clip.speed == sp else "#1e293b",
                command=lambda s=sp: self._set_clip_speed(clip, s),
            )
            btn.pack(side="left", padx=2)

        # 3. Aesthetic Filters
        filter_card = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        filter_card.pack(fill="x", pady=4)
        ctk.CTkLabel(filter_card, text="✨ Clipchamp Aesthetic Filter:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))

        combo_filter = ctk.CTkComboBox(
            filter_card,
            values=get_all_filter_names(),
            command=lambda c: self._set_clip_filter(clip, c),
        )
        combo_filter.set(clip.filter_name)
        combo_filter.pack(fill="x", padx=8, pady=(0, 6))

        # 4. Rotation & Flip
        trans_card = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        trans_card.pack(fill="x", pady=4)
        ctk.CTkLabel(trans_card, text="🔄 Transform & Orientation:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))

        row_tr = ctk.CTkFrame(trans_card, fg_color="transparent")
        row_tr.pack(fill="x", padx=6, pady=(0, 6))

        btn_rot = ctk.CTkButton(
            row_tr, text="⟳ Rotate 90°", width=85, height=24,
            command=lambda: self._rotate_clip(clip),
        )
        btn_rot.pack(side="left", padx=3)

        btn_flip = ctk.CTkButton(
            row_tr, text="⇄ Mirror", width=75, height=24,
            command=lambda: self._flip_clip(clip),
        )
        btn_flip.pack(side="left", padx=3)

        # 5. Volume
        vol_card = ctk.CTkFrame(self.container, fg_color="#131722", corner_radius=8)
        vol_card.pack(fill="x", pady=4)
        ctk.CTkLabel(vol_card, text=f"🔊 Volume: {int(clip.volume * 100)}%", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))

        s_vol = ctk.CTkSlider(
            vol_card, from_=0.0, to=2.0,
            command=lambda v: self._set_clip_volume(clip, float(v)),
        )
        s_vol.set(clip.volume)
        s_vol.pack(fill="x", padx=8, pady=(0, 6))

    def _update_trim_start(self, clip, val):
        clip.trim_start = val
        if self.on_project_modified:
            self.on_project_modified()

    def _update_trim_end(self, clip, val):
        clip.trim_end = val
        if self.on_project_modified:
            self.on_project_modified()

    def _set_clip_speed(self, clip, speed):
        clip.speed = speed
        self._build_video_clip_controls(clip)
        if self.on_project_modified:
            self.on_project_modified()

    def _set_clip_filter(self, clip, filter_name):
        clip.filter_name = filter_name
        if self.on_project_modified:
            self.on_project_modified()

    def _rotate_clip(self, clip):
        clip.rotation = (clip.rotation + 90) % 360
        if self.on_project_modified:
            self.on_project_modified()

    def _flip_clip(self, clip):
        clip.flip_h = not clip.flip_h
        if self.on_project_modified:
            self.on_project_modified()

    def _set_clip_volume(self, clip, vol):
        clip.volume = vol

    # -------------------------------------------------------------
    # Text Overlay Controls
    # -------------------------------------------------------------
    def _build_text_overlay_controls(self, txt):
        ctk.CTkLabel(
            self.container,
            text="🔤 Title & Subtitle Overlay",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#f59e0b",
        ).pack(anchor="w", pady=(0, 6))

        # Text Content
        ctk.CTkLabel(self.container, text="Text String:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry_txt = ctk.CTkEntry(self.container)
        entry_txt.insert(0, txt.text)
        entry_txt.pack(fill="x", pady=(0, 6))
        entry_txt.bind("<KeyRelease>", lambda e: self._update_overlay_text(txt, entry_txt.get()))

        # Position Preset
        ctk.CTkLabel(self.container, text="Screen Position:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        combo_pos = ctk.CTkComboBox(
            self.container,
            values=["bottom_subtitle", "center", "top_banner", "lower_third"],
            command=lambda p: self._update_overlay_pos(txt, p),
        )
        combo_pos.set(txt.position)
        combo_pos.pack(fill="x", pady=(0, 6))

        # Font Size
        ctk.CTkLabel(self.container, text=f"Font Size ({txt.font_size}pt):", font=ctk.CTkFont(size=11)).pack(anchor="w")
        s_size = ctk.CTkSlider(
            self.container, from_=20, to=80,
            command=lambda v: self._update_overlay_size(txt, int(float(v))),
        )
        s_size.set(txt.font_size)
        s_size.pack(fill="x", pady=(0, 6))

        # Font Color
        ctk.CTkLabel(self.container, text="Font Color:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        combo_col = ctk.CTkComboBox(
            self.container,
            values=["white", "yellow", "cyan", "red", "#38bdf8", "#10b981"],
            command=lambda c: self._update_overlay_col(txt, c),
        )
        combo_col.set(txt.font_color)
        combo_col.pack(fill="x", pady=(0, 6))

    def _update_overlay_text(self, txt, new_text):
        txt.text = new_text
        if self.on_project_modified:
            self.on_project_modified()

    def _update_overlay_pos(self, txt, pos):
        txt.position = pos
        if self.on_project_modified:
            self.on_project_modified()

    def _update_overlay_size(self, txt, sz):
        txt.font_size = sz
        if self.on_project_modified:
            self.on_project_modified()

    def _update_overlay_col(self, txt, col):
        txt.font_color = col
        if self.on_project_modified:
            self.on_project_modified()

    # -------------------------------------------------------------
    # Audio Clip Controls
    # -------------------------------------------------------------
    def _build_audio_clip_controls(self, aud):
        ctk.CTkLabel(
            self.container,
            text=f"🎵 Audio Track: {aud.name}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#10b981",
        ).pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(self.container, text=f"Volume: {int(aud.volume * 100)}%", font=ctk.CTkFont(size=11)).pack(anchor="w")
        s_vol = ctk.CTkSlider(
            self.container, from_=0.0, to=2.0,
            command=lambda v: setattr(aud, "volume", float(v)),
        )
        s_vol.set(aud.volume)
        s_vol.pack(fill="x", pady=(0, 6))
