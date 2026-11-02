"""
Clipchamp Project Data Model.
Manages composition timeline, media assets, text overlays, audio tracks, and JSON serialization.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clipchamp_studio.model.clip import AudioClip, VideoClip
from clipchamp_studio.model.text_overlay import TextOverlay
from common.utils import calculate_sha256, probe_media_file

ASPECT_RATIOS = {
    "16:9 (Landscape)": (1920, 1080),
    "9:16 (Shorts/TikTok)": (1080, 1920),
    "1:1 (Square Instagram)": (1080, 1080),
    "4:3 (Classic)": (1440, 1080),
}


@dataclass
class ClipchampProject:
    project_id: str = field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:10]}")
    project_name: str = "Untitled Clipchamp Project"
    aspect_ratio_name: str = "16:9 (Landscape)"
    resolution: Tuple[int, int] = (1920, 1080)
    fps: int = 30
    video_clips: List[VideoClip] = field(default_factory=list)
    audio_clips: List[AudioClip] = field(default_factory=list)
    text_overlays: List[TextOverlay] = field(default_factory=list)
    export_codec: str = "auto_detect"
    export_bitrate: str = "5000k"
    use_chunking: bool = True
    chunk_duration: float = 6.0  # Seconds per temporal render chunk
    last_saved_path: Optional[str] = None

    @property
    def total_duration(self) -> float:
        """Total duration of the composition timeline."""
        max_t = 0.0
        for clip in self.video_clips:
            max_t = max(max_t, clip.timeline_end)
        for aud in self.audio_clips:
            max_t = max(max_t, aud.timeline_end)
        for txt in self.text_overlays:
            max_t = max(max_t, txt.timeline_end)
        return max_t

    def set_aspect_ratio(self, ratio_name: str):
        if ratio_name in ASPECT_RATIOS:
            self.aspect_ratio_name = ratio_name
            self.resolution = ASPECT_RATIOS[ratio_name]

    def add_video_clip_from_file(
        self,
        file_path: Path,
        timeline_start: Optional[float] = None,
        name: Optional[str] = None,
    ) -> VideoClip:
        """Probe media file and append video clip to the timeline."""
        file_path = Path(file_path)
        meta = probe_media_file(file_path)
        src_dur = float(meta.get("duration_seconds", 5.0))
        if src_dur <= 0.0:
            src_dur = 5.0

        if timeline_start is None:
            # Place after latest video clip
            timeline_start = 0.0
            for c in self.video_clips:
                timeline_start = max(timeline_start, c.timeline_end)

        # Asset SHA-256 for deduplication
        asset_sha = calculate_sha256(file_path)

        clip = VideoClip(
            name=name or file_path.name,
            source_path=str(file_path.resolve()),
            asset_id=asset_sha,
            source_duration=src_dur,
            trim_start=0.0,
            trim_end=src_dur,
            timeline_start=timeline_start,
        )
        self.video_clips.append(clip)
        return clip

    def add_audio_clip_from_file(
        self,
        file_path: Path,
        timeline_start: Optional[float] = None,
        name: Optional[str] = None,
    ) -> AudioClip:
        file_path = Path(file_path)
        meta = probe_media_file(file_path)
        src_dur = float(meta.get("duration_seconds", 10.0))
        if src_dur <= 0.0:
            src_dur = 10.0

        if timeline_start is None:
            timeline_start = 0.0
            for a in self.audio_clips:
                timeline_start = max(timeline_start, a.timeline_end)

        asset_sha = calculate_sha256(file_path)

        aud = AudioClip(
            name=name or file_path.name,
            source_path=str(file_path.resolve()),
            asset_id=asset_sha,
            source_duration=src_dur,
            trim_start=0.0,
            trim_end=src_dur,
            timeline_start=timeline_start,
        )
        self.audio_clips.append(aud)
        return aud

    def add_text_overlay(
        self,
        text: str = "TITLE BANNER",
        timeline_start: float = 0.0,
        duration: float = 4.0,
        position: str = "bottom_subtitle",
    ) -> TextOverlay:
        overlay = TextOverlay(
            text=text,
            timeline_start=timeline_start,
            timeline_end=timeline_start + duration,
            position=position,
        )
        self.text_overlays.append(overlay)
        return overlay

    def split_video_clip(self, clip_id: str, timeline_time: float) -> bool:
        """Split targeted video clip at timeline_time into two clips."""
        for idx, clip in enumerate(self.video_clips):
            if clip.id == clip_id:
                res = clip.split_at(timeline_time)
                if res:
                    c1, c2 = res
                    self.video_clips[idx] = c1
                    self.video_clips.insert(idx + 1, c2)
                    return True
                return False
        return False

    def remove_item(self, item_id: str) -> bool:
        """Remove any clip or overlay by id."""
        for i, c in enumerate(self.video_clips):
            if c.id == item_id:
                self.video_clips.pop(i)
                return True
        for i, a in enumerate(self.audio_clips):
            if a.id == item_id:
                self.audio_clips.pop(i)
                return True
        for i, t in enumerate(self.text_overlays):
            if t.id == item_id:
                self.text_overlays.pop(i)
                return True
        return False

    def find_item_by_id(self, item_id: str) -> Optional[Any]:
        for c in self.video_clips:
            if c.id == item_id:
                return c
        for a in self.audio_clips:
            if a.id == item_id:
                return a
        for t in self.text_overlays:
            if t.id == item_id:
                return t
        return None

    def get_required_assets(self) -> List[Dict[str, Any]]:
        """
        Collect unique media assets required to render this project.
        Returns list of metadata dicts with sha256, path, size, filename.
        """
        assets: Dict[str, Dict[str, Any]] = {}
        for clip in self.video_clips:
            p = Path(clip.source_path)
            if p.exists() and clip.asset_id:
                if clip.asset_id not in assets:
                    assets[clip.asset_id] = {
                        "asset_id": clip.asset_id,
                        "sha256": clip.asset_id,
                        "filename": p.name,
                        "local_path": str(p.resolve()),
                        "size_bytes": os.path.getsize(p),
                        "type": "video",
                    }
        for aud in self.audio_clips:
            p = Path(aud.source_path)
            if p.exists() and aud.asset_id:
                if aud.asset_id not in assets:
                    assets[aud.asset_id] = {
                        "asset_id": aud.asset_id,
                        "sha256": aud.asset_id,
                        "filename": p.name,
                        "local_path": str(p.resolve()),
                        "size_bytes": os.path.getsize(p),
                        "type": "audio",
                    }
        return list(assets.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "aspect_ratio_name": self.aspect_ratio_name,
            "resolution": list(self.resolution),
            "fps": self.fps,
            "total_duration": round(self.total_duration, 3),
            "export_codec": self.export_codec,
            "export_bitrate": self.export_bitrate,
            "use_chunking": self.use_chunking,
            "chunk_duration": round(self.chunk_duration, 2),
            "video_clips": [c.to_dict() for c in self.video_clips],
            "audio_clips": [a.to_dict() for a in self.audio_clips],
            "text_overlays": [t.to_dict() for t in self.text_overlays],
            "assets": self.get_required_assets(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClipchampProject":
        res = tuple(data.get("resolution", [1920, 1080]))
        proj = cls(
            project_id=data.get("project_id", f"proj-{uuid.uuid4().hex[:10]}"),
            project_name=data.get("project_name", "Untitled Clipchamp Project"),
            aspect_ratio_name=data.get("aspect_ratio_name", "16:9 (Landscape)"),
            resolution=res,
            fps=int(data.get("fps", 30)),
            export_codec=data.get("export_codec", "auto_detect"),
            export_bitrate=data.get("export_bitrate", "5000k"),
            use_chunking=bool(data.get("use_chunking", True)),
            chunk_duration=float(data.get("chunk_duration", 6.0)),
        )
        proj.video_clips = [VideoClip.from_dict(c) for c in data.get("video_clips", [])]
        proj.audio_clips = [AudioClip.from_dict(a) for a in data.get("audio_clips", [])]
        proj.text_overlays = [TextOverlay.from_dict(t) for t in data.get("text_overlays", [])]
        return proj

    def save_to_json(self, file_path: Path) -> Path:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self.last_saved_path = str(p.resolve())
        return p

    @classmethod
    def load_from_json(cls, file_path: Path) -> "ClipchampProject":
        p = Path(file_path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        proj = cls.from_dict(data)
        proj.last_saved_path = str(p.resolve())
        return proj

