"""
Unit Tests for Clipchamp Studio Data Models and Timeline Chunker.
"""

import sys
import unittest
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from clipchamp_studio.engine.chunker import TimelineChunker
from clipchamp_studio.model.clip import VideoClip
from clipchamp_studio.model.project import ClipchampProject


class TestClipchampChunker(unittest.TestCase):

    def setUp(self):
        self.project = ClipchampProject(project_name="Unit Test Project")
        # Add two virtual clips
        c1 = VideoClip(
            name="Scene 1",
            source_path="scene1.mp4",
            asset_id="hash_scene_1",
            source_duration=10.0,
            trim_start=0.0,
            trim_end=10.0,
            timeline_start=0.0,
            speed=1.0,
        )
        c2 = VideoClip(
            name="Scene 2",
            source_path="scene2.mp4",
            asset_id="hash_scene_2",
            source_duration=10.0,
            trim_start=2.0,
            trim_end=8.0,  # 6s duration
            timeline_start=10.0,
            speed=1.5,  # 6 / 1.5 = 4s duration -> ends at 14.0s
        )
        self.project.video_clips.extend([c1, c2])
        self.project.add_text_overlay("TEST TITLE", timeline_start=2.0, duration=4.0)

    def test_total_duration(self):
        self.assertAlmostEqual(self.project.total_duration, 14.0, places=2)

    def test_clip_splitting(self):
        # Split scene 1 at timeline 4.0s
        success = self.project.split_video_clip(self.project.video_clips[0].id, 4.0)
        self.assertTrue(success)
        self.assertEqual(len(self.project.video_clips), 3)

        c1 = self.project.video_clips[0]
        c2 = self.project.video_clips[1]
        self.assertAlmostEqual(c1.timeline_start, 0.0)
        self.assertAlmostEqual(c1.timeline_end, 4.0)
        self.assertAlmostEqual(c2.timeline_start, 4.0)
        self.assertAlmostEqual(c2.timeline_end, 10.0)

    def test_timeline_chunking(self):
        # 14s timeline with 5s chunk duration -> 3 chunks: [0-5], [5-10], [10-14]
        chunks = TimelineChunker.partition_project(self.project, chunk_duration=5.0)
        self.assertEqual(len(chunks), 3)

        self.assertAlmostEqual(chunks[0].window_start, 0.0)
        self.assertAlmostEqual(chunks[0].window_end, 5.0)
        self.assertAlmostEqual(chunks[1].window_start, 5.0)
        self.assertAlmostEqual(chunks[1].window_end, 10.0)
        self.assertAlmostEqual(chunks[2].window_start, 10.0)
        self.assertAlmostEqual(chunks[2].window_end, 14.0)

        # Verify text overlay in chunk 0 (starts at 2.0s, ends at 6.0s)
        self.assertEqual(len(chunks[0].text_slices), 1)
        self.assertEqual(chunks[0].text_slices[0].text, "TEST TITLE")
        self.assertAlmostEqual(chunks[0].text_slices[0].local_start, 2.0)
        self.assertAlmostEqual(chunks[0].text_slices[0].local_end, 5.0)

        # Text overlay should also bleed into chunk 1 (5.0s to 6.0s -> local 0.0s to 1.0s)
        self.assertEqual(len(chunks[1].text_slices), 1)
        self.assertAlmostEqual(chunks[1].text_slices[0].local_start, 0.0)
        self.assertAlmostEqual(chunks[1].text_slices[0].local_end, 1.0)


if __name__ == "__main__":
    unittest.main()

