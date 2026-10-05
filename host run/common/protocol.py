"""
Framed Binary Network Protocol for Distributed GPU Offloading.
Course: CSC-334 Parallel and Distributed Computing

Packet Layout:
+-------------------------------------------------------------------+
|  Magic Bytes (4B) | Version (1B) | MsgType (1B) | Flags (2B)      |
+-------------------------------------------------------------------+
|  Payload Length (8B uint64)                                       |
+-------------------------------------------------------------------+
|  Payload (Length bytes)                                           |
+-------------------------------------------------------------------+
Total Header Size: 16 Bytes
"""

import json
import socket
import struct
import time
from typing import Any, Dict, Optional, Tuple

from common.config import MAGIC_BYTES, PROTOCOL_VERSION

# Header Format: 4s (Magic), B (Version), B (MsgType), H (Flags), Q (Length)
HEADER_FORMAT = "!4sBBHQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 16 bytes

# Message Types
MSG_PING = 1
MSG_PONG = 2
MSG_HANDSHAKE_REQ = 3
MSG_HANDSHAKE_RESP = 4
MSG_JOB_SUBMIT = 5
MSG_JOB_ACCEPTED = 6
MSG_FILE_CHUNK = 7
MSG_FILE_COMPLETE = 8
MSG_FILE_ACK = 9
MSG_PROGRESS = 10
MSG_JOB_FINISHED = 11
MSG_DOWNLOAD_REQ = 12
MSG_DOWNLOAD_START = 13
MSG_ERROR = 14
MSG_CANCEL = 15
MSG_HEARTBEAT = 16

MESSAGE_NAMES = {
    MSG_PING: "PING",
    MSG_PONG: "PONG",
    MSG_HANDSHAKE_REQ: "HANDSHAKE_REQ",
    MSG_HANDSHAKE_RESP: "HANDSHAKE_RESP",
    MSG_JOB_SUBMIT: "JOB_SUBMIT",
    MSG_JOB_ACCEPTED: "JOB_ACCEPTED",
    MSG_FILE_CHUNK: "FILE_CHUNK",
    MSG_FILE_COMPLETE: "FILE_COMPLETE",
    MSG_FILE_ACK: "FILE_ACK",
    MSG_PROGRESS: "PROGRESS",
    MSG_JOB_FINISHED: "JOB_FINISHED",
    MSG_DOWNLOAD_REQ: "DOWNLOAD_REQ",
    MSG_DOWNLOAD_START: "DOWNLOAD_START",
    MSG_ERROR: "ERROR",
    MSG_CANCEL: "CANCEL",
    MSG_HEARTBEAT: "HEARTBEAT",
}


class ProtocolError(Exception):
    """Protocol violation or network transmission error."""
    pass


class ConnectionClosedError(ProtocolError):
    """Socket was unexpectedly closed by remote peer."""
    pass


def pack_header(msg_type: int, payload_len: int, flags: int = 0) -> bytes:
    """Pack protocol header into 16 bytes."""
    return struct.pack(HEADER_FORMAT, MAGIC_BYTES, PROTOCOL_VERSION, msg_type, flags, payload_len)


def unpack_header(header_bytes: bytes) -> Tuple[int, int, int]:
    """
    Unpack 16-byte header.
    Returns: (msg_type, flags, payload_len)
    Raises ProtocolError on invalid magic bytes or version mismatch.
    """
    if len(header_bytes) != HEADER_SIZE:
        raise ProtocolError(f"Header length mismatch: expected {HEADER_SIZE}, got {len(header_bytes)}")
    magic, version, msg_type, flags, payload_len = struct.unpack(HEADER_FORMAT, header_bytes)
    if magic != MAGIC_BYTES:
        raise ProtocolError(f"Invalid magic bytes: {magic!r}, expected {MAGIC_BYTES!r}")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Protocol version mismatch: {version} vs {PROTOCOL_VERSION}")
    return msg_type, flags, payload_len


def read_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Read exactly num_bytes from socket, raising ConnectionClosedError on EOF or reset."""
    data = bytearray()
    while len(data) < num_bytes:
        try:
            chunk = sock.recv(min(num_bytes - len(data), 65536))
        except (ConnectionResetError, ConnectionAbortedError) as e:
            raise ConnectionClosedError("Remote endpoint reset connection.") from e
        if not chunk:
            if len(data) == 0:
                raise ConnectionClosedError("Remote endpoint closed the socket.")
            raise ConnectionClosedError(f"Socket closed prematurely: received {len(data)} of {num_bytes} bytes.")
        data.extend(chunk)
    return bytes(data)


def send_packet(sock: socket.socket, msg_type: int, payload: bytes = b"", flags: int = 0) -> None:
    """Send header + payload atomically through socket."""
    header = pack_header(msg_type, len(payload), flags)
    sock.sendall(header + payload)


def recv_packet(sock: socket.socket) -> Tuple[int, int, bytes]:
    """
    Read the next framed packet from socket.
    Returns: (msg_type, flags, payload_bytes)
    """
    header_bytes = read_exact(sock, HEADER_SIZE)
    msg_type, flags, payload_len = unpack_header(header_bytes)
    payload = read_exact(sock, payload_len) if payload_len > 0 else b""
    return msg_type, flags, payload


def send_json(sock: socket.socket, msg_type: int, data: Dict[str, Any], flags: int = 0) -> None:
    """Helper to serialize dict as JSON and send packet."""
    json_bytes = json.dumps(data).encode("utf-8")
    send_packet(sock, msg_type, json_bytes, flags)


def recv_json(sock: socket.socket) -> Tuple[int, int, Dict[str, Any]]:
    """Helper to receive packet and deserialize JSON payload."""
    msg_type, flags, payload = recv_packet(sock)
    if not payload:
        return msg_type, flags, {}
    try:
        data = json.loads(payload.decode("utf-8"))
        return msg_type, flags, data
    except Exception as e:
        raise ProtocolError(f"Failed to decode JSON payload: {e}") from e
