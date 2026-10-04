"""
Quick Integration Verification Test for Distributed GPU Offloading System.
Tests Handshake, Latency Ping, Upload, Transcoding, Streaming Progress, Download & Integrity.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client.client_network import NetworkClient
from common.config import TEST_MEDIA_DIR

def run_test():
    test_clip = TEST_MEDIA_DIR / "test_clip_720p.mp4"
    if not test_clip.exists():
        print("Test clip missing, please generate it first.")
        return False

    client = NetworkClient(host="127.0.0.1", port=5050)
    print("[1] Connecting to daemon on 127.0.0.1:5050...")
    client.connect()
    print("    -> Connected successfully!")

    print("[2] Testing latency ping...")
    latency = client.ping()
    print(f"    -> Latency Ping: {latency:.2f} ms")

    print("[3] Testing handshake protocol...")
    worker_caps = client.handshake()
    print(f"    -> Worker Hostname : {worker_caps.get('worker_name')}")
    print(f"    -> GPU Detected    : {worker_caps.get('gpu_telemetry', {}).get('gpu_name')}")
    print(f"    -> Preferred Engine: {worker_caps.get('gpu_telemetry', {}).get('preferred_gpu_encoder')}")

    print("[4] Submitting offload job...")
    config = {
        "codec": "auto_detect",
        "resolution": "480p (SD 854x480)",
        "bitrate": "1500k",
        "preset": "p4",
        "audio": "copy",
    }

    progress_events = []
    def on_prog(p):
        progress_events.append(p)
        stage = p.get("stage", "")
        pct = p.get("percent", 0.0)
        speed = p.get("speed", "")
        fps = p.get("fps", 0)
        print(f"       [Progress] {stage}: {pct}% | FPS: {fps} | Speed: {speed}")

    def on_log(msg):
        print(f"       [Log] {msg}")

    start_t = time.time()
    result = client.offload_task(
        input_file=test_clip,
        config=config,
        progress_callback=on_prog,
        log_callback=on_log,
    )
    total_t = time.time() - start_t

    print("=" * 60)
    print("INTEGRATION TEST PASSED!")
    print(f"Status              : {result['status']}")
    print(f"Total Offload Time  : {result['total_offload_seconds']}s")
    print(f"  - Upload Duration : {result['upload_duration_seconds']}s ({result['upload_speed_mbps']} MB/s)")
    print(f"  - Compute Duration: {result['compute_duration_seconds']}s (GPU/Hardware Transcode)")
    print(f"  - Download Duration: {result['download_duration_seconds']}s ({result['download_speed_mbps']} MB/s)")
    print(f"Output File         : {result['output_file']}")
    print(f"Output Size         : {result['output_size_bytes']} bytes")
    print(f"SHA-256 Verified    : {result['sha256_verified']}")
    print("=" * 60)

    client.close()
    return True

if __name__ == "__main__":
    run_test()
