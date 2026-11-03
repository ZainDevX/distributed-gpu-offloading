"""
FFmpeg Command Builder for Clipchamp Studio.
Constructs complex filtergraphs for individual render chunks, aesthetic filters,
text overlays, multi-track audio mixing, and seamless lossless concatenation.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clipchamp_studio.engine.chunker import AudioSlice, RenderChunk, VideoSlice
from clipchamp_studio.model.filters import get_filter_expression
from common.utils import get_ffmpeg_binary, probe_media_file


class FFmpegBuilder:
    """Generates FFmpeg execution commands for Chunked Video Rendering."""

    def __init__(self, ffmpeg_bin: Optional[str] = None):
        self.ffmpeg_bin = ffmpeg_bin or get_ffmpeg_binary()

    def build_chunk_render_cmd(
        self,
        chunk: RenderChunk,
        output_file: Path,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
        codec: str = "h264_nvenc",
        bitrate: str = "5000k",
        asset_path_resolver: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """
        Build complete FFmpeg command line arguments to render a single temporal chunk.
        asset_path_resolver maps asset_id or original source_path to resolved on-disk path.
        """
        width, height = resolution
        dur = max(0.05, chunk.duration)

        # 1. Collect unique source input files needed for this chunk
        input_files: List[str] = []
        file_to_index: Dict[str, int] = {}
        file_has_audio: Dict[str, bool] = {}

        def resolve_path(src: str, asset_id: str) -> str:
            if asset_path_resolver:
                if asset_id and asset_id in asset_path_resolver:
                    return asset_path_resolver[asset_id]
                if src in asset_path_resolver:
                    return asset_path_resolver[src]
            return src

        # Inspect video sources
        for vs in chunk.video_slices:
            real_p = resolve_path(vs.source_path, vs.asset_id)
            if real_p not in file_to_index:
                file_to_index[real_p] = len(input_files)
                input_files.append(real_p)
                info = probe_media_file(Path(real_p))
                file_has_audio[real_p] = info.get("audio_codec", "None") not in ("None", "none", None)

        # Inspect audio sources
        for aslice in chunk.audio_slices:
            real_p = resolve_path(aslice.source_path, aslice.asset_id)
            if real_p not in file_to_index:
                file_to_index[real_p] = len(input_files)
                input_files.append(real_p)
                file_has_audio[real_p] = True

        cmd: List[str] = [
            self.ffmpeg_bin,
            "-y",
            "-loglevel", "error",
            "-nostats",
        ]

        # Add input files
        for inp in input_files:
            cmd.extend(["-i", inp])

        # 2. Build Complex Filtergraph
        filter_chains: List[str] = []

        # (a) Base black video canvas
        filter_chains.append(f"color=c=black:s={width}x{height}:r={fps}:d={dur:.3f}[base_v]")
        cur_v_tag = "base_v"

        # (b) Process Video Slices
        for idx, vs in enumerate(chunk.video_slices):
            real_p = resolve_path(vs.source_path, vs.asset_id)
            in_idx = file_to_index[real_p]

            slice_v_tag = f"v_sl_{idx}"
            sub_filters: List[str] = []

            # Trimming in source
            sub_filters.append(f"trim=start={vs.source_trim_in:.3f}:end={vs.source_trim_out:.3f}")
            sub_filters.append("setpts=PTS-STARTPTS")

            # Playback speed
            if abs(vs.speed - 1.0) > 0.01:
                pts_mult = 1.0 / max(0.1, vs.speed)
                sub_filters.append(f"setpts={pts_mult:.4f}*PTS")

            # Rotation
            if vs.rotation == 90:
                sub_filters.append("transpose=1")
            elif vs.rotation == 180:
                sub_filters.append("transpose=2,transpose=2")
            elif vs.rotation == 270:
                sub_filters.append("transpose=2")

            # Flip
            if vs.flip_h:
                sub_filters.append("hflip")

            # Aesthetic Filter
            f_expr = get_filter_expression(vs.filter_name)
            if f_expr and f_expr != "null":
                sub_filters.append(f_expr)

            # Transitions
            if vs.transition_in == "fade":
                sub_filters.append("fade=t=in:st=0:d=0.5")
            if vs.transition_out == "fade":
                fade_start = max(0.0, (vs.local_end - vs.local_start) - 0.5)
                sub_filters.append(f"fade=t=out:st={fade_start:.3f}:d=0.5")

            # Scale and pad to fit canvas
            sub_filters.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                f"format=yuv420p"
            )

            filter_chains.append(f"[{in_idx}:v]{','.join(sub_filters)}[{slice_v_tag}]")

            # Overlay onto canvas
            next_v_tag = f"v_comp_{idx}"
            overlay_expr = (
                f"[{cur_v_tag}][{slice_v_tag}]"
                f"overlay=x=0:y=0:enable='between(t,{vs.local_start:.3f},{vs.local_end:.3f})'"
                f"[{next_v_tag}]"
            )
            filter_chains.append(overlay_expr)
            cur_v_tag = next_v_tag

        # (c) Process Text Overlays
        for idx, ts in enumerate(chunk.text_slices):
            from clipchamp_studio.model.text_overlay import TextOverlay
            temp_overlay = TextOverlay(
                text=ts.text,
                position=ts.position,
                font_size=ts.font_size,
                font_color=ts.font_color,
                box=ts.box,
                box_color=ts.box_color,
                box_borderw=ts.box_borderw,
            )
            # Write text content to dedicated UTF-8 text file to eliminate filter escaping conflicts
            txt_file = output_file.parent / f"text_{chunk.chunk_index}_{idx}.txt"
            try:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                txt_file.write_text(ts.text, encoding="utf-8")
                draw_filter = temp_overlay.build_drawtext_filter(
                    local_start_time=ts.local_start,
                    local_end_time=ts.local_end,
                    text_file=txt_file,
                )
            except Exception:
                # Fallback to sanitized inline drawtext filter
                draw_filter = temp_overlay.build_drawtext_filter(
                    local_start_time=ts.local_start,
                    local_end_time=ts.local_end,
                )
            next_v_tag = f"v_txt_{idx}"
            filter_chains.append(f"[{cur_v_tag}]{draw_filter}[{next_v_tag}]")
            cur_v_tag = next_v_tag

        # (d) Process Audio Slices
        filter_chains.append(f"anullsrc=r=44100:cl=stereo:d={dur:.3f}[base_a]")
        audio_mix_inputs: List[str] = ["[base_a]"]

        # 1. Video clip audio tracks
        a_count = 0
        for vs in chunk.video_slices:
            real_p = resolve_path(vs.source_path, vs.asset_id)
            if file_has_audio.get(real_p, False) and vs.volume > 0.01:
                in_idx = file_to_index[real_p]
                a_tag = f"a_sl_{a_count}"
                a_count += 1
                a_filters = [
                    f"atrim=start={vs.source_trim_in:.3f}:end={vs.source_trim_out:.3f}",
                    "asetpts=PTS-STARTPTS",
                ]
                if abs(vs.speed - 1.0) > 0.01:
                    a_filters.append(f"atempo={vs.speed:.3f}")
                if abs(vs.volume - 1.0) > 0.01:
                    a_filters.append(f"volume={vs.volume:.2f}")

                delay_ms = max(0, int(vs.local_start * 1000))
                if delay_ms > 0:
                    a_filters.append(f"adelay={delay_ms}|{delay_ms}")

                filter_chains.append(f"[{in_idx}:a]{','.join(a_filters)}[{a_tag}]")
                audio_mix_inputs.append(f"[{a_tag}]")

        # 2. Dedicated background audio clips
        for aslice in chunk.audio_slices:
            real_p = resolve_path(aslice.source_path, aslice.asset_id)
            in_idx = file_to_index[real_p]
            a_tag = f"a_bgm_{a_count}"
            a_count += 1
            a_filters = [
                f"atrim=start={aslice.source_trim_in:.3f}:end={aslice.source_trim_out:.3f}",
                "asetpts=PTS-STARTPTS",
            ]
            if abs(aslice.volume - 1.0) > 0.01:
                a_filters.append(f"volume={aslice.volume:.2f}")

            delay_ms = max(0, int(aslice.local_start * 1000))
            if delay_ms > 0:
                a_filters.append(f"adelay={delay_ms}|{delay_ms}")

            filter_chains.append(f"[{in_idx}:a]{','.join(a_filters)}[{a_tag}]")
            audio_mix_inputs.append(f"[{a_tag}]")

        # Mix audio inputs together
        if len(audio_mix_inputs) > 1:
            amix_str = f"{''.join(audio_mix_inputs)}amix=inputs={len(audio_mix_inputs)}:duration=first:dropout_transition=0[final_a]"
            filter_chains.append(amix_str)
            cur_a_tag = "final_a"
        else:
            cur_a_tag = "base_a"

        # Join complex filter
        full_filtergraph = ";".join(filter_chains)
        cmd.extend(["-filter_complex", full_filtergraph])

        # Map final video and audio tags
        cmd.extend(["-map", f"[{cur_v_tag}]", "-map", f"[{cur_a_tag}]"])

        # Codec & hardware acceleration settings
        cmd.extend(["-c:v", codec])
        if "nvenc" in codec:
            cmd.extend(["-preset", "p4", "-rc", "vbr"])
        elif codec in ("libx264", "libx265"):
            cmd.extend(["-preset", "medium"])

        # Bitrate
        clean_b = bitrate.replace("k", "").strip() if bitrate else "5000"
        cmd.extend(["-b:v", f"{clean_b}k"])

        # Strictly enforce GOP keyframe alignment for concat demuxer
        cmd.extend([
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-g", str(fps),
            "-keyint_min", str(fps),
            "-sc_threshold", "0",
        ])

        # Audio encoder settings
        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
        ])

        # Duration & progress flag
        cmd.extend([
            "-t", f"{dur:.3f}",
            "-progress", "pipe:1",
            str(output_file.resolve()),
        ])

        return cmd

    def build_concat_manifest(self, chunk_files: List[Path], manifest_path: Path) -> Path:
        """
        Generate FFmpeg concat demuxer manifest text file.
        Uses relative paths from manifest to chunk files to ensure paths with spaces,
        quotes, or special characters in parent directories do not break FFmpeg demuxing.
        """
        manifest_path = Path(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            for c in chunk_files:
                try:
                    rel_p = os.path.relpath(c.resolve(), manifest_path.parent.resolve()).replace("\\", "/")
                except Exception:
                    rel_p = str(c.resolve()).replace("\\", "/")
                # Escape any single quotes in the filename
                escaped = rel_p.replace("'", r"\'")
                f.write(f"file '{escaped}'\n")
        return manifest_path

    def build_concat_cmd(self, manifest_path: Path, final_output_path: Path) -> List[str]:
        """
        Build lossless stream-copy concatenation command.
        Executes in milliseconds with zero quality loss.
        """
        return [
            self.ffmpeg_bin,
            "-y",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(manifest_path.resolve()),
            "-c", "copy",
            str(final_output_path.resolve()),
        ]

