"""
Clipchamp-style Aesthetic Filter Presets & FFmpeg Filter Mappings.
Provides instant visual transformations matching Microsoft Clipchamp video editor.
"""

from typing import Dict, List, NamedTuple, Optional


class FilterPreset(NamedTuple):
    name: str
    description: str
    preview_hex: str
    ffmpeg_filter: str


# Preset library inspired by Clipchamp's real filters
CLIPCHAMP_FILTERS: Dict[str, FilterPreset] = {
    "Normal": FilterPreset(
        name="Normal",
        description="Standard unfiltered video pass-through",
        preview_hex="#94a3b8",
        ffmpeg_filter="null",
    ),
    "Vivid": FilterPreset(
        name="Vivid",
        description="Boosts color vibrance, saturation and crisp micro-contrast",
        preview_hex="#38bdf8",
        ffmpeg_filter="eq=saturation=1.45:contrast=1.12:brightness=0.01",
    ),
    "Warm Cinematic": FilterPreset(
        name="Warm Cinematic",
        description="Golden-hour warm tones with rich amber midtones",
        preview_hex="#f59e0b",
        ffmpeg_filter="colorbalance=rs=0.15:gs=0.05:bs=-0.12:rm=0.15:gm=0.05:bm=-0.12,eq=saturation=1.15",
    ),
    "Cool Cyberpunk": FilterPreset(
        name="Cool Cyberpunk",
        description="Futuristic neon cyan and deep cobalt shadows",
        preview_hex="#06b6d4",
        ffmpeg_filter="colorbalance=rs=-0.12:gs=0.04:bs=0.22:rm=-0.1:gm=0.04:bm=0.2,eq=saturation=1.25:contrast=1.15",
    ),
    "Noir B&W": FilterPreset(
        name="Noir B&W",
        description="High-contrast classic Hollywood monochrome film look",
        preview_hex="#e2e8f0",
        ffmpeg_filter="hue=s=0,eq=contrast=1.3:brightness=-0.02",
    ),
    "Vintage Sepia": FilterPreset(
        name="Vintage Sepia",
        description="Nostalgic retro analog film emulsion tones",
        preview_hex="#d97706",
        ffmpeg_filter="colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0,eq=contrast=1.05",
    ),
    "Vignette Drama": FilterPreset(
        name="Vignette Drama",
        description="Cinematic soft edge falloff focusing attention in center",
        preview_hex="#818cf8",
        ffmpeg_filter="vignette=PI/4,eq=contrast=1.1:saturation=1.1",
    ),
    "High Contrast": FilterPreset(
        name="High Contrast",
        description="Punchy, modern stylized contrast with deep blacks",
        preview_hex="#ec4899",
        ffmpeg_filter="eq=contrast=1.38:brightness=-0.04:saturation=1.15",
    ),
    "Letterbox 2.35:1": FilterPreset(
        name="Letterbox 2.35:1",
        description="Anamorphic widescreen black cinematic bars top and bottom",
        preview_hex="#64748b",
        ffmpeg_filter="drawbox=x=0:y=0:w=iw:h=ih*0.12:color=black:t=fill,drawbox=x=0:y=ih-ih*0.12:w=iw:h=ih*0.12:color=black:t=fill",
    ),
}


def get_filter_expression(name: str) -> str:
    """Return FFmpeg filter string for a given preset name."""
    preset = CLIPCHAMP_FILTERS.get(name)
    if preset:
        return preset.ffmpeg_filter
    return "null"


def get_all_filter_names() -> List[str]:
    """Return ordered list of available filter preset names."""
    return list(CLIPCHAMP_FILTERS.keys())
