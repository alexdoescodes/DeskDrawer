"""The hourly sensor: which drawer origins does a live process hold open?

Only the user's own processes are readable, which is exactly the set that
matters. Anything unreadable is skipped rather than raising.
"""

import os
from pathlib import Path

from .store import Item

# fd symlinks that do not name a filesystem path
_NON_PATH_PREFIXES = ("pipe:", "socket:", "anon_inode:", "[")


def _is_path(target: str) -> bool:
    return target.startswith("/") and not target.startswith(_NON_PATH_PREFIXES)


def scan_open_paths(proc_root: Path = Path("/proc")) -> set[str]:
    proc_root = Path(proc_root)
    found: set[str] = set()
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return found

    for entry in entries:
        if not entry.name.isdigit():
            continue

        try:
            target = os.readlink(entry / "cwd")
            if _is_path(target):
                found.add(target)
        except OSError:
            pass

        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if _is_path(target):
                found.add(target)
    return found


def active_names(items: dict[str, Item], open_paths: set[str]) -> set[str]:
    active: set[str] = set()
    for name, item in items.items():
        origin = item.origin
        if item.is_dir:
            prefix = origin.rstrip("/") + "/"
            if any(p == origin or p.startswith(prefix) for p in open_paths):
                active.add(name)
        elif origin in open_paths:
            active.add(name)
    return active
