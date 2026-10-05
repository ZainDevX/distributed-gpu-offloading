"""
Automated One-Click Client Launcher for Distributed GPU Offloading System.
Course: CSC-334 Parallel and Distributed Computing

Features:
- Validates Python 3.9+ environment.
- Verifies and auto-installs all required dependencies.
- Smart Network Detection (prioritizes CAT6 Ethernet if plugged in; falls back to Wi-Fi if unplugged).
- Prints comprehensive, step-by-step manual workflow instructions in the terminal.
- Launches the modern CustomTkinter Desktop GUI Dashboard pre-configured.
"""

import importlib
import os
import socket
import subprocess
import sys
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
    print(f"{C_CYAN}{C_BOLD}       DISTRIBUTED GPU TASK OFFLOADING - CLIENT DASHBOARD{C_RESET}")
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


def analyze_network():
    """
    Intelligently inspect network interfaces.
    Handles edge cases:
    - Both Wi-Fi and Ethernet active: chooses Ethernet if CAT6 cable is connected.
    - If CAT6 cable is unplugged: falls back to Wi-Fi.
    - If CAT6 cable has APIPA (169.254.x.x): guides user on static IP setup.
    """
    print(f"{C_CYAN}--------------------------------------------------------------------{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}           STEP 2: SMART NETWORK DETECTION & SELECTION{C_RESET}")
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

    # Determine connection mode & recommended Host IP
    recommended_host_ip = "192.168.1.2"
    selected_mode = "Ethernet"

    has_valid_eth = eth_info and eth_info["is_up"] and eth_info["speed"] > 0 and not eth_info["is_apipa"]
    has_valid_wifi = wifi_info and wifi_info["is_up"] and not wifi_info["ip"].startswith("169.254.")

    if has_valid_eth:
        print(f"[*] Ethernet Adapter       : {C_GREEN}[ONLINE] {eth_info['name']}{C_RESET}")
        print(f"    - Physical Link Speed  : {C_GREEN}{eth_info['speed']} Mbps (CAT6 Cable Connected){C_RESET}")
        print(f"    - Client Ethernet IP   : {C_GREEN}{C_BOLD}{eth_info['ip']}{C_RESET}")
    elif eth_info and eth_info["is_apipa"]:
        print(f"[*] Ethernet Adapter       : {C_YELLOW}[CABLE DETECTED BUT UNCONFIGURED]{C_RESET}")
        print(f"    - Current IP           : {C_YELLOW}{eth_info['ip']} (Auto-IP / Needs Static IP){C_RESET}")
    else:
        print(f"[*] Ethernet Adapter       : {C_RED}[DISCONNECTED / CABLE UNPLUGGED]{C_RESET}")

    if has_valid_wifi:
        print(f"[*] Wi-Fi Adapter          : {C_GREEN}[ONLINE] {wifi_info['name']}{C_RESET}")
        print(f"    - Client Wi-Fi IP      : {C_CYAN}{C_BOLD}{wifi_info['ip']}{C_RESET}")
    else:
        print(f"[*] Wi-Fi Adapter          : {C_WHITE}[INACTIVE / NOT CONNECTED]{C_RESET}")

    print()

    # Decision Matrix
    if has_valid_eth and has_valid_wifi:
        print(f"{C_GREEN}[CHOICE] Both Ethernet (CAT6) and Wi-Fi are active.{C_RESET}")
        print(f"{C_GREEN}         Prioritizing ETHERNET for maximum 1 Gbps throughput & <1ms latency!{C_RESET}")
        selected_mode = "Ethernet (CAT6)"
        recommended_host_ip = "192.168.1.2"
    elif has_valid_eth:
        print(f"{C_GREEN}[CHOICE] Using Direct CAT6 Ethernet connection (1000 Mbps full duplex).{C_RESET}")
        selected_mode = "Ethernet (CAT6)"
        recommended_host_ip = "192.168.1.2"
    elif has_valid_wifi:
        if eth_info and not has_valid_eth:
            print(f"{C_YELLOW}[!] CAT6 Cable is disconnected or not configured. Automatically falling back to WI-FI!{C_RESET}")
        else:
            print(f"{C_GREEN}[CHOICE] Using Local Wi-Fi network connection.{C_RESET}")
        selected_mode = "Wi-Fi"
        # Guess default host subnet
        wifi_parts = wifi_info["ip"].split(".")
        recommended_host_ip = f"{wifi_parts[0]}.{wifi_parts[1]}.{wifi_parts[2]}.238"  # common host or let user adjust
    elif eth_info and eth_info["is_apipa"]:
        print(f"{C_YELLOW}[!] ACTION REQUIRED: CAT6 Cable is plugged in, but Windows assigned 169.254.x.x.{C_RESET}")
        print(f"{C_YELLOW}    Run scripts/setup_static_ip.bat or set Static IP: 192.168.1.1 (Mask: 255.255.255.0).{C_RESET}")
        recommended_host_ip = "192.168.1.2"
    else:
        print(f"{C_RED}[ERROR] No active network connection detected!{C_RESET}")
        print(f"{C_RED}        Please plug in the CAT6 Ethernet cable or connect to Wi-Fi.{C_RESET}")
        recommended_host_ip = "192.168.1.2"

    print()
    return selected_mode, recommended_host_ip


def print_manual_instructions(selected_mode: str, recommended_host_ip: str):
    """Print clean step-by-step instructions for the client user."""
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_YELLOW}{C_BOLD}       >>> STEP-BY-STEP MANUAL WORKFLOW FOR CLIENT LAPTOP <<<{C_RESET}")
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print(f"{C_WHITE}1. NETWORK MODE        : {C_GREEN}{C_BOLD}{selected_mode}{C_RESET}")
    print(f"{C_WHITE}2. WORKER HOST IP      : {C_GREEN}{C_BOLD}{recommended_host_ip}{C_RESET}")
    print(f"{C_WHITE}3. TARGET PORT         : {C_GREEN}{C_BOLD}5050{C_RESET}")
    print()
    print(f"{C_WHITE}Follow these steps in the GUI window that is opening:{C_RESET}")
    print(f"  {C_CYAN}[Step 1]{C_RESET} Verify {C_WHITE}'Worker IP'{C_RESET} is set to {C_GREEN}{recommended_host_ip}{C_RESET} (or the Host's IP).")
    print(f"  {C_CYAN}[Step 2]{C_RESET} Click the {C_GREEN}'[Handshake & Ping Check]'{C_RESET} button.")
    print(f"           - Status badge will turn {C_GREEN}GREEN [Connected]{C_RESET} with sub-millisecond ping.")
    print(f"           - The Host's GPU name (e.g. GeForce GTX 1050 4GB) will appear.")
    print(f"  {C_CYAN}[Step 3]{C_RESET} Click {C_GREEN}'[Browse...]'{C_RESET} to pick a video, OR click {C_GREEN}'[Generate Sample Video]'{C_RESET}.")
    print(f"  {C_CYAN}[Step 4]{C_RESET} Select Target Resolution (e.g. 1080p / 720p) and Encoder {C_GREEN}h264_nvenc{C_RESET}.")
    print(f"  {C_CYAN}[Step 5]{C_RESET} Click {C_GREEN}'[Start Remote GPU Offload]'{C_RESET}!")
    print(f"           - The video will stream to the Host GPU over the network.")
    print(f"           - Real-time FPS and percentage will update live on your screen.")
    print(f"           - The completed video is saved in {C_WHITE}'client_outputs/'{C_RESET} with SHA-256 match!")
    print(f"{C_YELLOW}{C_BOLD}===================================================================={C_RESET}")
    print()


def main():
    print_banner()
    check_and_install_dependencies()
    selected_mode, target_ip = analyze_network()
    print_manual_instructions(selected_mode, target_ip)

    print(f"{C_GREEN}{C_BOLD}[*] Launching Client Desktop GUI Dashboard...{C_RESET}\n")
    time.sleep(0.5)

    from client.gui_app import main as launch_gui
    launch_gui(target_ip=target_ip)


if __name__ == "__main__":
    main()
