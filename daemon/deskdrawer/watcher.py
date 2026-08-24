"""inotify watches over drawer origins, via raw syscalls through ctypes.

Exists because an hourly poll cannot see applications that read a file and
release the descriptor immediately (Kate, Okular, GIMP). Directories are
watched one level deep; deeper activity is covered by the /proc scanner.
"""

import ctypes
import ctypes.util
import errno
import os
import select
import struct
from pathlib import Path

from .store import Item

IN_ACCESS = 0x00000001
IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_CLOSE_NOWRITE = 0x00000010
IN_OPEN = 0x00000020

WATCH_MASK = IN_ACCESS | IN_MODIFY | IN_CLOSE_WRITE | IN_CLOSE_NOWRITE | IN_OPEN

_IN_NONBLOCK = 0o4000
_IN_CLOEXEC = 0o2000000
_EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, name_len
_READ_SIZE = 8192


class InotifyWatcher:
    def __init__(self):
        self._libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self._libc.inotify_init1.argtypes = [ctypes.c_int]
        self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]

        self._fd = self._libc.inotify_init1(_IN_NONBLOCK | _IN_CLOEXEC)
        if self._fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")

        self._wd_to_name: dict[int, str] = {}
        self._watched_paths: dict[str, set[str]] = {}  # name -> paths currently watched

    def fileno(self) -> int:
        return self._fd

    def _add_watch(self, path: Path, name: str) -> bool:
        wd = self._libc.inotify_add_watch(self._fd, os.fsencode(str(path)), WATCH_MASK)
        if wd < 0:
            return False
        self._wd_to_name[wd] = name
        return True

    def _paths_for(self, item: Item) -> set[str]:
        """The origin, plus its immediate children when the origin is a directory."""
        origin = Path(item.origin)
        if not origin.exists():
            return set()
        paths = {str(origin)}
        if item.is_dir:
            try:
                paths.update(str(child) for child in origin.iterdir())
            except OSError:
                pass
        return paths

    def sync(self, items: dict[str, Item]) -> None:
        wanted = {name: self._paths_for(item) for name, item in items.items()}

        for name, paths in self._watched_paths.items():
            if wanted.get(name) == paths:
                continue
            for wd, watched_name in list(self._wd_to_name.items()):
                if watched_name == name:
                    self._libc.inotify_rm_watch(self._fd, wd)
                    del self._wd_to_name[wd]

        for name, paths in wanted.items():
            if self._watched_paths.get(name) == paths:
                continue
            for path in paths:
                self._add_watch(Path(path), name)

        self._watched_paths = wanted

    def poll(self, timeout: float) -> set[str]:
        names: set[str] = set()
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return names

        while True:
            try:
                data = os.read(self._fd, _READ_SIZE)
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno == errno.EAGAIN:
                    break
                raise
            if not data:
                break

            offset = 0
            while offset < len(data):
                wd, _mask, _cookie, name_len = _EVENT_HEADER.unpack_from(data, offset)
                offset += _EVENT_HEADER.size + name_len
                name = self._wd_to_name.get(wd)
                if name is not None:
                    names.add(name)

            ready, _, _ = select.select([self._fd], [], [], 0)
            if not ready:
                break
        return names

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
