"""
Automated Benchmarking Suite for Distributed GPU Offloading System.
Runs comparative evaluation of Local Client CPU vs Remote GPU Offload across resolutions.
Course: CSC-334 Parallel and Distributed Computing
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client.client_network import NetworkClient
from client.local_engine import LocalBenchmarkEngine
from common.config import BASE_DIR, TEST_MEDIA_DIR
from common.utils import format_bytes
from scripts.generate_test_media import generate_benchmark_suite

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("BenchmarkSuite")

RESULTS_DIR = BASE_DIR / "benchmark" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_benchmark_experiment(
    host: str = "127.0.0.1",
    port: int = 5050,
    resolutions: List[str] = None,
    output_dir: Path = RESULTS_DIR,
) -> Dict[str, Any]:
    """
    Execute full empirical evaluation across test video resolutions.
    Measures Local CPU vs Remote GPU offload performance, speedup, and network overhead.
    """
    if resolutions is None:
        resolutions = ["480p", "720p", "1080p"]

    logger.info("=" * 70)
    logger.info("   DISTRIBUTED GPU OFFLOADING PERFORMANCE BENCHMARK (CSC-334)")
    logger.info("=" * 70)
    logger.info(f"Target Worker Node : {host}:{port}")
    logger.info(f"Test Resolutions   : {', '.join(resolutions)}")

    # 1. Ensure test clips are generated
    logger.info("[*] Generating / verifying test media assets...")
    clips = generate_benchmark_suite(TEST_MEDIA_DIR)

    # 2. Initialize clients
    client = NetworkClient(host=host, port=port)
    local_engine = LocalBenchmarkEngine()

    logger.info(f"[*] Establishing connection to worker node {host}:{port}...")
    client.connect()
    handshake_data = client.handshake()
    latency_ms = client.ping()

    gpu_telemetry = handshake_data.get("gpu_telemetry", {})
    gpu_name = gpu_telemetry.get("gpu_name", "N/A")
    vram_mb = gpu_telemetry.get("vram_total_mb", 0)

    logger.info(f"[+] Worker Node Confirmed: {handshake_data.get('worker_name')}")
    logger.info(f"    - Latency (RTT)    : {latency_ms:.2f} ms")
    logger.info(f"    - Remote GPU Model : {gpu_name} ({vram_mb} MB VRAM)")
    logger.info(f"    - Preferred Engine : {gpu_telemetry.get('preferred_gpu_encoder')}")
    logger.info("-" * 70)

    results = []

    for res_name in resolutions:
        clip_path = clips.get(res_name)
        if not clip_path or not clip_path.exists():
            logger.warning(f"Clip for {res_name} not found, skipping.")
            continue

        file_size = clip_path.stat().st_size
        logger.info(f"\n[>>>] Running Benchmark for: {res_name.upper()} ({clip_path.name}, {format_bytes(file_size)})")

        job_config = {
            "codec": "auto_detect",
            "resolution": "Original",
            "bitrate": "4000k",
            "preset": "p4",
            "audio": "copy",
        }

        # -------------------------------------------------------------
        # Part A: Local Client CPU Benchmark Execution
        # -------------------------------------------------------------
        logger.info("  [1/2] Executing Local Client CPU Transcode (libx264)...")
        start_local = time.time()
        local_res = local_engine.run_local_transcode(input_path=clip_path, config=job_config)
        t_local = local_res["execution_time_seconds"]
        logger.info(f"        -> Local CPU Duration (T_local): {t_local:.2f}s")

        # -------------------------------------------------------------
        # Part B: Remote GPU Offload Execution
        # -------------------------------------------------------------
        logger.info("  [2/2] Executing Distributed GPU Offloading over Network...")
        remote_res = client.offload_task(input_file=clip_path, config=job_config)

        t_upload = remote_res["upload_duration_seconds"]
        t_compute = remote_res["compute_duration_seconds"]
        t_download = remote_res["download_duration_seconds"]
        t_remote_total = remote_res["total_offload_seconds"]
        t_overhead = remote_res["network_overhead_seconds"]
        overhead_pct = remote_res["network_overhead_pct"]

        # Calculate Speedup
        total_speedup = round(t_local / max(0.001, t_remote_total), 2)
        compute_speedup = round(t_local / max(0.001, t_compute), 2)

        logger.info(f"        -> Upload Time   (T_upload)  : {t_upload:.2f}s ({remote_res['upload_speed_mbps']} MB/s)")
        logger.info(f"        -> GPU Compute   (T_compute) : {t_compute:.2f}s [{remote_res['encoder_used']}]")
        logger.info(f"        -> Download Time (T_download): {t_download:.2f}s ({remote_res['download_speed_mbps']} MB/s)")
        logger.info(f"        -> Total Offload (T_total)   : {t_remote_total:.2f}s")
        logger.info(f"        -> Net Overhead  (Overhead)  : {t_overhead:.2f}s ({overhead_pct:.1f}%)")
        logger.info(f"        ==> Total System Speedup (S) : {total_speedup}x")
        logger.info(f"        ==> Compute-only Speedup     : {compute_speedup}x")

        entry = {
            "resolution": res_name,
            "input_file": clip_path.name,
            "input_size_bytes": file_size,
            "input_size_formatted": format_bytes(file_size),
            "output_size_bytes": remote_res["output_size_bytes"],
            "t_local_seconds": t_local,
            "t_upload_seconds": t_upload,
            "t_remote_compute_seconds": t_compute,
            "t_download_seconds": t_download,
            "t_remote_total_seconds": t_remote_total,
            "network_overhead_seconds": t_overhead,
            "network_overhead_pct": overhead_pct,
            "total_speedup": total_speedup,
            "compute_speedup": compute_speedup,
            "upload_mbps": remote_res["upload_speed_mbps"],
            "download_mbps": remote_res["download_speed_mbps"],
            "sha256_verified": remote_res["sha256_verified"],
            "remote_gpu": gpu_name,
            "encoder_used": remote_res["encoder_used"],
        }
        results.append(entry)

    client.close()

    # 3. Export data to JSON & CSV
    json_path = output_dir / "benchmark_data.json"
    csv_path = output_dir / "benchmark_data.csv"

    benchmark_bundle = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {
            "client_host": os.environ.get("COMPUTERNAME", "Client-Node"),
            "worker_host": handshake_data.get("worker_name"),
            "gpu_name": gpu_name,
            "vram_mb": vram_mb,
            "network_latency_ms": latency_ms,
        },
        "results": results,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_bundle, f, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "resolution", "input_size_formatted", "t_local_seconds", "t_upload_seconds",
            "t_remote_compute_seconds", "t_download_seconds", "t_remote_total_seconds",
            "network_overhead_pct", "total_speedup", "compute_speedup", "upload_mbps", "download_mbps"
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "resolution": r["resolution"],
                "input_size_formatted": r["input_size_formatted"],
                "t_local_seconds": r["t_local_seconds"],
                "t_upload_seconds": r["t_upload_seconds"],
                "t_remote_compute_seconds": r["t_remote_compute_seconds"],
                "t_download_seconds": r["t_download_seconds"],
                "t_remote_total_seconds": r["t_remote_total_seconds"],
                "network_overhead_pct": r["network_overhead_pct"],
                "total_speedup": r["total_speedup"],
                "compute_speedup": r["compute_speedup"],
                "upload_mbps": r["upload_mbps"],
                "download_mbps": r["download_mbps"],
            })

    # Print summary table
    print("\n" + "=" * 88)
    print("                      CSC-334 BENCHMARK EVALUATION SUMMARY")
    print("=" * 88)
    print(f"{'Resolution':<12} | {'Input Size':<11} | {'T_local (s)':<11} | {'T_remote (s)':<12} | {'Speedup':<8} | {'Compute S':<9} | {'Net OH %':<8}")
    print("-" * 88)
    for r in results:
        print(f"{r['resolution']:<12} | {r['input_size_formatted']:<11} | {r['t_local_seconds']:<11.2f} | {r['t_remote_total_seconds']:<12.2f} | {r['total_speedup']:<7.2f}x | {r['compute_speedup']:<8.2f}x | {r['network_overhead_pct']:<7.1f}%")
    print("=" * 88)
    print(f"[*] Benchmark dataset exported to:")
    print(f"    - JSON: {json_path}")
    print(f"    - CSV : {csv_path}")

    return benchmark_bundle


def main():
    parser = argparse.ArgumentParser(description="Run Automated Performance Benchmarking")
    parser.add_argument("--host", default="127.0.0.1", help="Worker daemon IP")
    parser.add_argument("--port", type=int, default=5050, help="Worker daemon port")
    parser.add_argument("--res", nargs="+", default=["480p", "720p", "1080p"], help="Resolutions to test")
    args = parser.parse_args()

    run_benchmark_experiment(host=args.host, port=args.port, resolutions=args.res)


if __name__ == "__main__":
    main()
