"""
Clip Model definitions for Clipchamp Studio.
Supports multi-track video trimming, speed scaling, volume, rotation, filters and slicing.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class VideoClip:
    id: str = field(default_factory=lambda: f"clip-{uuid.uuid4().hex[:8]}")
    name: str = "Video Clip"
    source_path: str = ""
    asset_id: str = ""  # SHA-256 checksum for network asset deduplication
    source_duration: float = 0.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    timeline_start: float = 0.0
    speed: float = 1.0
    volume: float = 1.0
    rotation: int = 0  # 0, 90, 180, 270 degrees
    flip_h: bool = False
    filter_name: str = "Normal"
    transition_in: str = "none"  # "none", "fade"
    transition_out: str = "none"
    color: str = "#6366f1"  # Modern Clipchamp Indigo block

    def __post_init__(self):
        if self.trim_end <= 0.0 and self.source_duration > 0.0:
            self.trim_end = self.source_duration

    @property
    def source_cut_duration(self) -> float:
        return max(0.05, self.trim_end - self.trim_start)

    @property
    def duration(self) -> float:
        """Effective playback duration on timeline accounting for speed multiplier."""
        return max(0.05, self.source_cut_duration / max(0.1, self.speed))

    @property
    def timeline_end(self) -> float:
        return self.timeline_start + self.duration

    def split_at(self, timeline_split_time: float) -> Optional[Tuple["VideoClip", "VideoClip"]]:
        """
        Split this clip at the given timeline time (Razor tool).
        Returns (first_clip, second_clip) or None if split time is out of bounds.
        """
        if timeline_split_time <= self.timeline_start + 0.1 or timeline_split_time >= self.timeline_end - 0.1:
            return None

        # Calculate time delta in timeline
        dt_timeline = timeline_split_time - self.timeline_start
        dt_source = dt_timeline * self.speed
        source_split_point = self.trim_start + dt_source

        # Clip 1: [trim_start -> source_split_point]
        clip1 = VideoClip(
            id=f"clip-{uuid.uuid4().hex[:8]}",
            name=f"{self.name} (Part 1)",
            source_path=self.source_path,
            asset_id=self.asset_id,
            source_duration=self.source_duration,
            trim_start=self.trim_start,
            trim_end=source_split_point,
            timeline_start=self.timeline_start,
            speed=self.speed,
            volume=self.volume,
            rotation=self.rotation,
            flip_h=self.flip_h,
            filter_name=self.filter_name,
            transition_in=self.transition_in,
            transition_out="none",
            color=self.color,
        )

        # Clip 2: [source_split_point -> trim_end]
        clip2 = VideoClip(
            id=f"clip-{uuid.uuid4().hex[:8]}",
            name=f"{self.name} (Part 2)",
            source_path=self.source_path,
            asset_id=self.asset_id,
            source_duration=self.source_duration,
            trim_start=source_split_point,
            trim_end=self.trim_end,
            timeline_start=timeline_split_time,
            speed=self.speed,
            volume=self.volume,
            rotation=self.rotation,
            flip_h=self.flip_h,
            filter_name=self.filter_name,
            transition_in="none",
            transition_out=self.transition_out,
            color=self.color,
        )

        return clip1, clip2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source_path": self.source_path,
            "asset_id": self.asset_id,
            "source_duration": round(self.source_duration, 3),
            "trim_start": round(self.trim_start, 3),
            "trim_end": round(self.trim_end, 3),
            "timeline_start": round(self.timeline_start, 3),
            "speed": round(self.speed, 2),
            "volume": round(self.volume, 2),
            "rotation": self.rotation,
            "flip_h": self.flip_h,
            "filter_name": self.filter_name,
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoClip":
        return cls(
            id=data.get("id", f"clip-{uuid.uuid4().hex[:8]}"),
            name=data.get("name", "Video Clip"),
            source_path=data.get("source_path", ""),
            asset_id=data.get("asset_id", ""),
            source_duration=float(data.get("source_duration", 0.0)),
            trim_start=float(data.get("trim_start", 0.0)),
            trim_end=float(data.get("trim_end", 0.0)),
            timeline_start=float(data.get("timeline_start", 0.0)),
            speed=float(data.get("speed", 1.0)),
            volume=float(data.get("volume", 1.0)),
            rotation=int(data.get("rotation", 0)),
            flip_h=bool(data.get("flip_h", False)),
            filter_name=data.get("filter_name", "Normal"),
            transition_in=data.get("transition_in", "none"),
            transition_out=data.get("transition_out", "none"),
            color=data.get("color", "#6366f1"),
        )


@dataclass
class AudioClip:
    id: str = field(default_factory=lambda: f"aud-{uuid.uuid4().hex[:8]}")
    name: str = "Audio Track"
    source_path: str = ""
    asset_id: str = ""
    source_duration: float = 0.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    timeline_start: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    loop: bool = False
    color: str = "#10b981"  # Emerald green audio block

    def __post_init__(self):
        if self.trim_end <= 0.0 and self.source_duration > 0.0:
            self.trim_end = self.source_duration

    @property
    def duration(self) -> float:
        return max(0.05, self.trim_end - self.trim_start)

    @property
    def timeline_end(self) -> float:
        return self.timeline_start + self.duration

    def split_at(self, timeline_split_time: float) -> Optional[Tuple["AudioClip", "AudioClip"]]:
        """Split audio track at given timeline time."""
        if timeline_split_time <= self.timeline_start + 0.1 or timeline_split_time >= self.timeline_end - 0.1:
            return None

        dt = timeline_split_time - self.timeline_start
        source_split = self.trim_start + dt

        aud1 = AudioClip(
            id=f"aud-{uuid.uuid4().hex[:8]}",
            name=f"{self.name} (Part 1)",
            source_path=self.source_path,
            asset_id=self.asset_id,
            source_duration=self.source_duration,
            trim_start=self.trim_start,
            trim_end=source_split,
            timeline_start=self.timeline_start,
            volume=self.volume,
            fade_in=self.fade_in,
            fade_out=0.0,
            color=self.color,
        )
        aud2 = AudioClip(
            id=f"aud-{uuid.uuid4().hex[:8]}",
            name=f"{self.name} (Part 2)",
            source_path=self.source_path,
            asset_id=self.asset_id,
            source_duration=self.source_duration,
            trim_start=source_split,
            trim_end=self.trim_end,
            timeline_start=timeline_split_time,
            volume=self.volume,
            fade_in=0.0,
            fade_out=self.fade_out,
            color=self.color,
        )
        return aud1, aud2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source_path": self.source_path,
            "asset_id": self.asset_id,
            "source_duration": round(self.source_duration, 3),
            "trim_start": round(self.trim_start, 3),
            "trim_end": round(self.trim_end, 3),
            "timeline_start": round(self.timeline_start, 3),
            "volume": round(self.volume, 2),
            "fade_in": round(self.fade_in, 2),
            "fade_out": round(self.fade_out, 2),
            "loop": self.loop,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioClip":
        return cls(
            id=data.get("id", f"aud-{uuid.uuid4().hex[:8]}"),
            name=data.get("name", "Audio Track"),
            source_path=data.get("source_path", ""),
            asset_id=data.get("asset_id", ""),
            source_duration=float(data.get("source_duration", 0.0)),
            trim_start=float(data.get("trim_start", 0.0)),
            trim_end=float(data.get("trim_end", 0.0)),
            timeline_start=float(data.get("timeline_start", 0.0)),
            volume=float(data.get("volume", 1.0)),
            fade_in=float(data.get("fade_in", 0.0)),
            fade_out=float(data.get("fade_out", 0.0)),
            loop=bool(data.get("loop", False)),
            color=data.get("color", "#10b981"),
        )

