"""
Timeline Chunking Engine for Distributed GPU Video Rendering.
Decomposes complex multi-track video timelines into independent, keyframe-aligned
temporal chunks for parallel execution and fault tolerance.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

from clipchamp_studio.model.project import ClipchampProject


@dataclass
class VideoSlice:
    clip_id: str
    name: str
    source_path: str
    asset_id: str
    local_start: float
    local_end: float
    source_trim_in: float
    source_trim_out: float
    speed: float
    volume: float
    rotation: int
    flip_h: bool
    filter_name: str
    transition_in: str
    transition_out: str


@dataclass
class TextSlice:
    overlay_id: str
    text: str
    local_start: float
    local_end: float
    position: str
    font_size: int
    font_color: str
    box: bool
    box_color: str
    box_borderw: int
    animation: str


@dataclass
class AudioSlice:
    clip_id: str
    source_path: str
    asset_id: str
    local_start: float
    local_end: float
    source_trim_in: float
    source_trim_out: float
    volume: float
    fade_in: float
    fade_out: float


@dataclass
class RenderChunk:
    chunk_index: int
    total_chunks: int
    window_start: float
    window_end: float
    duration: float
    video_slices: List[VideoSlice] = field(default_factory=list)
    text_slices: List[TextSlice] = field(default_factory=list)
    audio_slices: List[AudioSlice] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "window_start": round(self.window_start, 3),
            "window_end": round(self.window_end, 3),
            "duration": round(self.duration, 3),
            "video_slices_count": len(self.video_slices),
            "text_slices_count": len(self.text_slices),
            "audio_slices_count": len(self.audio_slices),
        }


class TimelineChunker:
    """Partitions a ClipchampProject timeline into discrete render chunks."""

    @staticmethod
    def partition_project(
        project: ClipchampProject,
        chunk_duration: float = 6.0,
    ) -> List[RenderChunk]:
        """
        Split project timeline into temporal chunks of at most `chunk_duration` seconds.
        If chunk_duration <= 0 or timeline <= chunk_duration, returns 1 monolithic chunk.
        """
        total_dur = project.total_duration
        if total_dur <= 0.05:
            # Minimal safety fallback
            total_dur = 1.0

        if chunk_duration <= 0 or total_dur <= chunk_duration:
            num_chunks = 1
            step = total_dur
        else:
            num_chunks = max(1, math.ceil(total_dur / chunk_duration))
            step = chunk_duration

        chunks: List[RenderChunk] = []

        for i in range(num_chunks):
            w_start = i * step
            w_end = min(total_dur, (i + 1) * step)
            c_dur = max(0.05, w_end - w_start)

            chunk = RenderChunk(
                chunk_index=i,
                total_chunks=num_chunks,
                window_start=w_start,
                window_end=w_end,
                duration=c_dur,
            )

            # 1. Sift overlapping Video Clips
            for clip in project.video_clips:
                c_start = clip.timeline_start
                c_end = clip.timeline_end
                # Check intersection: max(w_start, c_start) < min(w_end, c_end)
                overlap_start = max(w_start, c_start)
                overlap_end = min(w_end, c_end)
                if overlap_end > overlap_start + 0.01:
                    local_start = overlap_start - w_start
                    local_end = overlap_end - w_start

                    # Source offset calculation
                    offset_from_clip_start = (overlap_start - c_start) * clip.speed
                    slice_duration_in_source = (overlap_end - overlap_start) * clip.speed
                    trim_in = clip.trim_start + offset_from_clip_start
                    trim_out = trim_in + slice_duration_in_source

                    v_slice = VideoSlice(
                        clip_id=clip.id,
                        name=clip.name,
                        source_path=clip.source_path,
                        asset_id=clip.asset_id,
                        local_start=round(local_start, 3),
                        local_end=round(local_end, 3),
                        source_trim_in=round(trim_in, 3),
                        source_trim_out=round(trim_out, 3),
                        speed=clip.speed,
                        volume=clip.volume,
                        rotation=clip.rotation,
                        flip_h=clip.flip_h,
                        filter_name=clip.filter_name,
                        transition_in=clip.transition_in if overlap_start == c_start else "none",
                        transition_out=clip.transition_out if overlap_end == c_end else "none",
                    )
                    chunk.video_slices.append(v_slice)

            # 2. Sift overlapping Text Overlays
            for txt in project.text_overlays:
                t_start = txt.timeline_start
                t_end = txt.timeline_end
                overlap_start = max(w_start, t_start)
                overlap_end = min(w_end, t_end)
                if overlap_end > overlap_start + 0.01:
                    t_slice = TextSlice(
                        overlay_id=txt.id,
                        text=txt.text,
                        local_start=round(overlap_start - w_start, 3),
                        local_end=round(overlap_end - w_start, 3),
                        position=txt.position,
                        font_size=txt.font_size,
                        font_color=txt.font_color,
                        box=txt.box,
                        box_color=txt.box_color,
                        box_borderw=txt.box_borderw,
                        animation=txt.animation,
                    )
                    chunk.text_slices.append(t_slice)

            # 3. Sift overlapping Audio Clips
            for aud in project.audio_clips:
                a_start = aud.timeline_start
                a_end = aud.timeline_end
                overlap_start = max(w_start, a_start)
                overlap_end = min(w_end, a_end)
                if overlap_end > overlap_start + 0.01:
                    local_start = overlap_start - w_start
                    local_end = overlap_end - w_start
                    offset_src = overlap_start - a_start
                    dur_src = overlap_end - overlap_start
                    a_trim_in = aud.trim_start + offset_src
                    a_trim_out = a_trim_in + dur_src

                    a_slice = AudioSlice(
                        clip_id=aud.id,
                        source_path=aud.source_path,
                        asset_id=aud.asset_id,
                        local_start=round(local_start, 3),
                        local_end=round(local_end, 3),
                        source_trim_in=round(a_trim_in, 3),
                        source_trim_out=round(a_trim_out, 3),
                        volume=aud.volume,
                        fade_in=aud.fade_in if overlap_start == a_start else 0.0,
                        fade_out=aud.fade_out if overlap_end == a_end else 0.0,
                    )
                    chunk.audio_slices.append(a_slice)

            chunks.append(chunk)

        return chunks
