"""The drawer directory: symlinks in items/ and their metadata in state.json.

Every mutation of the drawer happens here. Removal always targets a path inside
items/; origins are only ever read.
"""

import json
import mimetypes
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

_ICON_BY_TYPE = {
    "application/pdf": "application-pdf",
    "application/zip": "application-x-archive",
    "application/gzip": "application-x-archive",
    "application/x-tar": "application-x-archive",
}
_ICON_BY_PREFIX = {
    "image": "image-x-generic",
    "video": "video-x-generic",
    "audio": "audio-x-generic",
    "text": "text-x-generic",
}


def icon_for(path: Path, is_dir: bool) -> str:
    """A freedesktop icon name the widget can hand straight to Kirigami.Icon."""
    if is_dir:
        return "folder"
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed is None:
        return "unknown"
    if guessed in _ICON_BY_TYPE:
        return _ICON_BY_TYPE[guessed]
    return _ICON_BY_PREFIX.get(guessed.split("/")[0], "unknown")


@dataclass
class Item:
    name: str
    origin: str
    dropped: float
    last_activity: float
    is_dir: bool = False
    exists: bool = True
    icon: str = "unknown"


class Store:
    def __init__(self, drawer_dir: Path, clock: Callable[[], float] = time.time):
        self.drawer_dir = Path(drawer_dir)
        self.items_dir = self.drawer_dir / "items"
        self.state_path = self.drawer_dir / "state.json"
        self.clock = clock

    def link_path(self, name: str) -> Path:
        return self.items_dir / name

    def _ensure_dirs(self) -> None:
        self.items_dir.mkdir(parents=True, exist_ok=True)

    def _links_on_disk(self) -> dict[str, Path]:
        if not self.items_dir.is_dir():
            return {}
        return {p.name: p for p in self.items_dir.iterdir() if p.is_symlink()}

    def load(self) -> dict[str, Item]:
        """Read state.json, reconciled against the links actually present.

        The directory is the source of truth for existence; state.json only
        supplies metadata. A missing or corrupt state file is rebuilt rather
        than being treated as an error.
        """
        links = self._links_on_disk()
        try:
            raw = json.loads(self.state_path.read_text())
            recorded = {k: Item(**v) for k, v in raw.items()}
        except (OSError, ValueError, TypeError):
            recorded = {}

        items: dict[str, Item] = {}
        for name, link in links.items():
            entry = recorded.get(name)
            if entry is None:
                origin = os.readlink(link)
                stamp = link.lstat().st_mtime
                entry = Item(
                    name=name,
                    origin=origin,
                    dropped=stamp,
                    last_activity=stamp,
                    is_dir=Path(origin).is_dir(),
                )
            # Recomputed on every read so a moved origin shows as broken
            # without waiting for the daemon to rewrite state.json.
            origin_path = Path(entry.origin)
            entry.exists = origin_path.exists()
            entry.icon = icon_for(origin_path, entry.is_dir)
            items[name] = entry
        return items

    def save(self, items: dict[str, Item]) -> None:
        self._ensure_dirs()
        payload = {name: asdict(item) for name, item in items.items()}
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.state_path)

    def _unique_name(self, stem_name: str, taken: set[str]) -> str:
        if stem_name not in taken:
            return stem_name
        base = Path(stem_name)
        counter = 2
        while True:
            candidate = f"{base.stem} ({counter}){base.suffix}"
            if candidate not in taken:
                return candidate
            counter += 1

    def add(self, origin: Path) -> Item | None:
        origin = Path(origin).expanduser().resolve()
        items = self.load()
        if any(item.origin == str(origin) for item in items.values()):
            return None

        self._ensure_dirs()
        name = self._unique_name(origin.name, set(items))
        os.symlink(origin, self.link_path(name))

        now = self.clock()
        item = Item(
            name=name,
            origin=str(origin),
            dropped=now,
            last_activity=now,
            is_dir=origin.is_dir(),
            exists=True,
            icon=icon_for(origin, origin.is_dir()),
        )
        items[name] = item
        self.save(items)
        return item

    def remove(self, name: str) -> bool:
        """Unlink one entry. os.unlink on a symlink never follows it."""
        items = self.load()
        if name not in items:
            return False
        link = self.link_path(name)
        try:
            os.unlink(link)
        except FileNotFoundError:
            pass
        del items[name]
        self.save(items)
        return True

    def touch(self, names: Iterable[str]) -> None:
        names = set(names)
        if not names:
            return
        items = self.load()
        now = self.clock()
        changed = False
        for name in names:
            if name in items:
                items[name].last_activity = now
                changed = True
        if changed:
            self.save(items)
