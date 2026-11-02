"""
Microsoft Windows 11 Clipchamp Studio Video Editor with Distributed GPU Chunked Offloading.
Course: CSC-334 Parallel and Distributed Computing
"""

from clipchamp_studio.model.clip import AudioClip, VideoClip
from clipchamp_studio.model.filters import CLIPCHAMP_FILTERS
from clipchamp_studio.model.project import ClipchampProject
from clipchamp_studio.model.text_overlay import TextOverlay
from clipchamp_studio.ui.editor_window import ClipchampEditorWindow

__all__ = [
    "ClipchampProject",
    "VideoClip",
    "AudioClip",
    "TextOverlay",
    "CLIPCHAMP_FILTERS",
    "ClipchampEditorWindow",
]

