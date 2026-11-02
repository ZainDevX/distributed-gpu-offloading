"""
Unit & Local Render Tests for FFmpeg Builder and Lossless Concat.
"""

import sys
import unittest
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from clipchamp_studio.engine.chunker import TimelineChunker
from clipchamp_studio.engine.ffmpeg_builder import FFmpegBuilder
from clipchamp_studio.engine.project_executor import LocalProjectExecutor
from clipchamp_studio.model.project import ClipchampProject
from common.config import TEST_MEDIA_DIR
from common.utils import probe_media_file


class TestBuilderAndRender(unittest.TestCase):

    def test_local_render_and_concat(self):
        clip_path = TEST_MEDIA_DIR / "test_clip_480p.mp4"
        if not clip_path.exists():
            self.skipTest("Sample test clip not found")

        project = ClipchampProject(project_name="Render Test", chunk_duration=3.0)
        c = project.add_video_clip_from_file(clip_path)
        c.filter_name = "Vivid"
        c.trim_end = min(6.0, c.source_duration)
        project.add_text_overlay("DEMO TITLE", timeline_start=0.5, duration=2.0)

        out_file = TEST_MEDIA_DIR / "test_local_assembled_output.mp4"
        if out_file.exists():
            out_file.unlink()

        executor = LocalProjectExecutor()
        res = executor.render_project_locally(project, out_file, use_chunking=True)

        self.assertEqual(res["status"], "success")
        self.assertTrue(out_file.exists())
        self.assertGreater(out_file.stat().st_size, 0)

        # Probe output video
        meta = probe_media_file(out_file)
        self.assertGreater(meta["duration_seconds"], 2.0)
        self.assertEqual(meta["width"], 1920)
        self.assertEqual(meta["height"], 1080)

        # Cleanup test output
        if out_file.exists():
            out_file.unlink()


if __name__ == "__main__":
    unittest.main()

