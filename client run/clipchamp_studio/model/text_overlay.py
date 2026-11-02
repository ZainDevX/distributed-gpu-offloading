"""
Text and Subtitle Overlay Model for Clipchamp Video Editor.
Generates compliant FFmpeg drawtext filter syntax and handles timing/positioning.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TextOverlay:
    id: str = field(default_factory=lambda: f"txt-{uuid.uuid4().hex[:8]}")
    text: str = "TITLE TEXT"
    timeline_start: float = 0.0
    timeline_end: float = 5.0
    position: str = "bottom_subtitle"  # "center", "top_banner", "bottom_subtitle", "lower_third"
    font_size: int = 42
    font_color: str = "white"
    box: bool = True
    box_color: str = "black@0.6"
    box_borderw: int = 12
    animation: str = "fade"  # "fade", "pop", "static"
    color: str = "#f59e0b"  # Amber badge on timeline

    @property
    def duration(self) -> float:
        return max(0.1, self.timeline_end - self.timeline_start)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "timeline_start": round(self.timeline_start, 3),
            "timeline_end": round(self.timeline_end, 3),
            "position": self.position,
            "font_size": self.font_size,
            "font_color": self.font_color,
            "box": self.box,
            "box_color": self.box_color,
            "box_borderw": self.box_borderw,
            "animation": self.animation,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextOverlay":
        return cls(
            id=data.get("id", f"txt-{uuid.uuid4().hex[:8]}"),
            text=data.get("text", "TITLE TEXT"),
            timeline_start=float(data.get("timeline_start", 0.0)),
            timeline_end=float(data.get("timeline_end", 5.0)),
            position=data.get("position", "bottom_subtitle"),
            font_size=int(data.get("font_size", 42)),
            font_color=data.get("font_color", "white"),
            box=bool(data.get("box", True)),
            box_color=data.get("box_color", "black@0.6"),
            box_borderw=int(data.get("box_borderw", 12)),
            animation=data.get("animation", "fade"),
            color=data.get("color", "#f59e0b"),
        )

    def build_drawtext_filter(
        self,
        local_start_time: float,
        local_end_time: float,
        font_file: Optional[str] = None,
    ) -> str:
        """
        Build FFmpeg drawtext expression calibrated to a local chunk window.
        local_start_time and local_end_time are in seconds relative to the chunk.
        """
        # Escape special characters for FFmpeg filter syntax
        clean_text = (
            self.text.replace("\\", "\\\\")
            .replace("'", "'\\\\''")
            .replace(":", "\\:")
            .replace("%", "\\%")
        )

        # Coordinate positioning formulas
        if self.position == "center":
            pos_x = "(w-text_w)/2"
            pos_y = "(h-text_h)/2"
        elif self.position == "top_banner":
            pos_x = "(w-text_w)/2"
            pos_y = "h*0.1"
        elif self.position == "lower_third":
            pos_x = "w*0.08"
            pos_y = "h*0.75"
        else:  # bottom_subtitle
            pos_x = "(w-text_w)/2"
            pos_y = "h*0.82"

        # Enable clause bounded to chunk
        enable_clause = f"between(t,{local_start_time:.3f},{local_end_time:.3f})"

        # Base filter parameters
        parts = [
            f"text='{clean_text}'",
            f"fontsize={self.font_size}",
            f"fontcolor={self.font_color}",
            f"x={pos_x}",
            f"y={pos_y}",
        ]

        if font_file:
            clean_font = font_file.replace("\\", "/").replace(":", "\\:")
            parts.append(f"fontfile='{clean_font}'")

        if self.box:
            parts.extend([
                "box=1",
                f"boxcolor={self.box_color}",
                f"boxborderw={self.box_borderw}",
            ])

        parts.append(f"enable='{enable_clause}'")
        return f"drawtext={':'.join(parts)}"
