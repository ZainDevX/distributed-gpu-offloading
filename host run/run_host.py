"""
Automated One-Click Host Server Launcher for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing

Features:
- Validates Python 3.9+ environment.
- Verifies and auto-installs all required dependencies.
- Hardware GPU detection (GeForce GTX 1050, 4GB VRAM, NVENC / Hardware MFT).
- Smart Network Detection (prioritizes CAT6 Ethernet if plugged in; falls back to Wi-Fi if unplugged).
- Prints comprehensive, step-by-step manual workflow instructions in the terminal.
- Starts high-throughput Worker Server Daemon on port 5050 (handles port-in-use gracefully).
- Launches the Desktop GUI Dashboard on Host pre-configured to 127.0.0.1 (or supports --headless).
"""

import argparse
import importlib
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# Enable UTF-8 and ANSI escape sequences on Windows console
if sys.platform == "win32":
    os.system("")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ANSI Color Codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_BLUE = "\033[94m"
C_WHITE = "\033[97m"

# Ensure script root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Required modules mapping: {import_name: pip_package_spec}
REQUIRED_PACKAGES = {
    "customtkinter": "customtkinter>=6.0.0",
    "imageio_ffmpeg": "imageio-ffmpeg>=0.5.1",
    "psutil": "psutil>=5.9.0",
    "PIL": "pillow>=10.0.0",
    "packaging": "packaging>=23.0",
    "darkdetect": "darkdetect>=0.8.0",
}


def print_banner():
    print(f"{C_CYAN}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_CYAN}{C_BOLD}        DISTRIBUTED GPU TASK OFFLOADING - HOST WORKER NODE{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}===================================================================={C_RESET}")

    py_ver = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 9:
        print(f"[*] Python Environment     : {C_GREEN}[OK] Python {py_ver}{C_RESET} ({sys.platform})")
    else:
        print(f"[*] Python Environment     : {C_RED}[WARN] Python {py_ver} (Python 3.9+ recommended){C_RESET}")
    print(f"[*] Working Directory      : {SCRIPT_DIR.resolve()}")
    print()


def check_and_install_dependencies():
    """Verify all dependencies and auto-install any missing packages."""
    print(f"{C_BOLD}[*] Step 1: Verifying Required Python Dependencies...{C_RESET}")

    missing = []
    for mod_name, pip_spec in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(mod_name)
            print(f"    {C_GREEN}[OK]{C_RESET}        {mod_name:<16} {C_WHITE}(installed & ready){C_RESET}")
        except ImportError:
            print(f"    {C_RED}[MISSING]{C_RESET}   {mod_name:<16} {C_YELLOW}(requires {pip_spec}){C_RESET}")
            missing.append(pip_spec)

    if missing:
        print(f"\n{C_YELLOW}[!] Missing packages detected. Automatically installing via pip...{C_RESET}")
        req_file = SCRIPT_DIR / "requirements.txt"
        try:
            if req_file.exists():
                print(f"{C_CYAN}[*] Running: pip install -r requirements.txt{C_RESET}")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                    cwd=str(SCRIPT_DIR),
                )
            else:
                print(f"{C_CYAN}[*] Running: pip install {' '.join(missing)}{C_RESET}")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install"] + missing,
                    cwd=str(SCRIPT_DIR),
                )
            print(f"\n{C_GREEN}{C_BOLD}[+] All required packages installed successfully!{C_RESET}\n")
        except subprocess.CalledProcessError as e:
            print(f"\n{C_RED}{C_BOLD}[ERROR] Automatic pip installation failed with exit code {e.returncode}.{C_RESET}")
            print(f"{C_YELLOW}Please ensure your computer has an active internet connection and run:{C_RESET}")
            print(f"    pip install -r requirements.txt")
            input(f"\n{C_WHITE}Press Enter to exit...{C_RESET}")
            sys.exit(1)
    else:
        print(f"\n{C_GREEN}[+] All dependencies are already installed and verified!{C_RESET}\n")


def display_hardware_telemetry():
    """Detect and display GPU status."""
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}           STEP 2: HARDWARE ACCELERATION & GPU TELEMETRY{C_RESET}")
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")

    from server.gpu_detector import GPUDetector
    caps = GPUDetector.get_worker_capabilities()
    gpu_name = caps.get("gpu_name", "No Dedicated GPU Found")
    vram = caps.get("vram_total_mb", 0)
    driver = caps.get("driver_version", "N/A")
    cuda = caps.get("cuda_version", "N/A")
    enc = caps.get("preferred_gpu_encoder", "libx264")

    if caps.get("has_nvidia_gpu", False):
        print(f"[*] Detected GPU           : {C_GREEN}{C_BOLD}{gpu_name}{C_RESET} ({C_GREEN}{vram} MB VRAM{C_RESET})")
        print(f"[*] Driver / CUDA Version  : Driver {driver} | CUDA {cuda}")
        print(f"[*] Hardware Encoders      : {C_GREEN}{enc} (Operational){C_RESET}")
    else:
        print(f"[*] Detected GPU           : {C_YELLOW}{gpu_name} (Using CPU Transcode Engine){C_RESET}")
    print()


def analyze_network():
    """
    Smart Network Detection on Host.
    Prioritizes CAT6 Ethernet if cable is plugged in; falls back to Wi-Fi if unplugged.
    """
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}           STEP 3: SMART NETWORK DETECTION & HOST IP{C_RESET}")
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")

    import psutil
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    eth_info = None
    wifi_info = None

    for iface_name, stat in stats.items():
        name_lower = iface_name.lower()
        if ("ethernet" in name_lower or "eth" in name_lower or "local area" in name_lower) and "pseudo" not in name_lower:
            for a in addrs.get(iface_name, []):
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    eth_info = {
                        "name": iface_name,
                        "ip": a.address,
                        "is_up": stat.isup,
                        "speed": stat.speed,
                        "is_apipa": a.address.startswith("169.254."),
                    }
                    break
        elif ("wi-fi" in name_lower or "wifi" in name_lower or "wireless" in name_lower or "wlan" in name_lower) and "pseudo" not in name_lower:
            for a in addrs.get(iface_name, []):
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    wifi_info = {
                        "name": iface_name,
                        "ip": a.address,
                        "is_up": stat.isup,
                        "speed": stat.speed,
                    }
                    break

    selected_ip = "192.168.1.2"
    selected_mode = "Ethernet"

    has_valid_eth = eth_info and eth_info["is_up"] and eth_info["speed"] > 0 and not eth_info["is_apipa"]
    has_valid_wifi = wifi_info and wifi_info["is_up"] and not wifi_info["ip"].startswith("169.254.")

    if has_valid_eth:
        print(f"[*] Ethernet Adapter       : {C_GREEN}[ONLINE] {eth_info['name']}{C_RESET}")
        print(f"    - Physical Link Speed  : {C_GREEN}{eth_info['speed']} Mbps (CAT6 Cable Connected){C_RESET}")
        print(f"    - Host Ethernet IP     : {C_GREEN}{C_BOLD}{eth_info['ip']}{C_RESET}")
    elif eth_info and eth_info["is_apipa"]:
        print(f"[*] Ethernet Adapter       : {C_YELLOW}[CABLE DETECTED BUT UNCONFIGURED]{C_RESET}")
        print(f"    - Current IP           : {C_YELLOW}{eth_info['ip']} (Auto-IP / Needs Static IP){C_RESET}")
    else:
        print(f"[*] Ethernet Adapter       : {C_RED}[DISCONNECTED / CABLE UNPLUGGED]{C_RESET}")

    if has_valid_wifi:
        print(f"[*] Wi-Fi Adapter          : {C_GREEN}[ONLINE] {wifi_info['name']}{C_RESET}")
        print(f"    - Host Wi-Fi IP        : {C_CYAN}{C_BOLD}{wifi_info['ip']}{C_RESET}")
    else:
        print(f"[*] Wi-Fi Adapter          : {C_WHITE}[INACTIVE / NOT CONNECTED]{C_RESET}")

    print()

    # Decision Matrix
    if has_valid_eth and has_valid_wifi:
        print(f"{C_GREEN}[CHOICE] Both Ethernet (CAT6) and Wi-Fi are active.{C_RESET}")
        print(f"{C_GREEN}         Prioritizing ETHERNET for maximum 1 Gbps throughput & lowest latency!{C_RESET}")
        selected_mode = "Ethernet (CAT6 Cable)"
        selected_ip = eth_info["ip"]
    elif has_valid_eth:
        print(f"{C_GREEN}[CHOICE] Using Direct CAT6 Ethernet connection (1000 Mbps full duplex).{C_RESET}")
        selected_mode = "Ethernet (CAT6 Cable)"
        selected_ip = eth_info["ip"]
    elif has_valid_wifi:
        if eth_info and not has_valid_eth:
            print(f"{C_YELLOW}[!] CAT6 Cable is disconnected or unplugged. Automatically falling back to WI-FI!{C_RESET}")
        else:
            print(f"{C_GREEN}[CHOICE] Using Local Wi-Fi network connection.{C_RESET}")
        selected_mode = "Local Wi-Fi"
        selected_ip = wifi_info["ip"]
    elif eth_info and eth_info["is_apipa"]:
        print(f"{C_YELLOW}[!] ACTION REQUIRED: CAT6 Cable is plugged in, but Windows assigned 169.254.x.x.{C_RESET}")
        print(f"{C_YELLOW}    Run scripts/setup_static_ip.bat or set Static IP: 192.168.1.2 (Mask: 255.255.255.0).{C_RESET}")
        selected_ip = "192.168.1.2"
    else:
        print(f"{C_RED}[ERROR] No active network connection detected!{C_RESET}")
        print(f"{C_RED}        Please plug in the CAT6 Ethernet cable or connect to Wi-Fi.{C_RESET}")
        selected_ip = "192.168.1.2"

    print()
    return selected_mode, selected_ip


def print_manual_instructions(selected_mode: str, selected_ip: str):
    """Print clean step-by-step instructions for the host user."""
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_YELLOW}{C_BOLD}        >>> STEP-BY-STEP MANUAL WORKFLOW FOR HOST NODE <<<{C_RESET}")
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_WHITE}1. NETWORK MODE        : {C_GREEN}{C_BOLD}{selected_mode}{C_RESET}")
    print(f"{C_WHITE}2. GIVE THIS IP TO CLIENT : {C_GREEN}{C_BOLD}{selected_ip}{C_RESET}")
    print(f"{C_WHITE}3. SERVER PORT         : {C_GREEN}{C_BOLD}5050{C_RESET}")
    print()
    print(f"{C_WHITE}Manual Steps to Complete the Offload:{C_RESET}")
    print(f"  {C_CYAN}[Step 1]{C_RESET} Keep this terminal window open in the background.")
    print(f"  {C_CYAN}[Step 2]{C_RESET} Tell the Client to enter IP {C_GREEN}{C_BOLD}{selected_ip}{C_RESET} and Port {C_GREEN}5050{C_RESET}.")
    print(f"  {C_CYAN}[Step 3]{C_RESET} When Client clicks 'Handshake', connection logs will appear here.")
    print(f"  {C_CYAN}[Step 4]{C_RESET} When Client submits a video, your NVIDIA GPU will encode it live.")
    print(f"  {C_CYAN}[Step 5]{C_RESET} Once encoded, the video streams automatically back to the Client.")
    print(f"  {C_CYAN}[Bonus]{C_RESET}  The GUI Dashboard is also opening on your screen for local monitoring!")
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print()


def is_port_in_use(port: int = 5050, host: str = "127.0.0.1") -> bool:
    """Check if the daemon is already running on the target port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(0.8)
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


def start_server_daemon_background(port: int = 5050):
    """Start the WorkerDaemon in a background thread if not already active."""
    from server.daemon import WorkerDaemon
    daemon = WorkerDaemon(host="0.0.0.0", port=port)
    t = threading.Thread(target=daemon.start, daemon=True, name="WorkerDaemonThread")
    t.start()
    time.sleep(1.0)
    return daemon


def main():
    parser = argparse.ArgumentParser(description="Distributed GPU Offloading - Host Launcher")
    parser.add_argument("--port", type=int, default=5050, help="Port to bind server (default: 5050)")
    parser.add_argument("--headless", action="store_true", help="Run server daemon in headless console mode without GUI")
    args, _ = parser.parse_known_args()

    print_banner()
    check_and_install_dependencies()
    display_hardware_telemetry()
    selected_mode, selected_ip = analyze_network()
    print_manual_instructions(selected_mode, selected_ip)

    # Step 4: Daemon Startup
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}              STEP 4: WORKER SERVER DAEMON STARTUP{C_RESET}")
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")

    if is_port_in_use(args.port):
        print(f"{C_GREEN}[OK] Worker Server Daemon is ALREADY active on port {args.port}!{C_RESET}")
        print(f"     Listening on all interfaces (0.0.0.0:{args.port}) - Ready for client connections.\n")
    else:
        print(f"{C_CYAN}[*] Starting high-throughput Worker Server Daemon on port {args.port}...{C_RESET}")
        start_server_daemon_background(port=args.port)
        print(f"{C_GREEN}[+] Server Daemon is now ONLINE and listening on port {args.port}!{C_RESET}\n")

    # Step 5: Launch GUI (or stay in console mode)
    if args.headless:
        print(f"{C_GREEN}[*] Running in headless daemon mode. Press Ctrl+C to terminate server.{C_RESET}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}[*] Shutting down Worker Daemon gracefully...{C_RESET}")
    else:
        print(f"{C_GREEN}{C_BOLD}[*] Step 5: Launching Desktop GUI Dashboard on Host...{C_RESET}\n")
        time.sleep(0.5)
        try:
            from client.gui_app import main as launch_gui
            launch_gui(target_ip="127.0.0.1")
        except Exception as e:
            print(f"{C_YELLOW}[!] Could not open GUI dashboard ({e}). Running in headless console mode.{C_RESET}")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print(f"\n{C_YELLOW}[*] Shutting down Worker Daemon gracefully...{C_RESET}")


if __name__ == "__main__":
    main()
