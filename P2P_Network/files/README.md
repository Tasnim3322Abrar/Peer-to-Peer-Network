# UAP P2P Network – Text & File Sharing (CSE 433)

A lightweight peer-to-peer application in Python. Each running copy of the program is one **peer**
that is both a TCP **server** (accepts connections) and a TCP **client** (connects to others).
Peers exchange text messages and any binary file (image, audio, video, PDF, ZIP...) directly,
with **no central server**.

## Requirements
- Python 3.9 or later (Tkinter is included with the standard Windows/macOS installers)
- No third-party packages (see `requirements.txt`)

## Project structure
| File | Responsibility |
|---|---|
| `main.py` | Tkinter user interface |
| `p2p_node.py` | Server + client sockets, threads, handshake, text and file transfer |
| `protocol.py` | Message framing `[4-byte length][JSON]`, encode/decode |
| `downloads/` | Received files are saved here |

## Setup and running (PyCharm)
1. **File > Open** and select the `P2P_Network` folder.
2. **File > Settings > Project > Python Interpreter**: choose Python 3.9+ (add one if needed). No packages to install.
3. Open `main.py`. To run several peers: **Run > Edit Configurations**, select `main`, tick **Allow multiple instances**
   (called *Allow parallel run* in older versions), click OK.
4. Right-click `main.py` > **Run 'main'**. Run it again for every additional peer.

Command line alternative: `python main.py`

## Connecting two peers (same computer)
1. Window 1: Name `Alice`, Port `5000`, click **Start Peer**.
2. Window 2: Name `Bob`, Port `5001`, click **Start Peer**.
3. In Bob's window: IP `127.0.0.1`, Port `5000`, click **Connect**.
4. Both windows now list each other under *Connected Peers*.

## Connecting over a LAN (two or more computers)
1. All computers must be on the same Wi-Fi/LAN.
2. Find the IP of the computer you want to connect to: Windows `ipconfig` (IPv4 Address), Linux/macOS `ifconfig` or `ip a`.
3. Use that IP (e.g. `192.168.1.10`) and its port in the *Connect* box.
4. If it fails, allow Python through the Windows firewall (or the chosen port).

## Sending text
Click a peer in the *Connected Peers* list, type in *Send Text*, press **Send** (or Enter).

## Transferring files
Click a peer, press **Choose File & Send**, pick any file. The receiver saves it in `downloads/`
(an existing file is never overwritten; `photo_1.jpg` etc. is used).

## How it works (short)
1. Peer starts: `socket -> bind -> listen`, accept-loop thread starts.
2. Connect: `socket -> connect`, then `hello` / `hello_ack` handshake exchanges name, id and listening port.
3. One thread per connection reads messages.
4. Every JSON message is framed as `[4-byte length][JSON]`.
5. File = `file` JSON (filename, filesize) followed by exactly `filesize` raw bytes sent in 64 KB chunks.

## Error handling
Invalid IP/port, connection refused, timeout, peer disconnecting (also mid-transfer), missing file,
sending with no peer selected, port already in use. The app shows a message instead of crashing.

## Screenshots
Add your own screenshots here (Peer 1, Peer 2, Peer 3 windows).
