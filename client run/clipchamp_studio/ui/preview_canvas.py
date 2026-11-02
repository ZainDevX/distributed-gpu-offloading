"""
Interactive Video Preview Canvas for Clipchamp Studio.
Provides real-time frame extraction, timecode display, aspect ratio framing,
and visual text overlay rendering.
"""

import subprocess
import threading
import time
from pathlib import Path
from tkinter import Canvas
from typing import Any, Callable, Dict, Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from clipchamp_studio.model.filters import CLIPCHAMP_FILTERS
from clipchamp_studio.model.project import ClipchampProject
from common.utils import format_duration, get_ffmpeg_binary


class VideoPreviewCanvas(ctk.CTkFrame):
    """Real-time video preview player with aspect ratio framing and playback controls."""

    def __init__(
        self,
        master,
        project: ClipchampProject,
        on_playhead_change: Optional[Callable[[float], None]] = None,
        **kwargs,
    ):
        super().__init__(master, corner_radius=12, fg_color="#131722", **kwargs)
        self.project = project
        self.on_playhead_change = on_playhead_change
        self.current_time = 0.0
        self.is_playing = False
        self._play_thread: Optional[threading.Thread] = None

        # Frame extraction cache
        self.frame_cache: Dict[str, Image.Image] = {}
        self.ffmpeg_bin = get_ffmpeg_binary()
        self._current_photo: Optional[ImageTk.PhotoImage] = None

        self._build_ui()

    def _build_ui(self):
        # 1. Top Header Bar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        self.lbl_title = ctk.CTkLabel(
            header,
            text="📺 PREVIEW MONITOR",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_title.pack(side="left")

        self.lbl_timecode = ctk.CTkLabel(
            header,
            text="00:00:00.00 / 00:00:00.00",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#e2e8f0",
        )
        self.lbl_timecode.pack(side="right")

        # 2. Canvas Display
        self.canvas_width = 640
        self.canvas_height = 360
        self.canvas = Canvas(
            self,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="#090b10",
            highlightthickness=1,
            highlightbackground="#1e293b",
        )
        self.canvas.pack(padx=12, pady=6, expand=True)

        # 3. Transport Controls Row
        ctrl_row = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=12, pady=(4, 10))

        # Seek Bar Slider
        self.seek_slider = ctk.CTkSlider(
            ctrl_row,
            from_=0.0,
            to=max(1.0, self.project.total_duration),
            command=self._on_slider_seek,
            progress_color="#6366f1",
            button_color="#818cf8",
        )
        self.seek_slider.set(0.0)
        self.seek_slider.pack(fill="x", pady=(0, 6))

        # Button Group
        btn_box = ctk.CTkFrame(ctrl_row, fg_color="transparent")
        btn_box.pack()

        self.btn_rw = ctk.CTkButton(
            btn_box,
            text="⏪ -1s",
            width=65,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.seek_relative(-1.0),
        )
        self.btn_rw.pack(side="left", padx=4)

        self.btn_play = ctk.CTkButton(
            btn_box,
            text="▶ PLAY",
            width=90,
            height=28,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self.toggle_playback,
        )
        self.btn_play.pack(side="left", padx=6)

        self.btn_ff = ctk.CTkButton(
            btn_box,
            text="+1s ⏩",
            width=65,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.seek_relative(1.0),
        )
        self.btn_ff.pack(side="left", padx=4)

        self.btn_reset = ctk.CTkButton(
            btn_box,
            text="⏮ Start",
            width=65,
            height=28,
            fg_color="#1e293b",
            hover_color="#334155",
            command=lambda: self.seek_to(0.0),
        )
        self.btn_reset.pack(side="left", padx=4)

        # Initial render
        self.render_frame_at(0.0)

    def set_project(self, project: ClipchampProject):
        self.project = project
        max_d = max(1.0, self.project.total_duration)
        self.seek_slider.configure(to=max_d)
        self.render_frame_at(self.current_time)

    def seek_to(self, target_time: float):
        total_d = self.project.total_duration
        self.current_time = max(0.0, min(total_d, target_time))
        self.seek_slider.set(self.current_time)
        self.render_frame_at(self.current_time)
        if self.on_playhead_change:
            self.on_playhead_change(self.current_time)

    def seek_relative(self, delta_seconds: float):
        self.seek_to(self.current_time + delta_seconds)

    def _on_slider_seek(self, val):
        self.seek_to(float(val))

    def toggle_playback(self):
        if self.is_playing:
            self.is_playing = False
            self.btn_play.configure(text="▶ PLAY", fg_color="#6366f1")
        else:
            self.is_playing = True
            self.btn_play.configure(text="⏸ PAUSE", fg_color="#ef4444")
            self._play_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self._play_thread.start()

    def _playback_loop(self):
        fps = 15  # 15 fps preview playback
        frame_interval = 1.0 / fps
        while self.is_playing:
            start_t = time.time()
            new_t = self.current_time + frame_interval
            if new_t >= self.project.total_duration:
                self.current_time = 0.0
                self.is_playing = False
                self.after(0, lambda: self.btn_play.configure(text="▶ PLAY", fg_color="#6366f1"))
                self.after(0, lambda: self.seek_to(0.0))
                break

            self.current_time = new_t
            self.after(0, lambda t=self.current_time: self._update_playhead_from_loop(t))
            elapsed = time.time() - start_t
            sleep_time = max(0.01, frame_interval - elapsed)
            time.sleep(sleep_time)

    def _update_playhead_from_loop(self, t: float):
        self.seek_slider.set(t)
        self.render_frame_at(t)
        if self.on_playhead_change:
            self.on_playhead_change(t)

    def render_frame_at(self, timeline_time: float):
        """Render snapshot preview of the composition at `timeline_time`."""
        total_dur = self.project.total_duration
        self.lbl_timecode.configure(
            text=f"{format_duration(timeline_time)} / {format_duration(total_dur)}"
        )

        # 1. Base Image
        w, h = self.canvas_width, self.canvas_height
        img = Image.new("RGBA", (w, h), (10, 14, 20, 255))
        draw = ImageDraw.Draw(img)

        # 2. Find active video clip
        active_clip = None
        for clip in self.project.video_clips:
            if clip.timeline_start <= timeline_time <= clip.timeline_end:
                active_clip = clip
                break

        if active_clip and Path(active_clip.source_path).exists():
            # Calculate source time offset
            dt_timeline = timeline_time - active_clip.timeline_start
            src_time = active_clip.trim_start + (dt_timeline * active_clip.speed)

            frame_img = self._extract_source_frame(active_clip.source_path, src_time)
            if frame_img:
                # Apply simulated filter tint
                frame_img = self._apply_preview_filter(frame_img, active_clip.filter_name)
                # Aspect ratio fit & center
                frame_img.thumbnail((w, h), Image.Resampling.LANCZOS)
                paste_x = (w - frame_img.width) // 2
                paste_y = (h - frame_img.height) // 2
                img.paste(frame_img, (paste_x, paste_y))

                # Overlay clip info watermark
                tag = f"🎞 {active_clip.name} [{active_clip.filter_name}] ({active_clip.speed}x)"
                draw.text((paste_x + 10, paste_y + 10), tag, fill="#38bdf8")
        else:
            # Draw placeholder canvas
            draw.text(
                (w // 2 - 80, h // 2 - 10),
                "⏹ [NO VIDEO AT PLAYHEAD]",
                fill="#475569",
            )

        # 3. Render active Text Overlays
        for txt in self.project.text_overlays:
            if txt.timeline_start <= timeline_time <= txt.timeline_end:
                self._draw_text_overlay(draw, txt, w, h)

        # 4. Push to Canvas
        self._current_photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._current_photo, anchor="nw")

    def _extract_source_frame(self, file_path: str, timestamp_sec: float) -> Optional[Image.Image]:
        """Extract a single frame from video at `timestamp_sec`."""
        cache_key = f"{file_path}_{int(timestamp_sec * 2)}"  # cache at 0.5s granularity
        if cache_key in self.frame_cache:
            return self.frame_cache[cache_key]

        try:
            cmd = [
                self.ffmpeg_bin,
                "-ss", f"{timestamp_sec:.2f}",
                "-i", file_path,
                "-frames:v", "1",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-",
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
            if res.returncode == 0 and res.stdout:
                import io
                fimg = Image.open(io.BytesIO(res.stdout)).convert("RGBA")
                if len(self.frame_cache) > 40:
                    self.frame_cache.pop(next(iter(self.frame_cache)))
                self.frame_cache[cache_key] = fimg
                return fimg
        except Exception:
            pass
        return None

    def _apply_preview_filter(self, img: Image.Image, filter_name: str) -> Image.Image:
        """Simulate aesthetic filter in Pillow for instant live UI feedback."""
        if filter_name == "Vivid":
            from PIL import ImageEnhance
            return ImageEnhance.Color(img).enhance(1.4)
        elif filter_name == "Warm Cinematic":
            r, g, b, a = img.split()
            r = r.point(lambda i: min(255, int(i * 1.15)))
            b = b.point(lambda i: int(i * 0.88))
            return Image.merge("RGBA", (r, g, b, a))
        elif filter_name == "Cool Cyberpunk":
            r, g, b, a = img.split()
            b = b.point(lambda i: min(255, int(i * 1.25)))
            r = r.point(lambda i: int(i * 0.85))
            return Image.merge("RGBA", (r, g, b, a))
        elif filter_name == "Noir B&W":
            gray = img.convert("L").convert("RGBA")
            return gray
        elif filter_name == "Vintage Sepia":
            gray = img.convert("L")
            sepia = Image.new("RGBA", img.size, (255, 240, 192, 0))
            return Image.blend(gray.convert("RGBA"), sepia, 0.25)
        return img

    def _draw_text_overlay(self, draw: ImageDraw.ImageDraw, txt, w: int, h: int):
        """Render text banner or subtitle onto preview image."""
        text = txt.text
        # Positioning
        font_size = max(16, int(txt.font_size * 0.6))
        # Estimate bounding box
        text_w = len(text) * (font_size * 0.55)
        text_h = font_size * 1.3

        if txt.position == "center":
            x = (w - text_w) // 2
            y = (h - text_h) // 2
        elif txt.position == "top_banner":
            x = (w - text_w) // 2
            y = h * 0.1
        elif txt.position == "lower_third":
            x = w * 0.08
            y = h * 0.72
        else:  # bottom_subtitle
            x = (w - text_w) // 2
            y = h * 0.82

        # Draw background box if enabled
        if txt.box:
            pad = 6
            draw.rectangle(
                [x - pad, y - pad, x + text_w + pad, y + text_h + pad],
                fill=(0, 0, 0, 180),
            )

        draw.text((x, y), text, fill=txt.font_color)
