"""
Interactive Multi-Track Visual Timeline for Clipchamp Studio.
Features interactive clip blocks, playhead scrubber needle, razor split tool,
and multi-track layout (Video, Text, Audio).
"""

from tkinter import Canvas
from typing import Any, Callable, Dict, Optional

import customtkinter as ctk

from clipchamp_studio.model.project import ClipchampProject


class InteractiveTimeline(ctk.CTkFrame):
    """Visual multi-track timeline editor widget with drag scrubber & razor split tool."""

    def __init__(
        self,
        master,
        project: ClipchampProject,
        on_select_item: Optional[Callable[[str, str], None]] = None,
        on_playhead_move: Optional[Callable[[float], None]] = None,
        on_split_request: Optional[Callable[[str, float], None]] = None,
        on_delete_request: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(master, corner_radius=12, fg_color="#181e29", **kwargs)
        self.project = project
        self.on_select_item = on_select_item
        self.on_playhead_move = on_playhead_move
        self.on_split_request = on_split_request
        self.on_delete_request = on_delete_request

        self.selected_item_id: Optional[str] = None
        self.selected_item_type: Optional[str] = None
        self.playhead_time = 0.0

        # Timeline scaling
        self.pixels_per_second = 35.0  # Zoom level
        self.ruler_height = 26
        self.track_height = 42
        self.track_gap = 6
        self.margin_left = 60  # Space for track labels (V1, T1, A1)

        # Mapping canvas object IDs to clip items
        self.canvas_items_map: Dict[int, Dict[str, Any]] = {}

        self._build_ui()

    def _build_ui(self):
        # 1. Timeline Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="#131722", corner_radius=8)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        lbl = ctk.CTkLabel(
            toolbar,
            text="🎞 TIMELINE TRACKS",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#94a3b8",
        )
        lbl.pack(side="left", padx=10)

        # Split tool
        self.btn_split = ctk.CTkButton(
            toolbar,
            text="✂️ Split Clip (S)",
            width=115,
            height=26,
            fg_color="#334155",
            hover_color="#475569",
            command=self._on_click_split,
        )
        self.btn_split.pack(side="left", padx=6)

        # Delete tool
        self.btn_del = ctk.CTkButton(
            toolbar,
            text="🗑️ Delete (Del)",
            width=100,
            height=26,
            fg_color="#334155",
            hover_color="#ef4444",
            command=self._on_click_delete,
        )
        self.btn_del.pack(side="left", padx=6)

        # Zoom controls
        btn_zoom_in = ctk.CTkButton(
            toolbar,
            text="🔍 +",
            width=40,
            height=26,
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.adjust_zoom(1.25),
        )
        btn_zoom_in.pack(side="right", padx=4)

        btn_zoom_out = ctk.CTkButton(
            toolbar,
            text="🔍 -",
            width=40,
            height=26,
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.adjust_zoom(0.8),
        )
        btn_zoom_out.pack(side="right", padx=4)

        # 2. Scrollable Canvas Area
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            orientation="horizontal",
            height=180,
            fg_color="#0e1219",
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        total_width = self._calc_canvas_width()
        total_height = self.ruler_height + 3 * (self.track_height + self.track_gap) + 20

        self.canvas = Canvas(
            self.scroll_frame,
            width=total_width,
            height=total_height,
            bg="#0e1219",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Mouse event bindings
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)

        # Keyboard shortcuts
        self.bind_all("<Key-s>", lambda e: self._on_click_split())
        self.bind_all("<Delete>", lambda e: self._on_click_delete())

        self.redraw()

    def _calc_canvas_width(self) -> int:
        dur = max(10.0, self.project.total_duration + 5.0)
        return int(self.margin_left + dur * self.pixels_per_second + 100)

    def set_project(self, project: ClipchampProject):
        self.project = project
        self.redraw()

    def set_playhead_time(self, t: float):
        self.playhead_time = max(0.0, t)
        self._draw_playhead()

    def adjust_zoom(self, factor: float):
        new_px = max(12.0, min(120.0, self.pixels_per_second * factor))
        self.pixels_per_second = new_px
        self.redraw()

    def redraw(self):
        """Redraw all tracks, clip blocks, labels, ruler, and playhead."""
        self.canvas.delete("all")
        self.canvas_items_map.clear()

        w = self._calc_canvas_width()
        self.canvas.configure(width=w)

        # 1. Draw Ruler
        self._draw_ruler(w)

        # 2. Draw Track Headers & Background Lanes
        y_video = self.ruler_height + 4
        y_text = y_video + self.track_height + self.track_gap
        y_audio = y_text + self.track_height + self.track_gap

        self._draw_track_lane("V1 (Video)", y_video, "#1e2433")
        self._draw_track_lane("T1 (Titles)", y_text, "#252119")
        self._draw_track_lane("A1 (Audio)", y_audio, "#182622")

        # 3. Draw Video Clips (Track V1)
        for clip in self.project.video_clips:
            self._draw_video_clip_block(clip, y_video)

        # 4. Draw Text Overlays (Track T1)
        for txt in self.project.text_overlays:
            self._draw_text_overlay_block(txt, y_text)

        # 5. Draw Audio Clips (Track A1)
        for aud in self.project.audio_clips:
            self._draw_audio_clip_block(aud, y_audio)

        # 6. Draw Playhead Needle
        self._draw_playhead()

    def _draw_ruler(self, total_w: int):
        # Ruler background
        self.canvas.create_rectangle(
            0, 0, total_w, self.ruler_height,
            fill="#141822", outline="#232a3b", width=1,
        )
        # Time tick marks every 1s / 5s
        max_sec = int((total_w - self.margin_left) / self.pixels_per_second)
        step = 1 if self.pixels_per_second >= 40 else 2 if self.pixels_per_second >= 20 else 5

        for sec in range(0, max_sec + 2, step):
            x = self.margin_left + sec * self.pixels_per_second
            is_major = (sec % 5 == 0)
            tick_h = 10 if is_major else 5
            self.canvas.create_line(x, self.ruler_height - tick_h, x, self.ruler_height, fill="#64748b")
            if is_major or self.pixels_per_second >= 50:
                self.canvas.create_text(
                    x, 8, text=f"{sec}s", fill="#94a3b8", font=("Consolas", 8),
                )

    def _draw_track_lane(self, label: str, y_top: int, bg_color: str):
        total_w = self._calc_canvas_width()
        # Track background lane
        self.canvas.create_rectangle(
            self.margin_left, y_top, total_w, y_top + self.track_height,
            fill=bg_color, outline="#1f293d", width=1,
        )
        # Track Header Pill
        self.canvas.create_rectangle(
            0, y_top, self.margin_left, y_top + self.track_height,
            fill="#111622", outline="#1f293d", width=1,
        )
        self.canvas.create_text(
            self.margin_left // 2, y_top + self.track_height // 2,
            text=label, fill="#7dd3fc", font=("Segoe UI", 8, "bold"),
        )

    def _draw_video_clip_block(self, clip, y_top: int):
        x1 = self.margin_left + clip.timeline_start * self.pixels_per_second
        x2 = self.margin_left + clip.timeline_end * self.pixels_per_second
        y1 = y_top + 3
        y2 = y_top + self.track_height - 3

        is_sel = (clip.id == self.selected_item_id)
        border_col = "#38bdf8" if is_sel else "#4338ca"
        border_w = 2 if is_sel else 1

        rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=clip.color, outline=border_col, width=border_w,
        )
        # Title text
        f_tag = f"[{clip.filter_name}] " if clip.filter_name != "Normal" else ""
        sp_tag = f"({clip.speed}x) " if clip.speed != 1.0 else ""
        text_str = f"🎬 {clip.name} {f_tag}{sp_tag}({clip.duration:.1f}s)"

        txt_id = self.canvas.create_text(
            x1 + 6, y1 + (y2 - y1) // 2,
            text=text_str, anchor="w", fill="#ffffff", font=("Segoe UI", 9, "bold"),
        )

        item_meta = {"id": clip.id, "type": "video"}
        self.canvas_items_map[rect_id] = item_meta
        self.canvas_items_map[txt_id] = item_meta

    def _draw_text_overlay_block(self, txt, y_top: int):
        x1 = self.margin_left + txt.timeline_start * self.pixels_per_second
        x2 = self.margin_left + txt.timeline_end * self.pixels_per_second
        y1 = y_top + 3
        y2 = y_top + self.track_height - 3

        is_sel = (txt.id == self.selected_item_id)
        border_col = "#38bdf8" if is_sel else "#b45309"
        border_w = 2 if is_sel else 1

        rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=txt.color, outline=border_col, width=border_w,
        )
        txt_id = self.canvas.create_text(
            x1 + 6, y1 + (y2 - y1) // 2,
            text=f"🔤 \"{txt.text}\" ({txt.duration:.1f}s)",
            anchor="w", fill="#111827", font=("Segoe UI", 9, "bold"),
        )
        item_meta = {"id": txt.id, "type": "text"}
        self.canvas_items_map[rect_id] = item_meta
        self.canvas_items_map[txt_id] = item_meta

    def _draw_audio_clip_block(self, aud, y_top: int):
        x1 = self.margin_left + aud.timeline_start * self.pixels_per_second
        x2 = self.margin_left + aud.timeline_end * self.pixels_per_second
        y1 = y_top + 3
        y2 = y_top + self.track_height - 3

        is_sel = (aud.id == self.selected_item_id)
        border_col = "#38bdf8" if is_sel else "#047857"
        border_w = 2 if is_sel else 1

        rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=aud.color, outline=border_col, width=border_w,
        )
        txt_id = self.canvas.create_text(
            x1 + 6, y1 + (y2 - y1) // 2,
            text=f"🎵 {aud.name} ({aud.duration:.1f}s)",
            anchor="w", fill="#ffffff", font=("Segoe UI", 9, "bold"),
        )
        item_meta = {"id": aud.id, "type": "audio"}
        self.canvas_items_map[rect_id] = item_meta
        self.canvas_items_map[txt_id] = item_meta

    def _draw_playhead(self):
        self.canvas.delete("playhead")
        x = self.margin_left + self.playhead_time * self.pixels_per_second
        total_h = self.ruler_height + 3 * (self.track_height + self.track_gap) + 10

        # Vertical Needle Line
        self.canvas.create_line(
            x, 0, x, total_h,
            fill="#f43f5e", width=2, tags="playhead",
        )
        # Top Needle Arrow / Head
        poly = [x - 6, 0, x + 6, 0, x, 12]
        self.canvas.create_polygon(
            poly, fill="#f43f5e", outline="#fda4af", tags="playhead",
        )

    def _on_canvas_click(self, event):
        x = event.x
        # Check if clicked on a clip
        clicked_tags = self.canvas.find_withtag("current")
        clicked_clip = None
        for tag in clicked_tags:
            if tag in self.canvas_items_map:
                clicked_clip = self.canvas_items_map[tag]
                break

        if clicked_clip:
            self.selected_item_id = clicked_clip["id"]
            self.selected_item_type = clicked_clip["type"]
            self.redraw()
            if self.on_select_item:
                self.on_select_item(self.selected_item_id, self.selected_item_type)
        else:
            # Move playhead
            self._move_playhead_to_x(x)

    def _on_canvas_drag(self, event):
        self._move_playhead_to_x(event.x)

    def _move_playhead_to_x(self, x: int):
        raw_t = (x - self.margin_left) / self.pixels_per_second
        t = max(0.0, min(self.project.total_duration, raw_t))
        self.set_playhead_time(t)
        if self.on_playhead_move:
            self.on_playhead_move(t)

    def _on_click_split(self):
        """Split selected clip at current playhead."""
        if self.selected_item_id and self.selected_item_type == "video":
            if self.on_split_request:
                self.on_split_request(self.selected_item_id, self.playhead_time)
            elif self.project.split_video_clip(self.selected_item_id, self.playhead_time):
                self.redraw()

    def _on_click_delete(self):
        """Delete selected item."""
        if self.selected_item_id:
            if self.on_delete_request:
                self.on_delete_request(self.selected_item_id)
            elif self.project.remove_item(self.selected_item_id):
                self.selected_item_id = None
                self.redraw()

