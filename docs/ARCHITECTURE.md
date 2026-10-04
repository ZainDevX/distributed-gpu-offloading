# System Architecture & Technical Specification
**Course**: CSC-334 Parallel and Distributed Computing  
**Project**: Distributed GPU Offloading System

---

## 1. High-Level Architectural Pattern

The system implements an asynchronous **Client-Server Master-Worker Architecture** designed to bridge resource-constrained edge devices (clients) with high-throughput remote computing accelerators (workers).

```mermaid
graph TD
    subgraph Client ["Client Laptop (Resource-Constrained)"]
        UI["CustomTkinter Desktop GUI"]
        FP["File Picker & Media Prober"]
        CFG["Job Configuration Matrix"]
        LE["Local CPU Engine (Baseline)"]
        NC["Network Client (Socket / Streaming)"]
        TERM["Real-time Terminal Logger"]
    end

    subgraph Channel ["High-Throughput Network Link (CAT6 / 5GHz Wi-Fi)"]
        TCP["Binary Framed TCP Protocol (Port 5050)"]
    end

    subgraph Server ["Remote Worker Node (Dedicated GPU)"]
        DAEMON["Headless Daemon Listener"]
        HS["Handshake & Latency Monitor"]
        TQ["Thread-safe Task Queue Manager"]
        GD["GPU Detector & Telemetry Engine"]
        EE["Execution Engine (FFmpeg NVENC / CUDA)"]
        SHA["SHA-256 Streaming Integrity Validator"]
    end

    UI --> FP
    UI --> CFG
    UI --> LE
    CFG --> NC
    NC <-->|TCP Packets| TCP
    TCP <-->|Framed Sockets| DAEMON
    DAEMON --> HS
    DAEMON --> GD
    DAEMON --> TQ
    TQ --> EE
    EE -->|Progress Pipe| DAEMON
    DAEMON --> SHA
    NC --> TERM
    NC --> UI
```

---

## 2. Framed Binary Network Protocol Layout

To ensure minimal protocol overhead, deterministic packet framing, and zero reliance on heavy web frameworks, the system employs a custom **16-byte fixed-header binary streaming protocol**:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Magic Identifier: 'DGPO' (4 Bytes)             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version (1B) |  MsgType (1B) |         Flags (2 Bytes)       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                    Payload Length (8 Bytes uint64)            +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                   Payload (Variable Length)                   +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Packet Protocol Fields:
- **Magic Identifier** (`4 Bytes`, `b"DGPO"`): Validates network alignment and protects against spurious socket data.
- **Version** (`1 Byte`, `uint8`): Enforces client-server protocol compatibility check.
- **Message Type** (`1 Byte`, `uint8`):
  - `MSG_PING (0x01)`: RTT latency measurement ping.
  - `MSG_PONG (0x02)`: Latency measurement response with server timestamps.
  - `MSG_HANDSHAKE_REQ (0x03)`: Client initiation and metadata.
  - `MSG_HANDSHAKE_RESP (0x04)`: Worker capability manifest (GPU model, VRAM, supported codecs).
  - `MSG_JOB_SUBMIT (0x05)`: Offload job descriptor, input checksum, transcode config.
  - `MSG_JOB_ACCEPTED (0x06)`: Acceptance confirmation with unique `job_id`.
  - `MSG_FILE_CHUNK (0x07)`: 64 KB raw binary chunk streaming.
  - `MSG_FILE_COMPLETE (0x08)`: End-of-file boundary with expected SHA-256.
  - `MSG_FILE_ACK (0x09)`: Verification acknowledgement (success or corruption signal).
  - `MSG_PROGRESS (0x0A)`: Real-time asynchronous metrics (frame, fps, %, speed, bitrate).
  - `MSG_JOB_FINISHED (0x0B)`: GPU processing completion signal and output metadata.
  - `MSG_DOWNLOAD_REQ (0x0C)`: Client request to retrieve rendered output.
  - `MSG_DOWNLOAD_START (0x0D)`: Output payload metadata header.
  - `MSG_ERROR (0x0E)`: Graceful error propagation.
  - `MSG_CANCEL (0x0F)`: Immediate execution termination request.
- **Flags** (`2 Bytes`, `uint16`): Reserved for compression and priority bits.
- **Payload Length** (`8 Bytes`, `uint64`): Exact byte length of the variable payload.

---

## 3. End-to-End Offloading State Machine

```mermaid
sequenceDiagram
    autonumber
    participant C as Client GUI
    participant N as Client Network
    participant S as Server Daemon
    participant Q as Task Queue
    participant G as GPU / NVENC Engine

    Note over C,S: Phase 1: Connection & Latency Handshake
    C->>N: Connect(192.168.1.1:5050)
    N->>S: TCP SYN-ACK Handshake
    N->>S: MSG_PING (Timestamp: T0)
    S-->>N: MSG_PONG (Latency = T1 - T0)
    N->>S: MSG_HANDSHAKE_REQ (Client info)
    S-->>N: MSG_HANDSHAKE_RESP (GPU: GTX 1050 4GB, Codecs: NVENC/MFT/x264)
    N-->>C: Update UI Status Badge & Latency

    Note over C,S: Phase 2: Checksum & Upload Pipeline
    C->>N: Offload Job (File, Config)
    N->>N: Calculate Local Input SHA-256
    N->>S: MSG_JOB_SUBMIT (Filename, Size, SHA-256, Parameters)
    S->>Q: Create Job Record
    S-->>N: MSG_JOB_ACCEPTED (job_id)
    loop 64 KB Binary Streaming
        N->>S: MSG_FILE_CHUNK (Binary Data)
    end
    N->>S: MSG_FILE_COMPLETE (SHA-256)
    S->>S: Stream SHA-256 Verification
    S-->>N: MSG_FILE_ACK (Status: OK)

    Note over S,G: Phase 3: Hardware-Accelerated Transcoding
    S->>Q: Enqueue Job
    Q->>G: Dispatch to NVENC Execution Engine
    loop Progress Streaming
        G-->>S: FFmpeg progress stdout (frame, fps, speed, out_time)
        S-->>N: MSG_PROGRESS (Live JSON metrics)
        N-->>C: Update Progress Bar, FPS, ETA
    end
    G-->>S: Transcode Complete (Output SHA-256)
    S->>Q: Mark Completed
    S-->>N: MSG_JOB_FINISHED (Metadata, Output Size, SHA-256)

    Note over C,S: Phase 4: Download & Integrity Verification
    N->>S: MSG_DOWNLOAD_REQ (job_id)
    S-->>N: MSG_DOWNLOAD_START (Output Metadata)
    loop 64 KB Binary Streaming
        S-->>N: MSG_FILE_CHUNK (Rendered Video)
    end
    S-->>N: MSG_FILE_COMPLETE (SHA-256)
    N->>N: Verify Download SHA-256 Integrity
    N->>S: MSG_FILE_ACK (Verified OK)
    N-->>C: Display Speedup, Save Output, Enable Video Player
```

---

## 4. Fault-Tolerance & Resilience Mechanisms

1. **In-Flight Data Integrity (SHA-256 End-to-End)**:
   - Input files are hashed before socket transmission. The worker server computes a streaming SHA-256 hash as chunks arrive. If a network corruption occurs, the worker immediately rejects the file (`MSG_FILE_ACK status=error`), purges the temporary file, and requests retransmission.
   - The same validation occurs upon downloading the rendered output back to the client.
2. **Network Timeout & Keepalive Management**:
   - Connection sockets employ `TCP_NODELAY` and strict timeout thresholds:
     - `CONNECT_TIMEOUT`: 5 seconds
     - `PING_TIMEOUT`: 3 seconds
     - `SOCKET_TIMEOUT`: 20 seconds
   - If an unexpected socket disconnection occurs, worker daemon releases GPU execution slots and cleans orphaned files in `server_workspace/`.
3. **Graceful Cancellation**:
   - When the user presses **Cancel**, an immediate `MSG_CANCEL` packet is dispatched. The server worker locates the active FFmpeg PID via `JobRecord.process_handle` and issues `proc.kill()`, freeing GPU VRAM and preventing wasted compute.
4. **Adaptive Fallback Engine**:
   - If a client requests `h264_nvenc` but the worker node has an outdated driver or lacks NVENC hardware, the daemon logs an informative diagnostic warning and falls back to hardware MFT or optimized `libx264` multi-threaded software encoding, guaranteeing 100% pipeline completion.
