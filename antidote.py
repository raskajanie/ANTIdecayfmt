#!/usr/bin/env python3
"""
antidote.py — a backup-based wrapper around `decayfmt`.

decayfmt's own README says it plainly: it is a social contract, not
security. Anyone with a backup can copy the file before opening it and
keep the original forever. This tool automates exactly that:

  - You "add" a .idcyX / .tdcyX file once. It's copied into a vault and
    marked read-only, so even a stray `decayfmt open` on the vault copy
    itself fails immediately (decayfmt refuses to touch read-only files).
  - Every time you want to "view" it, antidote makes a fresh disposable
    copy (same filename, so decayfmt still reads the right `x` from the
    name) and runs `decayfmt open` on THAT copy. The copy decays. The
    vault master never does.
  - You can view it as many times as you want; every view starts from
    the pristine original.

Requires the `decayfmt` binary to be on PATH (cargo install decayfmt).

Usage:
    antidote.py add   <file> [--name NAME]      # store a pristine master
    antidote.py list                            # show what's in the vault
    antidote.py open  <name> [--keep]           # view once (disposable copy)
    antidote.py export <name> <dest>            # get a fresh untouched copy, no viewing
    antidote.py forget <name>                   # remove a master from the vault

Vault location defaults to ~/.antidote_vault (override with --vault-dir
or the ANTIDOTE_VAULT env var).
"""
import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def default_vault_dir() -> Path:
    env = os.environ.get("ANTIDOTE_VAULT")
    if env:
        return Path(env)
    return Path.home() / ".antidote_vault"


def masters_dir(vault_dir: Path) -> Path:
    return vault_dir / "masters"


def make_read_only(path: Path) -> None:
    # Remove all write bits for owner/group/other.
    mode = os.stat(path).st_mode
    os.chmod(path, mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def cmd_add(args, vault_dir: Path) -> int:
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        print(f"error: {src} is not a file", file=sys.stderr)
        return 1

    ext_ok = any(
        src.suffix.startswith(suf) and src.suffix[len(suf):].isdigit() and src.suffix[len(suf):] != ""
        for suf in (".idcy", ".tdcy")
    )
    if not ext_ok:
        print(
            f"warning: {src.name} doesn't look like a decayfmt file "
            "(expected .idcy<N> or .tdcy<N>). Storing it anyway.",
            file=sys.stderr,
        )

    name = args.name or src.name
    dest_dir = masters_dir(vault_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name

    if dest.exists():
        print(f"error: '{name}' already exists in the vault. Use a different --name.", file=sys.stderr)
        return 1

    shutil.copy2(src, dest)
    make_read_only(dest)
    print(f"stored '{name}' in vault as a read-only master ({dest}).")
    print("The vault copy will never be opened or corrupted by this tool.")
    return 0


def cmd_list(args, vault_dir: Path) -> int:
    d = masters_dir(vault_dir)
    if not d.exists() or not any(d.iterdir()):
        print("vault is empty.")
        return 0
    print(f"vault: {vault_dir}")
    for p in sorted(d.iterdir()):
        size = p.stat().st_size
        print(f"  {p.name}\t{size} bytes")
    return 0


def cmd_open(args, vault_dir: Path) -> int:
    master = masters_dir(vault_dir) / args.name
    if not master.is_file():
        print(f"error: no master named '{args.name}' in vault. Run 'list' to see what's stored.", file=sys.stderr)
        return 1

    if shutil.which("decayfmt") is None:
        print("error: 'decayfmt' binary not found on PATH (cargo install decayfmt).", file=sys.stderr)
        return 1

    if args.keep:
        out_dir = Path(args.keep).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        copy_path = out_dir / master.name
        if copy_path.exists():
            stem = copy_path.stem
            suffix = copy_path.suffix
            copy_path = out_dir / f"{stem}_{int(time.time())}{suffix}"
        shutil.copy2(master, copy_path)
        make_writable(copy_path)
        _run_decayfmt_open(copy_path)
        print(f"disposable copy left at {copy_path} (already corrupted by this open).")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / master.name
        shutil.copy2(master, copy_path)
        make_writable(copy_path)
        rc = _run_decayfmt_open(copy_path)
        # copy_path is deleted with the tempdir; the vault master is untouched
        return rc


def make_writable(path: Path) -> None:
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IWUSR)


def _run_decayfmt_open(path: Path) -> int:
    proc = subprocess.run(["decayfmt", "open", str(path)])
    return proc.returncode


def cmd_export(args, vault_dir: Path) -> int:
    master = masters_dir(vault_dir) / args.name
    if not master.is_file():
        print(f"error: no master named '{args.name}' in vault.", file=sys.stderr)
        return 1
    dest = Path(args.dest).expanduser().resolve()
    if dest.is_dir():
        dest = dest / master.name
    shutil.copy2(master, dest)
    make_writable(dest)
    print(f"exported pristine, unopened copy to {dest}")
    return 0


def cmd_forget(args, vault_dir: Path) -> int:
    master = masters_dir(vault_dir) / args.name
    if not master.is_file():
        print(f"error: no master named '{args.name}' in vault.", file=sys.stderr)
        return 1
    make_writable(master)
    master.unlink()
    print(f"removed '{args.name}' from vault.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup-based antidote wrapper for decayfmt.")
    parser.add_argument("--vault-dir", help="Override vault location (default: ~/.antidote_vault)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Store a pristine, read-only master copy")
    p_add.add_argument("file")
    p_add.add_argument("--name", help="Name to store it under (default: original filename)")

    sub.add_parser("list", help="List masters in the vault")

    p_open = sub.add_parser("open", help="View a master via a disposable copy; master stays untouched")
    p_open.add_argument("name")
    p_open.add_argument("--keep", metavar="DIR", help="Keep the (now-corrupted) disposable copy in DIR instead of discarding it")

    p_export = sub.add_parser("export", help="Copy the pristine master out, without viewing/corrupting it")
    p_export.add_argument("name")
    p_export.add_argument("dest")

    p_forget = sub.add_parser("forget", help="Delete a master from the vault")
    p_forget.add_argument("name")

    args = parser.parse_args()
    vault_dir = Path(args.vault_dir).expanduser().resolve() if args.vault_dir else default_vault_dir()

    handlers = {
        "add": cmd_add,
        "list": cmd_list,
        "open": cmd_open,
        "export": cmd_export,
        "forget": cmd_forget,
    }
    return handlers[args.command](args, vault_dir)


if __name__ == "__main__":
    sys.exit(main())
