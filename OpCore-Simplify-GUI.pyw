#!/usr/bin/env python3
"""
OpCore-Simplify GUI
A Tkinter GUI wrapper for OpCore-Simplify CLI tool.

Usage:
    python OpCore-Simplify-GUI.py      # with console (debugging)
    pythonw OpCore-Simplify-GUI.py      # without console (Windows release)
"""
import sys
import os
import threading
import subprocess
import queue
import ctypes

# Ensure stdout/stderr are available even when running via pythonw
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    from tkinter.font import Font
except ImportError:
    print("Error: Tkinter is not available.")
    sys.exit(1)


class TerminalEmulator:
    """
    A terminal emulator GUI that wraps the OpCore-Simplify CLI tool.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpCore-Simplify - GUI")
        self.root.geometry("1100x750")
        self.root.minsize(800, 500)
        self.root.configure(bg="#1e1e2e")

        # Dark theme colors
        self.bg = "#1e1e2e"
        self.panel_bg = "#181825"
        self.text_bg = "#11111b"
        self.text_fg = "#cdd6f4"
        self.accent = "#cba6f7"
        self.green = "#a6e3a1"
        self.yellow = "#f9e2af"
        self.red = "#f38ba8"
        self.blue = "#89b4fa"
        self.btn_bg = "#45475a"
        self.btn_fg = "#cdd6f4"
        self.entry_bg = "#313244"

        # State
        self.cli_process = None
        self.output_queue = queue.Queue()
        self.running = False
        self.waiting_input = False
        self.last_prompt = None

        # Build UI
        self._build_ui()

        # Start output polling
        self._poll_output()

    def _build_ui(self):
        """Build the GUI layout."""
        # Request dark title bar on Windows
        try:
            if os.name == 'nt':
                self.root.wm_attributes('-transparentcolor', '')
                HWND = ctypes.windll.user32.GetParent(self.root.winfo_id())
                ctypes.windll.user32.SetWindowLongW(HWND, -20, 0x00010000)
        except:
            pass

        # ===== Top bar =====
        top_bar = tk.Frame(self.root, bg=self.panel_bg, height=55)
        top_bar.pack(fill=tk.X)
        top_bar.pack_propagate(False)

        title = tk.Label(top_bar, text=" OpCore-Simplify", font=("Segoe UI", 15, "bold"),
                        bg=self.panel_bg, fg=self.accent)
        title.pack(side=tk.LEFT, padx=(20, 10), pady=8)

        self.status_text = tk.StringVar(value="Ready")
        status_label = tk.Label(top_bar, textvariable=self.status_text,
                               font=("Segoe UI", 9), bg=self.panel_bg, fg=self.green)
        status_label.pack(side=tk.RIGHT, padx=20, pady=8)

        # ===== Main area =====
        main_frame = tk.Frame(self.root, bg=self.bg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Toolbar
        toolbar = tk.Frame(main_frame, bg=self.bg)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        self.launch_btn = tk.Button(toolbar, text="▶  Launch OpCore-Simplify", command=self._launch,
                                    font=("Segoe UI", 10, "bold"),
                                    bg=self.green, fg="#11111b",
                                    relief=tk.FLAT, padx=16, pady=7,
                                    cursor="hand2")
        self.launch_btn.pack(side=tk.LEFT)

        self.kill_btn = tk.Button(toolbar, text="✕  Stop", command=self._stop,
                                  font=("Segoe UI", 9),
                                  bg=self.red, fg="#11111b",
                                  relief=tk.FLAT, padx=12, pady=5,
                                  cursor="hand2", state=tk.DISABLED)
        self.kill_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Log
        log_label = tk.Label(main_frame, text="Output", font=("Segoe UI", 10, "bold"),
                            bg=self.bg, fg=self.accent)
        log_label.pack(anchor=tk.W)

        self.log = scrolledtext.ScrolledText(main_frame,
                                            font=("Consolas", 10),
                                            bg=self.text_bg, fg=self.text_fg,
                                            relief=tk.FLAT,
                                            wrap=tk.WORD,
                                            state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # ANSI color tags
        self.log.tag_config("bold", font=("Consolas", 10, "bold"))
        self.log.tag_config("red", foreground="#f38ba8")
        self.log.tag_config("green", foreground="#a6e3a1")
        self.log.tag_config("yellow", foreground="#f9e2af")
        self.log.tag_config("cyan", foreground="#89b4fa")
        self.log.tag_config("magenta", foreground="#cba6f7")
        self.log.tag_config("prompt", foreground="#cba6f7")

        # Input bar
        input_frame = tk.Frame(main_frame, bg=self.bg, height=32)
        input_frame.pack(fill=tk.X, pady=(8, 0))
        input_frame.pack_propagate(False)

        tk.Label(input_frame, text=">", font=("Consolas", 11, "bold"),
                bg=self.bg, fg=self.accent).pack(side=tk.LEFT, padx=(0, 5))

        self.input_var = tk.StringVar(value="")
        self.input_entry = tk.Entry(input_frame,
                                    textvariable=self.input_var,
                                    font=("Consolas", 10),
                                    bg=self.entry_bg, fg=self.text_fg,
                                    relief=tk.FLAT,
                                    state=tk.DISABLED, disabledbackground=self.entry_bg)
        self.input_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.input_entry.bind("<Return>", self._send_input)

    def _append_log(self, text, tag=None):
        """Thread-safe append to log widget."""
        self.output_queue.put((text, tag))

    def _poll_output(self):
        """Process queued output every 50ms."""
        while not self.output_queue.empty():
            try:
                text, tag = self.output_queue.get_nowait()
                self._insert_text(text, tag)
            except queue.Empty:
                break
        self.root.after(50, self._poll_output)

    def _insert_text(self, text, tag):
        """Insert text into log widget with optional tag."""
        self.log.configure(state=tk.NORMAL)
        if tag:
            self.log.insert(tk.END, text, tag)
        else:
            self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _launch(self):
        """Launch the CLI in a subprocess."""
        if self.running:
            return

        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        cli_path = os.path.join(script_dir, "OpCore-Simplify.py")

        if not os.path.exists(cli_path):
            self._append_log(f"Error: OpCore-Simplify.py not found at\n{cli_path}\n", "red")
            return

        self.log.configure(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self.log.configure(state=tk.DISABLED)

        self.running = True
        self.waiting_input = True
        self.status_text.set("Running")
        self.launch_btn.configure(state=tk.DISABLED, text="Running...")
        self.kill_btn.configure(state=tk.NORMAL)
        self.input_entry.configure(state=tk.NORMAL)
        self.input_entry.focus_set()

        try:
            self.cli_process = subprocess.Popen(
                [sys.executable, cli_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=script_dir
            )

            # Reader thread
            threading.Thread(target=self._read_stdout, daemon=True).start()

        except Exception as e:
            self._append_log(f"Error launching: {e}\n", "red")
            self._reset_state()

    def _read_stdout(self):
        """Read CLI stdout in a background thread."""
        try:
            for line in self.cli_process.stdout:
                self._append_log(line, None)
        except Exception:
            pass

        self._append_log("\nProcess exited.", "green")
        self.root.after(100, self._reset_state)

    def _send_input(self, event):
        """Send user input to the CLI."""
        text = self.input_var.get().strip()
        self.input_var.set("")
        if text and self.cli_process and self.cli_process.poll() is None:
            try:
                self.cli_process.stdin.write(text + "\n")
                self.cli_process.stdin.flush()
                self._append_log(f"> {text}\n", "magenta")
            except BrokenPipeError:
                self._append_log("Process closed.\n", "red")

    def _stop(self):
        """Kill the CLI process."""
        if self.cli_process and self.cli_process.poll() is None:
            try:
                self.cli_process.terminate()
                self.cli_process.wait(timeout=2)
            except Exception:
                try:
                    self.cli_process.kill()
                except:
                    pass
            self._append_log("\nStopped by user.", "red")
        self._reset_state()

    def _reset_state(self):
        """Reset UI state after process ends."""
        self.running = False
        self.status_text.set("Ready")
        self.launch_btn.configure(state=tk.NORMAL, text="▶  Launch OpCore-Simplify")
        self.kill_btn.configure(state=tk.DISABLED)
        self.input_entry.configure(state=tk.DISABLED)

    def run(self):
        """Start the GUI event loop."""
        self.root.mainloop()


def main():
    app = TerminalEmulator()
    app.run()


if __name__ == "__main__":
    main()
