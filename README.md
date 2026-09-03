# antidote

**A backup-based viewer for `decayfmt` files. Every open uses a disposable copy, the master never decays.**

[decayfmt](https://github.com/aravpanwar/decayfmt) corrupts a file a little on every open. Its own README says a backup defeats it entirely: copy the file first, open the copy, keep the original forever. `antidote` automates that. It does not bypass decayfmt's code. It keeps a pristine master and hands `decayfmt open` a throwaway copy instead.

Two tools, same idea:

- `antidote.py`, command line
- `antidote_gui.py`, dark-themed gallery app, folders plus persistent open counts

## How it works

1. A master file (`photo.idcy3`, `note.tdcy7`, etc) is stored and marked **read-only**. decayfmt refuses to open a read-only file, so the master can't decay even by accident.
2. On every "open", the master is copied to a new file (same name, so `x` still reads correctly from the extension). `decayfmt open` runs on the copy.
3. The copy decays. The master doesn't. Repeat forever.

```
master (read-only, never opened)
   |
   |-- copy 1 -> decayfmt open -> decayed
   |-- copy 2 -> decayfmt open -> decayed
   `-- copy N -> decayfmt open -> decayed
```

## GUI (`antidote_gui.py`)

Folders are created next to the script automatically, on any OS:

```
put files here/   drop your .idcyX / .tdcyX masters here, auto read-only on scan
gallery/           every open lands a new copy here, old copies are never touched again
```

Run:

```
python antidote_gui.py
```

- Left panel: masters, with open count per file.
- Right panel: history of every copy made for the selected master, newest first.
- `open fresh copy`: copies master into `gallery/`, runs `decayfmt open` on the copy in a background thread, updates the count.
- `rescan folder`: picks up files dropped into `put files here/` while the app is running.

**Memory.** Open counts and full copy history are stored in `gallery/.antidote_state.json` and reloaded on every launch. Survives restarts.

## CLI (`antidote.py`)

```
antidote.py add    <file> [--name NAME]     store a pristine, read-only master
antidote.py list                            show what's in the vault
antidote.py open   <name> [--keep DIR]      view once via a disposable copy
antidote.py export <name> <dest>            copy the master out, no viewing
antidote.py forget <name>                   remove a master from the vault
```

Vault location: `~/.antidote_vault` (override with `--vault-dir` or `ANTIDOTE_VAULT`).

```
antidote.py add photo.idcy3
antidote.py open photo.idcy3
antidote.py open photo.idcy3
antidote.py open photo.idcy3
```

Three opens, one master, zero decay on the master.

## Requirements

- Python 3
- `decayfmt` binary on PATH
- GUI only: tkinter. Ships with Python on Windows and macOS. On Linux, install separately if missing:
  - Ubuntu/Debian/Mint: `sudo apt install python3-tk`
  - Fedora/RHEL/Rocky: `sudo dnf install python3-tkinter`
  - Arch/Manjaro: `sudo pacman -S tk`
  - openSUSE: `sudo zypper install python3-tk`
  - macOS: `brew install python-tk`
  - Windows: reinstall Python with "tcl/tk and IDLE" checked

No external Python packages. Standard library only.

## Getting decayfmt on Windows, step by step

Skip building from source unless you have a reason to. Grab the prebuilt binary instead.

1. Open https://github.com/aravpanwar/decayfmt/releases
2. Download the Windows `.exe` from the latest release.
3. Open File Explorer, go to `C:\Users\<you>\.cargo\bin\` (create the folder if it doesn't exist).
4. Drop the downloaded `.exe` in there, rename it to `decayfmt.exe` if it isn't already.
5. Close every open PowerShell or terminal window.
6. Open a new one, run:
   ```
   decayfmt --version
   ```
   If it prints a version, done. If not, that folder isn't on PATH. See below.

**Check or add PATH:**

1. Press `Win+R`, type `sysdm.cpl`, Enter.
2. Advanced tab, then Environment Variables.
3. Top list ("User variables"), find `Path`, click Edit.
4. New, paste `C:\Users\<you>\.cargo\bin`.
5. OK on every window.
6. Close all terminals, open a new one, retry `decayfmt --version`.

PATH changes only apply to new terminal windows. A terminal that was already open before you edited PATH will never see the change. Close it, don't just retype the command in it.

### Building from source instead (`cargo install decayfmt`)

Needs Rust and a working linker. Common failure on Windows:

```
error: linker `link.exe` not found
note: the msvc targets depend on the msvc linker but `link.exe` was not found
```

The default MSVC toolchain has no C++ build tools behind it. Two fixes:

- Install Build Tools (heavier, most reliable): https://visualstudio.microsoft.com/visual-cpp-build-tools/. Run the installer, check "Desktop development with C++", install, open a new terminal, then `cargo install decayfmt`.
- Switch to the GNU toolchain (lighter, no Visual Studio):
  ```
  rustup toolchain install stable-gnu
  rustup default stable-gnu
  ```
  Verify with `rustup show`. It should list `stable-x86_64-pc-windows-gnu (default)`. Then:
  ```
  cargo install decayfmt
  ```

If `cargo` itself isn't recognized right after installing Rust (`rustup-init.exe`), that's the same PATH-not-refreshed issue as above. Close all terminals, open a new one, retry `cargo --version`.

## What this is, and is not

This is not a decayfmt exploit or a way to break its guarantees. decayfmt's own author states plainly that a backup defeats the corruption mechanic, and that this is expected. `antidote` is that backup, automated and organized: read-only masters, disposable copies, a history you can browse.

It is still true that:

- decayfmt corruption is permanent and unrecoverable for the copy that gets opened.
- The master is only safe as long as `antidote` (or you) never runs `decayfmt open` on it directly.
- If you delete or manually edit the master outside `antidote`, there's no recovery. Same as decayfmt itself.

## Limitations

- Vault and gallery integrity depend on file permissions (`os.chmod`). A user with enough privilege can still remove read-only and open the master directly. This is a safeguard against accidents, not a security boundary.
- No encryption, no cloud sync, no dedup. Masters and copies are plain files on disk.
- GUI needs a display. Headless Linux (SSH without X forwarding) will print an error instead of opening a window. Use the CLI there instead.

## License

MIT.
