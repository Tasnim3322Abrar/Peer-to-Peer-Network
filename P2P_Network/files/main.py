"""
main.py - Tkinter user interface for the P2P assignment.
Run with:  python main.py
"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from p2p_node import P2PNode


class App:
    def __init__(self, root):
        self.root = root
        root.title("UAP P2P Network")
        root.geometry("900x620")
        root.minsize(760, 520)

        self.node = None
        self.peer_ids = []                 # same order as the listbox rows
        self.events = queue.Queue()        # worker threads -> UI thread (thread-safe)

        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.process_events)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- My Peer
        f1 = ttk.LabelFrame(self.root, text="My Peer")
        f1.pack(fill="x", **pad)
        ttk.Label(f1, text="Name:").grid(row=0, column=0, **pad)
        self.name_var = tk.StringVar(value="Alice")
        self.name_entry = ttk.Entry(f1, textvariable=self.name_var, width=16)
        self.name_entry.grid(row=0, column=1, **pad)
        ttk.Label(f1, text="Port:").grid(row=0, column=2, **pad)
        self.port_var = tk.StringVar(value="5000")
        self.port_entry = ttk.Entry(f1, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, **pad)
        self.start_btn = ttk.Button(f1, text="Start Peer", command=self.start_peer)
        self.start_btn.grid(row=0, column=4, **pad)
        self.stop_btn = ttk.Button(f1, text="Stop", command=self.stop_peer, state="disabled")
        self.stop_btn.grid(row=0, column=5, **pad)
        self.info_var = tk.StringVar(value="Peer not started")
        ttk.Label(f1, textvariable=self.info_var).grid(row=1, column=0, columnspan=6,
                                                       sticky="w", **pad)

        # --- Connect
        f2 = ttk.LabelFrame(self.root, text="Connect to Another Peer")
        f2.pack(fill="x", **pad)
        ttk.Label(f2, text="IP:").grid(row=0, column=0, **pad)
        self.ip_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(f2, textvariable=self.ip_var, width=18).grid(row=0, column=1, **pad)
        ttk.Label(f2, text="Port:").grid(row=0, column=2, **pad)
        self.rport_var = tk.StringVar(value="5001")
        ttk.Entry(f2, textvariable=self.rport_var, width=8).grid(row=0, column=3, **pad)
        ttk.Button(f2, text="Connect", command=self.connect_peer).grid(row=0, column=4, **pad)

        # --- Middle: peer list + log
        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, **pad)

        pf = ttk.LabelFrame(mid, text="Connected Peers (select one to send)")
        pf.pack(side="left", fill="y", padx=(0, 6))
        self.peer_list = tk.Listbox(pf, width=32, exportselection=False)
        self.peer_list.pack(fill="both", expand=True, padx=4, pady=4)

        lf = ttk.LabelFrame(mid, text="Messages / Events")
        lf.pack(side="left", fill="both", expand=True)
        self.log_box = scrolledtext.ScrolledText(lf, state="disabled", wrap="word",
                                                 font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Send text
        f3 = ttk.LabelFrame(self.root, text="Send Text")
        f3.pack(fill="x", **pad)
        self.msg_var = tk.StringVar()
        entry = ttk.Entry(f3, textvariable=self.msg_var)
        entry.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        entry.bind("<Return>", lambda e: self.send_text())
        ttk.Button(f3, text="Send", command=self.send_text).pack(side="right", padx=6)

        # --- Send file
        f4 = ttk.LabelFrame(self.root, text="Send File")
        f4.pack(fill="x", **pad)
        ttk.Label(f4, text="Text, image, audio, video, PDF, ZIP, etc.").pack(side="left", padx=6)
        ttk.Button(f4, text="Choose File & Send", command=self.send_file).pack(
            side="right", padx=6, pady=6)

        # --- Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").pack(fill="x", side="bottom")

    # -------------------------------------------------------------- helpers
    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def process_events(self):
        """Runs in the UI thread; drains events posted by network threads."""
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log(payload)
                    self.status_var.set(payload[:120])
                elif kind == "peers":
                    self.refresh_peers()
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def refresh_peers(self):
        selected = self.selected_peer_id()
        self.peer_list.delete(0, "end")
        self.peer_ids = []
        if not self.node:
            return
        for pid, name, ip, port in self.node.get_peers():
            self.peer_list.insert("end", f"{name} [{pid}] {ip}:{port}")
            self.peer_ids.append(pid)
        if selected in self.peer_ids:
            self.peer_list.selection_set(self.peer_ids.index(selected))

    def selected_peer_id(self):
        sel = self.peer_list.curselection()
        if not sel or sel[0] >= len(self.peer_ids):
            return None
        return self.peer_ids[sel[0]]

    def error(self, text):
        self.events.put(("log", f"[ERROR] {text}"))

    # -------------------------------------------------------------- actions
    def start_peer(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a peer name.")
            return
        try:
            port = int(self.port_var.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Port must be a number between 1 and 65535.")
            return

        node = P2PNode(name, port,
                       on_log=lambda t: self.events.put(("log", t)),
                       on_peers_changed=lambda: self.events.put(("peers", None)))
        try:
            node.start()
        except OSError as e:
            messagebox.showerror("Error", f"Could not start peer on port {port}:\n{e}")
            return
        self.node = node
        self.info_var.set(f"{name} | ID: {node.id} | Port: {port}")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.name_entry.config(state="disabled")
        self.port_entry.config(state="disabled")

    def stop_peer(self):
        if self.node:
            self.node.stop()
            self.node = None
        self.refresh_peers()
        self.info_var.set("Peer not started")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.name_entry.config(state="normal")
        self.port_entry.config(state="normal")

    def connect_peer(self):
        if not self.node:
            messagebox.showerror("Error", "Start your peer first.")
            return
        ip, port = self.ip_var.get().strip(), self.rport_var.get().strip()
        self.status_var.set(f"Connecting to {ip}:{port} ...")
        threading.Thread(target=self._connect_worker, args=(self.node, ip, port),
                         daemon=True).start()

    def _connect_worker(self, node, ip, port):
        try:
            peer = node.connect(ip, port)
            self.events.put(("log", f"[SYSTEM] Connected to {peer.name} ({ip}:{peer.port})"))
        except Exception as e:                      # never crash the UI
            self.error(f"Connection failed: {e}")

    def send_text(self):
        if not self.node:
            messagebox.showerror("Error", "Start your peer first.")
            return
        pid = self.selected_peer_id()
        if pid is None:
            messagebox.showwarning("No peer selected", "Select a connected peer first.")
            return
        text = self.msg_var.get().strip()
        if not text:
            return
        try:
            self.node.send_text(pid, text)
            self.msg_var.set("")
        except Exception as e:
            self.error(str(e))

    def send_file(self):
        if not self.node:
            messagebox.showerror("Error", "Start your peer first.")
            return
        pid = self.selected_peer_id()
        if pid is None:
            messagebox.showwarning("No peer selected", "Select a connected peer first.")
            return
        path = filedialog.askopenfilename(title="Choose a file to send")
        if not path:
            return
        self.status_var.set("Sending file ...")
        # Send in a background thread so big files do not freeze the window.
        threading.Thread(target=self._send_file_worker, args=(self.node, pid, path),
                         daemon=True).start()

    def _send_file_worker(self, node, pid, path):
        try:
            node.send_file(pid, path)
        except Exception as e:
            self.error(str(e))

    def on_close(self):
        if self.node:
            self.node.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
