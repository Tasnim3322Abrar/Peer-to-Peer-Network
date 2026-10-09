"""
p2p_node.py - The P2P node: every peer = TCP server + TCP client.

* Server role : an accept-loop thread waits for incoming connections.
* Client role : connect() opens a connection to another peer.
* Each connection gets its own listener thread (so many peers work at once).
"""
import ipaddress
import os
import socket
import threading
import uuid

import protocol as proto

CONNECT_TIMEOUT = 5      # seconds to wait when connecting
HANDSHAKE_TIMEOUT = 5    # seconds to wait for HELLO from a new connection


def close_socket(sock):
    """shutdown() first so any thread blocked in recv() wakes up and the remote
    side is told right away; then close()."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class Peer:
    """One live connection to a remote peer."""

    def __init__(self, peer_id, name, ip, listen_port, sock):
        self.id = peer_id
        self.name = name
        self.ip = ip
        self.port = listen_port          # the remote peer's LISTENING port
        self.sock = sock
        self.send_lock = threading.Lock()  # stops two sends mixing their bytes


class P2PNode:
    def __init__(self, name, port, on_log=None, on_peers_changed=None,
                 download_dir="downloads"):
        self.name = name
        self.port = port
        self.id = uuid.uuid4().hex[:8]
        self.download_dir = download_dir
        self.on_log = on_log or (lambda text: None)
        self.on_peers_changed = on_peers_changed or (lambda: None)

        self.server_socket = None
        self.running = False
        self.peers = {}                  # peer_id -> Peer
        self.peers_lock = threading.Lock()

    # ------------------------------------------------------------ lifecycle
    def start(self):
        """Create the TCP server socket and start accepting connections."""
        os.makedirs(self.download_dir, exist_ok=True)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen()
        except OSError:
            self.server_socket.close()
            raise
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._log(f"[SYSTEM] Peer started: {self.name} [{self.id}] on port {self.port}")

    def stop(self):
        """Close the server socket and every connection."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        with self.peers_lock:
            peers = list(self.peers.values())
            self.peers.clear()
        for p in peers:
            close_socket(p.sock)
        self.on_peers_changed()
        self._log("[SYSTEM] Peer stopped")

    # ------------------------------------------------------------ server role
    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
            except OSError:
                break                    # server socket closed -> stop loop
            threading.Thread(target=self._handle_incoming, args=(conn, addr),
                             daemon=True).start()

    def _handle_incoming(self, conn, addr):
        """Handshake with a peer that connected to us, then listen to it."""
        try:
            conn.settimeout(HANDSHAKE_TIMEOUT)
            hello = proto.recv_message(conn)
            if hello.get("type") != proto.HELLO:
                raise proto.ProtocolError("Expected hello")
            remote_id = str(hello["peer_id"])
            if remote_id == self.id:
                raise proto.ProtocolError("Cannot connect to self")
            proto.send_message(conn, proto.make_hello_ack(self.id, self.name, self.port))
            conn.settimeout(None)
            peer = Peer(remote_id, str(hello["peer_name"]), addr[0],
                        int(hello["port"]), conn)
        except (OSError, ConnectionError, proto.ProtocolError, KeyError, ValueError):
            conn.close()
            return
        if not self._register(peer):
            conn.close()
            return
        self._log(f"[SYSTEM] Connected to {peer.name}")
        self._listen_loop(peer)

    # ------------------------------------------------------------ client role
    def connect(self, ip, port):
        """Connect to another peer. Raises ValueError / OSError on failure."""
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError(f"Invalid IP address: {ip!r}")
        try:
            port = int(port)
            if not 1 <= port <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Invalid port (must be 1-65535)")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        try:
            sock.connect((ip, port))                         # <- TCP 3-way handshake
            proto.send_message(sock, proto.make_hello(self.id, self.name, self.port))
            reply = proto.recv_message(sock)
            if reply.get("type") != proto.HELLO_ACK:
                raise proto.ProtocolError("Expected hello_ack")
            sock.settimeout(None)
            peer = Peer(str(reply["peer_id"]), str(reply["peer_name"]), ip,
                        int(reply["port"]), sock)
            if peer.id == self.id:
                raise ConnectionError("You cannot connect to yourself")
            if not self._register(peer):
                raise ConnectionError(f"Already connected to {peer.name}")
        except Exception:
            sock.close()
            raise
        threading.Thread(target=self._listen_loop, args=(peer,), daemon=True).start()
        return peer

    # ------------------------------------------------------------ peer table
    def _register(self, peer):
        with self.peers_lock:
            if peer.id in self.peers:
                return False
            self.peers[peer.id] = peer
        self.on_peers_changed()
        return True

    def _remove_peer(self, peer, reason=None):
        with self.peers_lock:
            if self.peers.get(peer.id) is not peer:
                return
            del self.peers[peer.id]
        close_socket(peer.sock)
        if self.running:
            self._log(f"[SYSTEM] {peer.name} disconnected" + (f" ({reason})" if reason else ""))
        self.on_peers_changed()

    def get_peers(self):
        with self.peers_lock:
            return [(p.id, p.name, p.ip, p.port) for p in self.peers.values()]

    def _get_peer(self, peer_id):
        with self.peers_lock:
            peer = self.peers.get(peer_id)
        if peer is None:
            raise ValueError("That peer is not connected")
        return peer

    # ------------------------------------------------------------ receiving
    def _listen_loop(self, peer):
        """One thread per connection: read messages until the peer goes away."""
        try:
            while self.running:
                msg = proto.recv_message(peer.sock)
                mtype = msg.get("type")
                if mtype == proto.TEXT:
                    self._log(f"{peer.name} -> You: {msg.get('message', '')}")
                elif mtype == proto.FILE:
                    self._receive_file(peer, msg)
                else:
                    self._log(f"[ERROR] Unknown message type from {peer.name}: {mtype}")
        except (OSError, ConnectionError, proto.ProtocolError) as e:
            self._remove_peer(peer, str(e))

    def _receive_file(self, peer, msg):
        filename = os.path.basename(str(msg.get("filename", "")).replace("\\", "/"))
        size = msg.get("filesize")
        if not filename or not isinstance(size, int) or size < 0:
            raise proto.ProtocolError("Invalid file metadata")

        os.makedirs(self.download_dir, exist_ok=True)
        path = self._unique_path(filename)
        remaining = size                 # metadata tells us EXACTLY how many bytes follow
        try:
            with open(path, "wb") as f:
                while remaining > 0:
                    chunk = peer.sock.recv(min(proto.CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("Disconnected during file transfer")
                    f.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            if os.path.exists(path):
                os.remove(path)          # don't keep a half-received file
            raise
        self._log(f"{peer.name} -> You: File received: {os.path.basename(path)}  "
                  f"({size} bytes) saved to {path}")

    def _unique_path(self, filename):
        path = os.path.join(self.download_dir, filename)
        base, ext = os.path.splitext(filename)
        n = 1
        while os.path.exists(path):      # never overwrite an existing file
            path = os.path.join(self.download_dir, f"{base}_{n}{ext}")
            n += 1
        return path

    # ------------------------------------------------------------ sending
    def send_text(self, peer_id, text):
        peer = self._get_peer(peer_id)
        try:
            with peer.send_lock:
                proto.send_message(peer.sock, proto.make_text(self.id, self.name, text))
        except OSError as e:
            self._remove_peer(peer, str(e))
            raise ConnectionError(f"Send failed: {e}")
        self._log(f"You -> {peer.name}: {text}")

    def send_file(self, peer_id, filepath):
        peer = self._get_peer(peer_id)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File does not exist: {filepath}")
        size = os.path.getsize(filepath)
        name = os.path.basename(filepath)
        try:
            with peer.send_lock:         # metadata + bytes must stay together
                proto.send_message(peer.sock,
                                   proto.make_file(self.id, self.name, name, size))
                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(proto.CHUNK_SIZE)   # never load whole file
                        if not chunk:
                            break
                        peer.sock.sendall(chunk)
        except OSError as e:
            self._remove_peer(peer, str(e))
            raise ConnectionError(f"Send failed: {e}")
        self._log(f"You -> {peer.name}: File sent: {name} ({size} bytes)")

    def _log(self, text):
        self.on_log(text)
