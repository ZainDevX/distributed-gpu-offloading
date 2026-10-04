"""
Benchmark Analysis and Performance Report Generator.
Computes Amdahl's Law models, speedup curves, and generates Markdown reporting tables.
Course: CSC-334 Parallel and Distributed Computing
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from common.config import BASE_DIR

RESULTS_JSON = BASE_DIR / "benchmark" / "results" / "benchmark_data.json"


def load_benchmark_data(json_path: Path = RESULTS_JSON) -> Dict[str, Any]:
    if not json_path.exists():
        raise FileNotFoundError(f"Benchmark results file not found at {json_path}. Run run_benchmark.py first.")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_amdahl_theoretical_speedup(p: float, s_gpu: float, t_comm_ratio: float) -> float:
    """
    Amdahl's Law adjusted for Distributed Systems with Communication Overhead:
    S = 1 / [ (1 - p) + (p / s_gpu) + t_comm_ratio ]
    where:
      p: fraction of workload offloaded to GPU (e.g. 0.95 for video transcoding)
      s_gpu: raw hardware execution acceleration factor (e.g. 10x - 20x)
      t_comm_ratio: T_network_transfer / T_local_serial
    """
    denom = (1.0 - p) + (p / s_gpu) + t_comm_ratio
    return round(1.0 / denom, 2) if denom > 0 else 0.0


def generate_markdown_analysis(data: Dict[str, Any]) -> str:
    """Generate Markdown evaluation section from experimental benchmark data."""
    results = data.get("results", [])
    hardware = data.get("hardware", {})

    md = []
    md.append("### Empirical Benchmark Results\n")
    md.append(f"- **Worker Hostname**: `{hardware.get('worker_host')}`")
    md.append(f"- **Detected Accelerator**: `{hardware.get('gpu_name')}` ({hardware.get('vram_mb')} MB VRAM)")
    md.append(f"- **Network Latency (RTT Ping)**: `{hardware.get('network_latency_ms')} ms`\n")

    md.append("| Resolution | Asset Size | $T_{local}$ (s) | $T_{upload}$ (s) | $T_{compute}$ (s) | $T_{download}$ (s) | $T_{total}$ (s) | Speedup ($S$) | Compute Speedup | Net Overhead (%) |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    total_speedups = []
    for r in results:
        res = r["resolution"]
        sz = r["input_size_formatted"]
        tl = r["t_local_seconds"]
        tu = r["t_upload_seconds"]
        tc = r["t_remote_compute_seconds"]
        td = r["t_download_seconds"]
        tt = r["t_remote_total_seconds"]
        sp = r["total_speedup"]
        csp = r["compute_speedup"]
        oh = r["network_overhead_pct"]
        total_speedups.append(sp)

        md.append(f"| **{res}** | {sz} | {tl:.2f}s | {tu:.2f}s | {tc:.2f}s | {td:.2f}s | {tt:.2f}s | **{sp:.2f}x** | {csp:.2f}x | {oh:.1f}% |")

    avg_speedup = sum(total_speedups) / len(total_speedups) if total_speedups else 1.0

    md.append(f"\n> **Key Metric**: Average End-to-End Speedup across test battery: **{avg_speedup:.2f}x**\n")

    # Mathematical discussion
    md.append("#### Amdahl's Law Distributed Extension Model\n")
    md.append("In a distributed offloading system, the speedup is bounded not only by the serial execution fraction $(1 - p)$, but fundamentally by the communication overhead ratio:")
    md.append("$$S_{distributed} = \\frac{T_{local}}{T_{remote}} = \\frac{T_{local}}{T_{upload} + T_{compute} + T_{download}}$$\n")
    md.append("When defining the network transfer cost as $T_{comm} = T_{upload} + T_{download}$, the effective speedup threshold requirement for offloading viability is:")
    md.append("$$T_{local} > T_{compute} + T_{comm} \\iff S_{distributed} > 1.0$$\n")
    md.append("As resolution scales from 480p to 1080p, the computational density ($O(W \\times H)$ operations per pixel) increases quadratically while network transfer throughput over Gigabit LAN remains consistent, resulting in increasingly advantageous speedup ratios for higher workloads.\n")

    return "\n".join(md)


if __name__ == "__main__":
    try:
        data = load_benchmark_data()
        analysis = generate_markdown_analysis(data)
        print(analysis)
    except Exception as e:
        print(f"Analysis note: {e}")
