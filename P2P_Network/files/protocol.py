"""
protocol.py - Application-level protocol for the P2P assignment.

Every message on the wire is FRAMED like this:

    [4-byte length (big-endian)][JSON payload (UTF-8)]

TCP is a byte stream (it has no message boundaries), so the receiver first reads
exactly 4 bytes to learn the length, then reads exactly that many bytes.

File transfer = a "file" JSON message (metadata) followed by `filesize` RAW bytes.
"""
import json
import struct

HEADER_SIZE = 4                  # bytes used for the length prefix
MAX_MESSAGE_SIZE = 1024 * 1024   # 1 MB safety limit for a JSON message
CHUNK_SIZE = 64 * 1024           # 64 KB chunks for file transfer

# Message types
HELLO = "hello"
HELLO_ACK = "hello_ack"
TEXT = "text"
FILE = "file"


class ProtocolError(Exception):
    """Raised when the other side sends something that breaks the protocol."""


# ---------- message builders ----------
def make_hello(peer_id, peer_name, port):
    return {"type": HELLO, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_hello_ack(peer_id, peer_name, port):
    return {"type": HELLO_ACK, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_text(sender_id, sender_name, message):
    return {"type": TEXT, "sender_id": sender_id, "sender_name": sender_name,
            "message": message}


def make_file(sender_id, sender_name, filename, filesize):
    return {"type": FILE, "sender_id": sender_id, "sender_name": sender_name,
            "filename": filename, "filesize": filesize}


# ---------- framing ----------
def encode_message(msg):
    """dict -> [4-byte length][json bytes]"""
    payload = json.dumps(msg).encode("utf-8")
    return struct.pack("!I", len(payload)) + payload


def send_message(sock, msg):
    sock.sendall(encode_message(msg))


def recv_exact(sock, n):
    """Read EXACTLY n bytes (recv may return fewer, so we loop)."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:                       # empty bytes = peer closed connection
            raise ConnectionError("Peer closed the connection")
        buf.extend(chunk)
    return bytes(buf)


def recv_message(sock):
    """Read one framed JSON message and return it as a dict."""
    header = recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack("!I", header)
    if length == 0 or length > MAX_MESSAGE_SIZE:
        raise ProtocolError(f"Invalid message length: {length}")
    payload = recv_exact(sock, length)
    try:
        msg = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProtocolError(f"Malformed message: {e}")
    if not isinstance(msg, dict) or "type" not in msg:
        raise ProtocolError("Message has no 'type' field")
    return msg
