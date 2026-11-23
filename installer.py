"""Small Windows GUI for the PrintExp native 3D page add-on."""
from __future__ import annotations

import os
import queue
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from addon_manager_core import (ADDON_DIR, LAUNCHER_NAME, InstallationError,
                                install_or_update, uninstall)


class Installer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PrintExp 3D Add-on Manager — Stage 1")
        self.geometry("750x440")
        self.minsize(660, 420)
        self.resizable(True, True)
        self.configure(background="#18212b")
        self.folder = tk.StringVar(value="")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self._build()
        self.after(80, self._drain)

    def _build(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#18212b")
        style.configure("TLabel", background="#18212b", foreground="#f5f7fa", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 19))
        style.configure("Secondary.TLabel", foreground="#b5c2cf")
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 9))
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="PrintExp · 3D Add-on", style="Header.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Stage 1: add a visible 3D tab inside PrintExp. No printer-control functions.",
                  style="Secondary.TLabel").pack(anchor="w", pady=(3, 17))
        ttk.Label(frame, text="PrintExp installation folder").pack(anchor="w")
        chooser = ttk.Frame(frame)
        chooser.pack(fill="x", pady=(5, 15))
        ttk.Entry(chooser, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(chooser, text="Browse…", command=self._browse).pack(side="left", padx=(7, 0))
        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(0, 12))
        self.install_btn = ttk.Button(actions, text="Install", command=lambda: self._operate("install"))
        self.install_btn.pack(side="left", padx=(0, 8))
        self.update_btn = ttk.Button(actions, text="Update from main", command=lambda: self._operate("update"))
        self.update_btn.pack(side="left", padx=(0, 8))
        self.uninstall_btn = ttk.Button(actions, text="Uninstall", command=lambda: self._operate("uninstall"))
        self.uninstall_btn.pack(side="left", padx=(0, 8))
        self.launch_btn = ttk.Button(actions, text="Launch PrintExp + 3D", command=self._launch)
        self.launch_btn.pack(side="left")
        ttk.Label(frame, text="The original PrintExp executable and DLLs are never modified. "
                  "The 3D tab is loaded only by the new launcher.",
                  style="Secondary.TLabel", wraplength=690).pack(anchor="w", pady=(0, 10))
        self.log = tk.Text(frame, background="#101820", foreground="#d3e7f3", height=10,
                           borderwidth=0, font=("Consolas", 9), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self._log("Dependencies checked by Start-Installer.cmd. Select PrintExp_X64.exe folder, then Install.")

    def _browse(self) -> None:
        selection = filedialog.askdirectory(title="Select PrintExp installation directory")
        if selection:
            self.folder.set(selection)

    def _log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _operate(self, action: str) -> None:
        if self.busy:
            return
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showerror("Choose PrintExp", "Select the folder containing PrintExp_X64.exe.")
            return
        if action in ("install", "update") and not messagebox.askyesno(
            "Experimental native page",
            "Stage 1 temporarily loads a new UI DLL into PrintExp using a targeted Windows "
            "message hook. No printhead, UV or motor commands will be sent.\n\n"
            "Test only while the printer is idle (preferably disconnected). Continue?"):
            return
        if action == "uninstall" and not messagebox.askyesno(
            "Uninstall add-on", "Remove UV3DAddOn and its dedicated launcher? "
            "The original PrintExp installation will remain untouched."):
            return
        self.busy = True
        for button in (self.install_btn, self.update_btn, self.uninstall_btn, self.launch_btn):
            button.configure(state="disabled")
        def task() -> None:
            try:
                if action in ("install", "update"):
                    if action == "update" and not (Path(folder) / ADDON_DIR).is_dir():
                        raise InstallationError("Not installed yet. Use Install first.")
                    install_or_update(Path(folder), log=lambda line: self.events.put(("log", line)))
                else:
                    uninstall(Path(folder), log=lambda line: self.events.put(("log", line)))
                self.events.put(("done", action))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=task, daemon=True).start()

    def _drain(self) -> None:
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(data)
            else:
                self.busy = False
                for button in (self.install_btn, self.update_btn, self.uninstall_btn, self.launch_btn):
                    button.configure(state="normal")
                if kind == "error":
                    self._log("ERROR: " + data)
                    messagebox.showerror("Operation failed", data)
                else:
                    self._log("SUCCESS: " + ("Installed / updated" if data in ("install", "update") else "Uninstalled"))
        self.after(80, self._drain)

    def _launch(self) -> None:
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showerror("Select a folder", "Select your PrintExp installation first.")
            return
        script = Path(folder) / LAUNCHER_NAME
        if not script.is_file():
            messagebox.showerror("Not installed", "Click Install / Update first.")
            return
        if not messagebox.askyesno("Start test", "Start PrintExp with the Stage 1 tab? "
                                   "Only do this while no print job is running."):
            return
        try:
            if os.name != "nt":
                raise InstallationError("Stage 1 only runs on Windows x64.")
            subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=folder)
        except Exception as exc:
            messagebox.showerror("Launch error", str(exc))


if __name__ == "__main__":
    Installer().mainloop()
