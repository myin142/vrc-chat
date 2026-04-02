import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
from pythonosc import udp_client

VRCHAT_IP = "127.0.0.1"
VRCHAT_PORT = 9000

osc_client = udp_client.SimpleUDPClient(VRCHAT_IP, VRCHAT_PORT)

# Each action is a list of (address, value) tuples
ACTIONS = {
    "Reset": [
        ("/input/Vertical", 0.0),
        ("/input/Horizontal", 0.0),
        ("/input/LookHorizontal", 0.0),
        ("/input/Run", 0.0),
    ],
    "Run Circle": [
        ("/input/Vertical", 1.0),
        ("/input/Horizontal", 1.0),
        ("/input/LookHorizontal", 1.0),
    ],
    "Move Forward": [
        ("/input/Vertical", 1.0),
    ],
    "Move Back": [
        ("/input/Vertical", -1.0),
    ],
    "Move Left": [
        ("/input/Horizontal", -1.0),
    ],
    "Move Right": [
        ("/input/Horizontal", 1.0),
    ],
    "Jump": [
        ("/input/Jump", 1.0),
    ],
    "Toggle Voice": [
        ("/input/Voice", 0.0),
        ("/input/Voice", 1.0),
    ],
    "Run Forward": [
        ("/input/Run", 1.0),
        ("/input/Vertical", 1.0),
    ],
}

# Timed sequences: list of (duration_seconds, [(address, value), ...])
# Each step fully specifies its input state so transitions are clean.
TIMED_SEQUENCES = {
    "Large Circle": [
        # Run straight forward
        (0.6, [
            ("/input/Run", 1.0),
            ("/input/Vertical", 1.0),
            ("/input/LookHorizontal", 0.0),
        ]),
        # Run while turning right
        (0.4, [
            ("/input/Run", 0.0),
            ("/input/Vertical", 1.0),
            ("/input/LookHorizontal", 1.0),
        ]),
    ],
}

_hold_thread = None
_holding = False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VRC OSC Controls")
        self.resizable(False, False)
        self._build_ui()

    def _build_ui(self):
        # ── Connection bar ──────────────────────────────────────────────
        conn_frame = ttk.LabelFrame(self, text="Connection", padding=8)
        conn_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 4), sticky="ew")

        ttk.Label(conn_frame, text="IP:").grid(row=0, column=0, sticky="w")
        self.ip_var = tk.StringVar(value=VRCHAT_IP)
        ttk.Entry(conn_frame, textvariable=self.ip_var, width=16).grid(row=0, column=1, padx=(4, 12))

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value=str(VRCHAT_PORT))
        ttk.Entry(conn_frame, textvariable=self.port_var, width=7).grid(row=0, column=3, padx=(4, 12))

        ttk.Button(conn_frame, text="Apply", command=self._apply_connection).grid(row=0, column=4)

        # ── Action buttons ──────────────────────────────────────────────
        btn_frame = ttk.LabelFrame(self, text="Actions", padding=8)
        btn_frame.grid(row=1, column=0, padx=10, pady=4, sticky="nsew")

        for i, action in enumerate(ACTIONS):
            row, col = divmod(i, 2)
            btn = ttk.Button(
                btn_frame, text=action, width=16,
                command=lambda a=action: self._send_action(a),
            )
            btn.grid(row=row, column=col, padx=4, pady=3)

        # ── Hold controls ───────────────────────────────────────────────
        hold_frame = ttk.LabelFrame(self, text="Hold Action", padding=8)
        hold_frame.grid(row=2, column=0, padx=10, pady=4, sticky="ew")

        self.hold_var = tk.StringVar(value=list(ACTIONS.keys())[0])
        ttk.Label(hold_frame, text="Action:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            hold_frame, textvariable=self.hold_var,
            values=list(ACTIONS.keys()) + list(TIMED_SEQUENCES.keys()), state="readonly", width=14,
        ).grid(row=0, column=1, padx=(4, 8))

        ttk.Label(hold_frame, text="Interval (s):").grid(row=0, column=2, sticky="w")
        self.interval_var = tk.StringVar(value="0.1")
        ttk.Entry(hold_frame, textvariable=self.interval_var, width=5).grid(row=0, column=3, padx=(4, 8))

        self.hold_btn = ttk.Button(hold_frame, text="Start Hold", command=self._toggle_hold)
        self.hold_btn.grid(row=0, column=4)

        # ── Custom message ──────────────────────────────────────────────
        custom_frame = ttk.LabelFrame(self, text="Custom OSC Message", padding=8)
        custom_frame.grid(row=3, column=0, padx=10, pady=4, sticky="ew")

        ttk.Label(custom_frame, text="Address:").grid(row=0, column=0, sticky="w")
        self.addr_var = tk.StringVar(value="/input/Vertical")
        ttk.Entry(custom_frame, textvariable=self.addr_var, width=22).grid(row=0, column=1, padx=(4, 8))

        ttk.Label(custom_frame, text="Value:").grid(row=0, column=2, sticky="w")
        self.val_var = tk.StringVar(value="1.0")
        ttk.Entry(custom_frame, textvariable=self.val_var, width=7).grid(row=0, column=3, padx=(4, 8))

        ttk.Button(custom_frame, text="Send", command=self._send_custom).grid(row=0, column=4)

        # ── Log ─────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="Log", padding=8)
        log_frame.grid(row=1, column=1, rowspan=3, padx=(0, 10), pady=4, sticky="nsew")

        self.log = scrolledtext.ScrolledText(log_frame, width=36, height=18, state="disabled", font=("Courier", 9))
        self.log.pack()

        ttk.Button(self, text="Clear Log", command=self._clear_log).grid(row=4, column=1, padx=(0, 10), pady=(0, 8), sticky="e")

    # ── Helpers ──────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _apply_connection(self):
        global osc_client
        ip = self.ip_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            self._log("! Invalid port number")
            return
        osc_client = udp_client.SimpleUDPClient(ip, port)
        self._log(f"→ Connected to {ip}:{port}")

    def _send_action(self, action: str):
        messages = ACTIONS[action]
        for address, value in messages:
            osc_client.send_message(address, value)
            self._log(f"[{action}] {address}  {value}")

    def _send_custom(self):
        address = self.addr_var.get().strip()
        raw = self.val_var.get().strip()
        if not address:
            self._log("! Address cannot be empty")
            return
        try:
            value = float(raw)
        except ValueError:
            value = raw  # send as string if not numeric
        osc_client.send_message(address, value)
        self._log(f"[Custom] {address}  {value}")

    def _toggle_hold(self):
        global _holding, _hold_thread
        if not _holding:
            _holding = True
            self.hold_btn.config(text="Stop Hold")
            _hold_thread = threading.Thread(target=self._hold_loop, daemon=True)
            _hold_thread.start()
        else:
            _holding = False
            self._send_action("Reset")  # Ensure we stop cleanly
            self.hold_btn.config(text="Start Hold")

    def _hold_loop(self):
        global _holding
        action = self.hold_var.get()
        if action in TIMED_SEQUENCES:
            steps = TIMED_SEQUENCES[action]
            step_idx = 0
            while _holding:
                duration, messages = steps[step_idx % len(steps)]
                for address, value in messages:
                    osc_client.send_message(address, value)
                    self.after(0, self._log, f"[Hold:{action}] {address}  {value}")
                time.sleep(max(0.01, duration))
                step_idx += 1
        else:
            while _holding:
                action = self.hold_var.get()
                try:
                    interval = float(self.interval_var.get())
                except ValueError:
                    interval = 0.1
                for address, value in ACTIONS[action]:
                    osc_client.send_message(address, value)
                    self.after(0, self._log, f"[Hold:{action}] {address}  {value}")
                time.sleep(max(0.01, interval))


if __name__ == "__main__":
    app = App()
    app.mainloop()
