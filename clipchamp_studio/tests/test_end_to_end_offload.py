"""
End-to-End Integration Test for Distributed GPU Chunked Video Offloading.
Tests daemon startup, handshake, asset deduplication, chunked transcoding,
lossless assembly, socket streaming, and SHA-256 verification.
"""

import sys
import threading
import time
import unittest
from pathlib import Path

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from clipchamp_studio.model.project import ClipchampProject
from clipchamp_studio.network.clipchamp_client import ClipchampNetworkClient
from client.client_network import NetworkClient
from common.config import CLIENT_OUTPUT_DIR, TEST_MEDIA_DIR
from server.daemon import WorkerDaemon

TEST_PORT = 5055


class TestEndToEndClipchampOffload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Start Worker Daemon in background thread
        cls.daemon = WorkerDaemon(
            host="127.0.0.1",
            port=TEST_PORT,
            allow_cpu_fallback=True,
        )
        cls.daemon_thread = threading.Thread(target=cls.daemon.start, daemon=True)
        cls.daemon_thread.start()
        # Give daemon a second to bind socket
        time.sleep(1.0)

    @classmethod
    def tearDownClass(cls):
        cls.daemon.stop()

    def test_full_chunked_offload_flow(self):
        clip_path = TEST_MEDIA_DIR / "test_clip_480p.mp4"
        if not clip_path.exists():
            self.skipTest("Sample test clip missing in test_media/")

        # 1. Establish Client Connection
        net_client = NetworkClient(host="127.0.0.1", port=TEST_PORT)
        self.assertTrue(net_client.connect())

        # 2. Handshake
        handshake_data = net_client.handshake()
        self.assertEqual(handshake_data.get("status"), "ready")
        gpu_caps = handshake_data.get("gpu_telemetry", {})
        print(f"\n[TEST] Host GPU Detected: {gpu_caps.get('gpu_name')}")

        # 3. Create Clipchamp Project
        project = ClipchampProject(
            project_name="Integration Test Project",
            chunk_duration=3.0,  # 3-second chunks
        )
        clip = project.add_video_clip_from_file(clip_path)
        clip.trim_end = min(6.0, clip.source_duration)  # 6s total -> 2 chunks
        clip.filter_name = "Warm Cinematic"
        project.add_text_overlay("OFFLOAD TEST", timeline_start=0.5, duration=2.5)

        # 4. Offload with Chunking
        clipchamp_client = ClipchampNetworkClient(net_client)

        progress_stages = []

        def on_prog(p):
            stage = p.get("stage", "")
            progress_stages.append(stage)
            pct = p.get("total_percent", p.get("percent", 0.0))
            cur_chunk = p.get("current_chunk", "")
            fps = p.get("fps", 0.0)
            print(f"       [Progress] {stage} ({pct:.1f}%) | Chunk: {cur_chunk} | FPS: {fps}")

        result = clipchamp_client.offload_project(
            project=project,
            output_dir=CLIENT_OUTPUT_DIR,
            progress_callback=on_prog,
            log_callback=lambda m: print(f"       [Log] {m}"),
        )

        # 5. Assertions
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["sha256_verified"])
        self.assertGreater(result["output_size_bytes"], 0)
        self.assertTrue(Path(result["output_file"]).exists())
        self.assertGreaterEqual(result["chunks_rendered"], 2)

        print("\n" + "=" * 60)
        print("DISTRIBUTED CHUNKED OFFLOAD PASSED!")
        print(f"Total Offload Time  : {result['total_offload_seconds']}s")
        print(f"  - Upload Duration : {result['upload_duration_seconds']}s")
        print(f"  - GPU Compute     : {result['compute_duration_seconds']}s ({result['gpu_name']} - {result['encoder_used']})")
        print(f"  - Download Time   : {result['download_duration_seconds']}s")
        print(f"Chunks Rendered     : {result['chunks_rendered']}")
        print(f"Output File         : {result['output_file']}")
        print(f"SHA-256 Checksum    : {result['sha256']}")
        print("=" * 60)

        # 6. Test Asset Deduplication: Offload again! Upload duration should be ~0.0s!
        print("\n[TEST] Testing Asset Deduplication (Second Run)...")
        res2 = clipchamp_client.offload_project(
            project=project,
            output_dir=CLIENT_OUTPUT_DIR,
        )
        self.assertEqual(res2["status"], "success")
        self.assertAlmostEqual(res2["upload_duration_seconds"], 0.0, delta=0.5)
        print(f"[TEST] Deduplication Success! Upload time on second run: {res2['upload_duration_seconds']:.2f}s (cached on host)")

        net_client.close()


if __name__ == "__main__":
    unittest.main()

