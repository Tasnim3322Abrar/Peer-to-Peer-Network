# Viva Guide – P2P Network (CSE 433)

## 1. The whole process in one picture
```
Peer A  ->  IP + port  ->  TCP socket  ->  HELLO handshake  ->  framed JSON protocol  ->  text / file bytes  ->  Peer B
```
1. **Start**: `socket()`, `bind(("0.0.0.0", port))`, `listen()`, then a thread runs `accept()` in a loop. (`P2PNode.start`)
2. **Connect**: the other peer does `socket()`, `connect((ip, port))`. TCP 3-way handshake happens. (`P2PNode.connect`)
3. **HELLO**: client sends `hello {peer_id, peer_name, port}`, server replies `hello_ack {...}`. Now both know who the other is.
4. **Threads**: each connection gets its own thread running `_listen_loop`, which reads messages forever.
5. **Framing**: every message is `[4-byte length][JSON]`. Receiver reads 4 bytes, then exactly that many bytes (`recv_exact`).
6. **Text**: `{"type":"text", ...}` -> receiver prints `Alice -> You: ...`.
7. **File**: `{"type":"file","filename","filesize"}` then exactly `filesize` raw bytes in 64 KB chunks. Receiver reads exactly `filesize` bytes and writes them to `downloads/`.
8. **Disconnect**: `recv()` returns empty bytes -> `ConnectionError` -> peer removed from the list, UI updated, no crash.

## 2. Key code to be able to explain
- `protocol.encode_message` : `struct.pack("!I", len(payload)) + payload` ("!I" = unsigned 4-byte int, network/big-endian order)
- `protocol.recv_exact` : loops on `recv(n - len(buf))` until n bytes collected; empty result = peer closed
- `P2PNode._accept_loop` : server role. `P2PNode.connect` : client role.
- `P2PNode._receive_file` : `remaining = filesize; while remaining > 0: recv(min(64KB, remaining))`
- `Peer.send_lock` : stops a text message from being mixed into the middle of a file being sent.
- `main.py` uses a `queue` + `root.after()` because Tkinter must only be touched from the main thread.

## 3. The 20 viva questions – model answers
1. **Client vs server?** A server waits (listens) for incoming connections and serves requests; a client starts the connection. They are *roles*, not machine types.
2. **Why can one peer be both?** Roles belong to the connection, not the computer. A peer has a listening socket (server role) and also opens outgoing sockets with `connect()` (client role). Same program does both.
3. **Purpose of IP address?** Identifies a computer/network interface on the network (e.g. 192.168.1.10), so packets reach the right machine. 127.0.0.1 = this same computer (loopback).
4. **Purpose of port number?** Identifies which application/service on that computer gets the data (16-bit number, 1-65535). IP finds the machine, port finds the program.
5. **Why different ports on the same computer?** Only one socket can listen on a given IP:port at a time; a second `bind()` fails ("address already in use"). So Alice=5000, Bob=5001, Charlie=5002.
6. **What happens on `connect()`?** The client asks the OS to open a TCP connection to IP:port. TCP does the 3-way handshake (SYN, SYN-ACK, ACK). It fails with "connection refused" if nobody is listening, or times out if unreachable.
7. **What happens on `accept()`?** It blocks until a client connects, then returns a *new* socket for that client plus its address. The original listening socket keeps listening for more peers.
8. **Why TCP, not UDP?** TCP is reliable, ordered, and has no loss/duplication, which a file needs (a single missing byte corrupts a ZIP/video). UDP could lose or reorder packets and would require us to build reliability ourselves.
9. **Why threads?** `accept()` and `recv()` block. Without threads, the peer could wait on one connection and ignore others. One thread per connection plus one accept thread lets many peers communicate concurrently and keeps the UI responsive.
10. **Purpose of HELLO?** The handshake: peers exchange identity (id, name, listening port) before normal communication, so the app can show names in the peer list and know each peer's listening port. Also validates the other side speaks our protocol.
11. **What is message framing?** Defining where one message ends and the next begins in a byte stream. We use a 4-byte length prefix followed by the JSON payload.
12. **Why not assume one `recv()` = one message?** TCP is a byte stream with no boundaries. One `recv()` may return half a message, or two messages merged, depending on buffering/packet sizes. So we loop until we have exactly the bytes we need.
13. **Why send file metadata first?** The receiver must know the filename (to save it) and the filesize (to know exactly how many raw bytes follow and when to stop). Raw bytes alone carry no such information.
14. **Why chunks?** Reading a multi-GB video fully into memory would exhaust RAM. 64 KB chunks keep memory use small and constant for any file size.
15. **How does the receiver know the file is finished?** It counts: `remaining = filesize` from metadata, subtract each received chunk, stop at 0. It never relies on a single `recv()` or on the connection closing.
16. **What if the other peer disconnects?** `recv()` returns `b""` (or raises an error); we raise `ConnectionError`, remove the peer, update the list, log a message. A half-received file is deleted. The app does not crash.
17. **Where is the received file stored?** In the `downloads/` folder; existing names are not overwritten (`photo_1.jpg`).
18. **Is there a central server?** No. Every peer is both server and client and peers connect directly. (A "server socket" exists in each peer, but it is just that peer's own listener, not a central authority.)
19. **If the central server of a client-server system went offline?** All communication stops: single point of failure and bottleneck. In P2P, the remaining peers can still talk to each other.
20. **Challenges for a large-scale Internet P2P system?** Peer discovery (DHT/trackers/bootstrap nodes), NAT and firewall traversal, peers joining/leaving constantly (churn), routing/scaling, security (authentication, encryption, malicious peers), file integrity (hashes), fairness/bandwidth, data replication, consensus (for blockchain).

## 4. Extra questions you could be asked
- **Why `0.0.0.0`?** Listen on all network interfaces (loopback and Wi-Fi/LAN), so other computers can reach you. `127.0.0.1` would only accept local connections.
- **Why `SO_REUSEADDR`?** Lets you restart the peer on the same port immediately without waiting for the OS to release it.
- **Why `sendall()` rather than `send()`?** `send()` may send only part of the data; `sendall()` keeps sending until everything is sent.
- **Why JSON?** Human-readable, simple, built into Python. Raw file bytes are not JSON; they follow separately after the metadata.
- **Why a lock while sending?** A text sent from another thread during a file transfer would corrupt the byte stream. The per-peer `send_lock` keeps each message/file atomic.
- **Why a queue between the network threads and the UI?** Tkinter is not thread-safe; background threads put events in a queue and the UI thread reads it every 100 ms.
- **Why `daemon=True` threads?** They stop automatically when the program exits.
- **What is `peer_id` for?** Unique identity (random 8 hex chars). Two peers can have the same name; the ID is unique, and it prevents connecting to yourself or twice to the same peer.
- **What is `struct.pack("!I")`?** Packs an integer into 4 bytes in network byte order (big-endian).
- **Security weaknesses?** No encryption/authentication (explicitly out of scope). Mitigations in my code: filename sanitised with `os.path.basename` (no path traversal), JSON size limit of 1 MB, invalid filesize rejected.
- **What is TCP vs the application protocol?** TCP delivers a reliable byte stream; our application protocol (hello/text/file + framing) gives those bytes meaning.
- **Difference between `listening port` and the port you see on an incoming connection?** The OS assigns a random temporary (ephemeral) port to the connecting side, so that is why HELLO carries the real listening port.

## 5. Assignment inconsistencies worth mentioning
- Rubric says "Total marks: 20" but components add up to 30 (2+5+3+5+5+10).
- Zip example name is `22101001_A2_...` but the folder is `22101001_3A_...`.
- File says "Peer startup 2 marks" but Viva alone is 10 marks, so know your code well.

## 6. Demo script (follow the assignment's checklist)
1. Start Alice (5000), Bob (5001). 2. Bob connects to 127.0.0.1:5000. 3. Show peer lists. 4. Alice -> Bob text, Bob -> Alice text.
5. Alice sends image to Bob. 6. Bob sends audio to Alice. 7. Alice sends video to Bob.
8. Start Charlie (5002); connect to Alice and Bob. 9. Send text/files between Charlie and each.
10. Close one peer and show the others keep running and display "disconnected".
