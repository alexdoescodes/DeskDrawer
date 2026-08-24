"""The daemon: two sensors feeding one rule, swept hourly.

A long-running process is required because inotify watches must persist; a
systemd timer firing a one-shot would lose them on every invocation.
"""

import sys
import time
from pathlib import Path

from . import config, expiry, scanner
from .store import Store
from .watcher import InotifyWatcher

TICK_SECONDS = 3600.0


def tick(store: Store, lifetime_seconds: float, now: float, proc_root: Path = Path("/proc")) -> list[str]:
    """Record who is open, then expire the rest. Order matters."""
    items = store.load()
    if items:
        open_paths = scanner.scan_open_paths(proc_root)
        store.touch(scanner.active_names(items, open_paths))
    return expiry.sweep(store, now=now, lifetime_seconds=lifetime_seconds)


def run(config_path: Path | None = None) -> int:
    cfg = config.load(config_path)
    store = Store(cfg.drawer_dir)
    watcher = InotifyWatcher()

    tick(store, cfg.lifetime_seconds, now=time.time())
    watcher.sync(store.load())
    next_tick = time.monotonic() + TICK_SECONDS

    try:
        while True:
            timeout = max(0.0, next_tick - time.monotonic())
            touched = watcher.poll(timeout=timeout)
            if touched:
                store.touch(touched)

            if time.monotonic() >= next_tick:
                cfg = config.load(config_path)
                store = Store(cfg.drawer_dir)
                tick(store, cfg.lifetime_seconds, now=time.time())
                watcher.sync(store.load())
                next_tick = time.monotonic() + TICK_SECONDS
    except KeyboardInterrupt:
        return 0
    finally:
        watcher.close()


if __name__ == "__main__":
    sys.exit(run())
