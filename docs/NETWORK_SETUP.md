# Networking & Direct Peer-to-Peer Connection Guide
**Course**: CSC-334 Parallel and Distributed Computing  
**Task 1**: Networking & Handshake Protocol Setup

---

## 1. Network Topologies Supported

The Distributed GPU Offloading system supports three distinct physical and logical network topologies:

1. **Direct Peer-to-Peer CAT6 Ethernet Link (Recommended for Maximum Throughput)**:
   - Connects Client Laptop and Worker Desktop directly using a standard CAT6 RJ45 patch cable (auto-MDIX eliminates the need for crossover cables on modern NICs).
   - Achieves up to **1000 Mbps (1 Gbps) or 2.5 Gbps** full-duplex with sub-millisecond round-trip latency ($\sim 0.3 - 0.8\text{ ms}$).
2. **Dedicated Wi-Fi Local Subnet (5 GHz / Wi-Fi 6)**:
   - Both nodes connect to a high-speed local wireless router or mobile hotspot.
   - Typical throughput: $300 - 800\text{ Mbps}$, latency: $2 - 6\text{ ms}$.
3. **Local Loopback Subnet (`127.0.0.1`)**:
   - Used for development, single-node evaluation, and automated testing.

```
+------------------------------------+             +------------------------------------+
|       CLIENT LAPTOP (Client)       |   CAT6 /    |       WORKER DESKTOP (Server)      |
|  Static IP: 192.168.1.2            | <=========> |  Static IP: 192.168.1.1            |
|  Subnet:    255.255.255.0          |   Direct    |  Subnet:    255.255.255.0          |
|  Gateway:   192.168.1.1            |   LAN Cable |  Default Port: 5050                |
+------------------------------------+             +------------------------------------+
```

---

## 2. Step-by-Step Static IP Configuration

### Method A: Automated Batch Script (Windows)

We provide an interactive helper script in the repository:
```powershell
# Run with Administrator privileges
.\scripts\setup_static_ip.bat
```
- Select Option **[1]** on the **Server Node** (`192.168.1.1`).
- Select Option **[2]** on the **Client Node** (`192.168.1.2`).

---

### Method B: Manual Configuration via Windows Settings

#### On the Worker Node (Server):
1. Press `Win + R`, type `ncpa.cpl`, and hit Enter to open **Network Connections**.
2. Right-click your Ethernet adapter (or Wi-Fi adapter) $\rightarrow$ **Properties**.
3. Select **Internet Protocol Version 4 (TCP/IPv4)** $\rightarrow$ click **Properties**.
4. Select **Use the following IP address**:
   - **IP address**: `192.168.1.1`
   - **Subnet mask**: `255.255.255.0`
   - **Default gateway**: *(Leave blank)*
5. Click **OK** to apply.

#### On the Client Laptop:
1. Repeat steps 1–3 on the client machine.
2. Select **Use the following IP address**:
   - **IP address**: `192.168.1.2`
   - **Subnet mask**: `255.255.255.0`
   - **Default gateway**: `192.168.1.1`
3. Click **OK** to apply.

---

### Method C: Command-Line (`netsh` on Windows)

Open PowerShell or Command Prompt as Administrator:

**On Worker Node:**
```powershell
netsh interface ipv4 set address name="Ethernet" static 192.168.1.1 255.255.255.0
```

**On Client Node:**
```powershell
netsh interface ipv4 set address name="Ethernet" static 192.168.1.2 255.255.255.0 192.168.1.1
```

---

### Method D: Linux / Ubuntu Configuration

**On Worker Node:**
```bash
sudo ip addr flush dev eth0
sudo ip addr add 192.168.1.1/24 dev eth0
sudo ip link set eth0 up
```

**On Client Node:**
```bash
sudo ip addr flush dev eth0
sudo ip addr add 192.168.1.2/24 dev eth0
sudo ip link set eth0 up
```

---

## 3. Firewall & Port Opening

The server daemon listens on TCP port `5050` by default. To allow incoming client traffic through Windows Firewall on the worker node:

```powershell
# Run in Administrator PowerShell on Worker Node:
New-NetFirewallRule -DisplayName "Distributed GPU Offloading Daemon" `
                    -Direction Inbound `
                    -LocalPort 5050 `
                    -Protocol TCP `
                    -Action Allow
```

---

## 4. Verification & Handshake Latency Test

1. **ICMP Ping Verification**:
   From Client Laptop:
   ```powershell
   ping 192.168.1.1 -n 4
   ```
   *Expected Result*: 0% packet loss, RTT $< 1\text{ ms}$ over CAT6.

2. **Application-Layer Protocol Handshake**:
   - Start the server daemon on worker node:
     ```powershell
     python start_server.py --port 5050
     ```
   - On the client desktop GUI, input `192.168.1.1` and port `5050`, then click **Handshake & Ping Check**.
   - The status badge will illuminate green: `● ONLINE: 192.168.1.1:5050 (0.64 ms)` and display remote GPU model and VRAM telemetry.
