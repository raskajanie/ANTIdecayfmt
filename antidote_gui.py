#!/usr/bin/env python3
"""
antidote_gui.py — a dark-themed gallery wrapper around `decayfmt`.

Folder layout (created next to this script on first run):

    put files here/   <- drop your .idcyX / .tdcyX masters here.
                          Each file found is made read-only, so it can
                          never be corrupted directly, even by accident.
    gallery/           <- every time you "open" a file, a brand-new copy
                          is made here and THAT copy is handed to
                          `decayfmt open`. Older copies in this folder
                          are never touched again.

Memory: how many times each master has been opened, and the list/history
of every copy ever made, is stored in
    gallery/.antidote_state.json
and reloaded every time you start the app, so counts and history survive
restarts.

Requires: Python 3 with tkinter (stdlib), and the `decayfmt` binary on
PATH (cargo install decayfmt).

Cross-platform notes:
  - Folder/file paths use pathlib throughout, so the same code creates
    "put files here" / "gallery" correctly on Windows, macOS, and any
    Linux distro without changes.
  - Read-only protection uses os.chmod, which works on all three; on
    Windows it toggles the file's read-only attribute, on POSIX systems
    it clears the write bits.
  - Finding the decayfmt binary uses shutil.which(), which on Windows
    automatically checks PATHEXT (so "decayfmt" finds "decayfmt.exe")
    and on POSIX checks the executable bit.
  - tkinter ships with the official Python installer on Windows and
    macOS. Some Linux distros split it into a separate package — if
    it's missing, this script prints the right install command for
    your distro instead of crashing with a bare import error.
"""
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path


def _tk_install_hint() -> str:
    system = platform.system()
    if system == "Linux":
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                osrel = f.read().lower()
        except OSError:
            osrel = ""
        if any(k in osrel for k in ("ubuntu", "debian", "mint", "pop")):
            return "sudo apt install python3-tk"
        if any(k in osrel for k in ("fedora", "rhel", "centos", "rocky", "alma")):
            return "sudo dnf install python3-tkinter"
        if any(k in osrel for k in ("arch", "manjaro", "endeavour")):
            return "sudo pacman -S tk"
        if any(k in osrel for k in ("opensuse", "suse")):
            return "sudo zypper install python3-tk"
        return "install the 'python3-tk' (or 'tk') package with your distro's package manager"
    if system == "Darwin":
        return "brew install python-tk   (or reinstall Python from python.org, which bundles Tk)"
    if system == "Windows":
        return "reinstall Python from python.org and make sure 'tcl/tk and IDLE' is checked in the installer"
    return "install your platform's Tcl/Tk (tkinter) package"


try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    import tkinter.font as tkfont
except ImportError:
    print(
        "error: tkinter is not available in this Python installation.\n"
        f"On {platform.system()}, try:\n    {_tk_install_hint()}",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------- paths ---

BASE_DIR = Path(sys.argv[0]).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "put files here"
GALLERY_DIR = BASE_DIR / "gallery"
STATE_FILE = GALLERY_DIR / ".antidote_state.json"

DECAY_EXTS = (".idcy", ".tdcy")

# --------------------------------------------------------------- theme ----

BG = "#111013"
PANEL = "#19181c"
PANEL_ALT = "#211f24"
FG = "#e8e6e3"
FG_MUTED = "#8a8790"
ACCENT = "#e0a458"
ACCENT_DIM = "#8a6a3f"
DANGER = "#c96a5a"

# Font families to try, in order, per role. Falls back to Tk's own
# guaranteed-present named fonts (TkDefaultFont / TkFixedFont) so the UI
# never errors out on a distro/OS that lacks all of the preferred fonts.
UI_FONT_CANDIDATES = [
    "Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Cantarell",
    "Noto Sans", "DejaVu Sans",
]
MONO_FONT_CANDIDATES = [
    "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono",
    "Liberation Mono", "Courier New",
]


def pick_font(root: tk.Tk, candidates, size: int, weight: str = "normal", fallback: str = "TkDefaultFont"):
    """Return a font spec usable by ttk styles, preferring an installed
    candidate family and otherwise falling back to a Tk-guaranteed named
    font so this works identically on Windows, macOS, and any Linux
    desktop regardless of which fonts happen to be installed."""
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()
    for name in candidates:
        if name in available:
            return (name, size, weight) if weight != "normal" else (name, size)
    return (fallback, size, weight) if weight != "normal" else (fallback, size)


def is_decay_file(p: Path) -> bool:
    suf = p.suffix
    for tag in DECAY_EXTS:
        if suf.startswith(tag) and suf[len(tag):].isdigit() and suf[len(tag):] != "":
            return True
    return False


def make_read_only(p: Path) -> None:
    mode = os.stat(p).st_mode
    os.chmod(p, mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def make_writable(p: Path) -> None:
    mode = os.stat(p).st_mode
    os.chmod(p, mode | stat.S_IWUSR)


# --------------------------------------------------------------- state ----

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


# ---------------------------------------------------------------- app -----

class AntidoteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state = load_state()
        self.busy = False

        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        GALLERY_DIR.mkdir(parents=True, exist_ok=True)

        self._setup_style()
        self._build_ui()
        self.rescan(initial=True)

    # -- ui construction ---------------------------------------------

    def _setup_style(self):
        self.root.title("decayfmt — antidote gallery")
        self.root.configure(bg=BG)
        self.root.geometry("880x560")
        self.root.minsize(700, 440)

        style = ttk.Style(self.root)
        # "clam" renders consistently (and lets bg/fg colors apply) on
        # Windows, macOS, and Linux, unlike the platform-native themes
        # which often ignore custom colors on some of those OSes.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        ui = lambda size, weight="normal": pick_font(self.root, UI_FONT_CANDIDATES, size, weight)
        mono = lambda size, weight="normal": pick_font(
            self.root, MONO_FONT_CANDIDATES, size, weight, fallback="TkFixedFont"
        )
        self.mono_font = mono(10)

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=ui(10))
        style.configure(
            "Header.TLabel",
            background=BG,
            foreground=ACCENT,
            font=ui(15, "bold"),
        )
        style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=ui(9))
        style.configure(
            "PanelMuted.TLabel",
            background=PANEL,
            foreground=FG_MUTED,
            font=ui(9),
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#1a1408",
            font=ui(10, "bold"),
            padding=8,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_DIM)])
        style.configure(
            "Flat.TButton",
            background=PANEL_ALT,
            foreground=FG,
            font=ui(9),
            padding=6,
        )
        style.map("Flat.TButton", background=[("active", "#2a2830")])

    def _build_ui(self):
        header = ttk.Frame(self.root, style="TFrame")
        header.pack(fill="x", padx=18, pady=(16, 8))
        ttk.Label(header, text="antidote gallery", style="Header.TLabel").pack(side="left")
        ttk.Label(
            header,
            text=f"masters: {SOURCE_DIR.name}   copies: {GALLERY_DIR.name}",
            style="Muted.TLabel",
        ).pack(side="right")

        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True, padx=18, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # left: masters list
        left = tk.Frame(body, bg=PANEL, highlightthickness=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(left, text="MASTERS  ·  never opened, never corrupted", style="PanelMuted.TLabel").pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        self.master_list = tk.Listbox(
            left,
            bg=PANEL,
            fg=FG,
            selectbackground=ACCENT,
            selectforeground="#1a1408",
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
            font=self.mono_font,
        )
        self.master_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.master_list.bind("<<ListboxSelect>>", lambda e: self.refresh_history())
        self.master_list.bind("<Double-Button-1>", lambda e: self.open_selected())

        # right: gallery history for selected master
        right = tk.Frame(body, bg=PANEL, highlightthickness=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(right, text="GALLERY  ·  disposable copies, most recent first", style="PanelMuted.TLabel").pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        self.history_list = tk.Listbox(
            right,
            bg=PANEL,
            fg=FG_MUTED,
            selectbackground=PANEL_ALT,
            selectforeground=FG,
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
            font=self.mono_font,
        )
        self.history_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # footer
        footer = ttk.Frame(self.root, style="TFrame")
        footer.pack(fill="x", padx=18, pady=(6, 16))

        self.status_var = tk.StringVar(value="ready.")
        ttk.Label(footer, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

        ttk.Button(footer, text="rescan folder", style="Flat.TButton", command=self.rescan).pack(
            side="right", padx=(8, 0)
        )
        self.open_btn = ttk.Button(
            footer, text="open fresh copy", style="Accent.TButton", command=self.open_selected
        )
        self.open_btn.pack(side="right")

    # -- data / actions -------------------------------------------------

    def rescan(self, initial: bool = False):
        found = sorted(
            [p for p in SOURCE_DIR.iterdir() if p.is_file()], key=lambda p: p.name.lower()
        )
        new_count = 0
        for p in found:
            key = p.name
            if key not in self.state:
                self.state[key] = {"opens": 0, "copies": [], "added": datetime.now().isoformat(timespec="seconds")}
                new_count += 1
            try:
                make_read_only(p)
            except OSError:
                pass

        save_state(self.state)

        self.master_list.delete(0, tk.END)
        self.known_names = [p.name for p in found]
        for p in found:
            info = self.state.get(p.name, {"opens": 0})
            tag = "" if is_decay_file(p) else "  (not a decayfmt file)"
            self.master_list.insert(tk.END, f"{p.name}   ·  opened {info['opens']}x{tag}")

        if not found:
            self.master_list.insert(tk.END, f"(drop files into '{SOURCE_DIR.name}' and rescan)")

        if not initial:
            self.status_var.set(f"rescanned — {new_count} new file(s) found.")
        self.refresh_history()

    def _selected_name(self):
        sel = self.master_list.curselection()
        if not sel or not getattr(self, "known_names", None):
            return None
        idx = sel[0]
        if idx >= len(self.known_names):
            return None
        return self.known_names[idx]

    def refresh_history(self):
        self.history_list.delete(0, tk.END)
        name = self._selected_name()
        if not name:
            return
        copies = list(reversed(self.state.get(name, {}).get("copies", [])))
        if not copies:
            self.history_list.insert(tk.END, "(no copies opened yet)")
            return
        for c in copies:
            self.history_list.insert(tk.END, f"{c['name']}   ·  {c['time']}")

    def open_selected(self):
        if self.busy:
            return
        name = self._selected_name()
        if not name:
            messagebox.showinfo("antidote", "Select a master file first.")
            return

        master_path = SOURCE_DIR / name
        if not master_path.is_file():
            messagebox.showerror("antidote", f"'{name}' no longer exists in the source folder.")
            self.rescan()
            return

        if shutil.which("decayfmt") is None:
            messagebox.showerror(
                "antidote",
                "The 'decayfmt' binary was not found on PATH.\nInstall it with: cargo install decayfmt",
            )
            return

        self.busy = True
        self.open_btn.state(["disabled"])
        self.status_var.set(f"opening a fresh copy of {name} ...")
        threading.Thread(target=self._open_worker, args=(name, master_path), daemon=True).start()

    def _open_worker(self, name: str, master_path: Path):
        try:
            n = self.state[name]["opens"] + 1
            stem = master_path.stem
            suffix = master_path.suffix
            copy_name = f"{stem}__open{n}{suffix}"
            copy_path = GALLERY_DIR / copy_name

            shutil.copy2(master_path, copy_path)
            make_writable(copy_path)

            proc = subprocess.run(["decayfmt", "open", str(copy_path)], capture_output=True, text=True)

            self.state[name]["opens"] = n
            self.state[name]["copies"].append(
                {"name": copy_name, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            )
            save_state(self.state)

            if proc.returncode != 0:
                err = proc.stderr.strip() or "unknown error"
                self.root.after(0, lambda: messagebox.showerror("decayfmt", err))
                self.root.after(0, lambda: self.status_var.set(f"decayfmt reported an error on {copy_name}."))
            else:
                self.root.after(0, lambda: self.status_var.set(f"opened {copy_name} — master untouched."))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: messagebox.showerror("antidote", str(exc)))
        finally:
            self.root.after(0, self._open_done)

    def _open_done(self):
        self.busy = False
        self.open_btn.state(["!disabled"])
        self.rescan()


def main():
    # Works unchanged on Windows, macOS, and Linux — pathlib resolves the
    # right separators and mkdir(parents=True, exist_ok=True) is a no-op
    # if the folders already exist.
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        hint = (
            "no display found. If this is a Linux server over SSH, either run it on a "
            "machine with a desktop, or reconnect with X forwarding (ssh -X)."
            if platform.system() == "Linux"
            else str(exc)
        )
        print(f"error: could not open a GUI window — {hint}", file=sys.stderr)
        sys.exit(1)
    AntidoteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
