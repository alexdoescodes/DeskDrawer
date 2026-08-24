# DeskDrawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a KDE Plasma 6 desktop widget that holds symlinks to dropped files and folders, removing each link 24 hours after its origin was last used, without ever modifying the origin.

**Architecture:** Two components share a directory and exchange no messages. A Python daemon under a systemd user service owns all logic with consequences — activity detection via inotify plus an hourly `/proc` scan, deadline bookkeeping, and the expiry sweep — and writes `state.json`. A thin QML plasmoid reads that file for display and shells out to a helper CLI for the only two mutations it can cause: add a link, remove a link.

**Tech Stack:** Python 3.14 (stdlib only — `ctypes`, `configparser`, `unittest`), QML / Qt Quick 6, Plasma 6.7 applet API, `org.kde.draganddrop`, `org.kde.plasma.plasma5support`, systemd user services.

**Spec:** `docs/superpowers/specs/2026-08-24-deskdrawer-design.md`

## Global Constraints

- **Zero third-party dependencies.** No pip packages, no pacman installs. `inotify_simple`, `pyinotify`, `inotify-tools`, and `pytest` are all absent from the target machine and must not be introduced. inotify is called through `ctypes`; tests use stdlib `unittest`.
- **`/` is mounted `noatime`.** Access times never update. Never use `st_atime` as an activity signal.
- **The origin file is never modified, moved, or deleted.** No code path may call `unlink`, `rename`, `rmtree`, or any write operation on an origin path. Removal always targets a path inside `items/`.
- **Only the link is removed on expiry.** `os.unlink` on a symlink removes the link without following it; this is the structural basis of the guarantee above.
- **Python 3.14.6, Plasma 6.7.2, Qt 6.** Applet id is `org.kde.plasma.deskdrawer`; `X-Plasma-API-Minimum-Version` is `6.0`.
- **There is no `org.kde.kio` QML module** on this machine. All filesystem mutation goes through the `deskdrawer` CLI, never through QML directly.
- **Single drawer.** No support for multiple named drawers.
- **Default lifetime is 24 hours**, configurable as `lifetime_hours`. Never hardcode "24" in user-visible strings.
- **Run tests from the `daemon/` directory** with `python3 -m unittest`.

---

### Task 1: Configuration module

Reads `~/.config/deskdrawerrc`, an INI file both components agree on. Everything downstream takes a `Config`, so this comes first.

**Files:**
- Create: `daemon/deskdrawer/__init__.py`
- Create: `daemon/deskdrawer/config.py`
- Create: `daemon/test/__init__.py`
- Create: `daemon/test/test_config.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `Config` dataclass with fields `lifetime_hours: float`, `drawer_dir: Path`, `icon_size: int`; properties `lifetime_seconds: float`, `items_dir: Path`, `state_path: Path`. Module functions `load(path: Path | None = None) -> Config` and `set_value(key: str, value: str, path: Path | None = None) -> None`.

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p daemon/deskdrawer daemon/test
touch daemon/deskdrawer/__init__.py daemon/test/__init__.py
printf '__pycache__/\n*.pyc\n' > .gitignore
```

- [ ] **Step 2: Write the failing test**

Create `daemon/test/test_config.py`:

```python
import tempfile
import unittest
from pathlib import Path

from deskdrawer import config


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "deskdrawerrc"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_yields_defaults(self):
        cfg = config.load(self.path)
        self.assertEqual(cfg.lifetime_hours, 24.0)
        self.assertEqual(cfg.icon_size, 48)
        self.assertEqual(cfg.drawer_dir, Path.home() / ".local/share/deskdrawer")

    def test_values_are_read(self):
        self.path.write_text(
            "[deskdrawer]\nlifetime_hours = 6\ndrawer_dir = /tmp/drawer\nicon_size = 64\n"
        )
        cfg = config.load(self.path)
        self.assertEqual(cfg.lifetime_hours, 6.0)
        self.assertEqual(cfg.drawer_dir, Path("/tmp/drawer"))
        self.assertEqual(cfg.icon_size, 64)

    def test_tilde_in_drawer_dir_is_expanded(self):
        self.path.write_text("[deskdrawer]\ndrawer_dir = ~/mydrawer\n")
        self.assertEqual(config.load(self.path).drawer_dir, Path.home() / "mydrawer")

    def test_garbage_values_fall_back_to_defaults(self):
        self.path.write_text("[deskdrawer]\nlifetime_hours = banana\nicon_size = -3\n")
        cfg = config.load(self.path)
        self.assertEqual(cfg.lifetime_hours, 24.0)
        self.assertEqual(cfg.icon_size, 48)

    def test_unparseable_file_falls_back_to_defaults(self):
        self.path.write_text("this is not ini {{{")
        self.assertEqual(config.load(self.path).lifetime_hours, 24.0)

    def test_derived_paths(self):
        self.path.write_text("[deskdrawer]\ndrawer_dir = /tmp/drawer\nlifetime_hours = 2\n")
        cfg = config.load(self.path)
        self.assertEqual(cfg.items_dir, Path("/tmp/drawer/items"))
        self.assertEqual(cfg.state_path, Path("/tmp/drawer/state.json"))
        self.assertEqual(cfg.lifetime_seconds, 7200.0)


class SetValueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "deskdrawerrc"

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_creates_file_and_roundtrips(self):
        config.set_value("lifetime_hours", "12", self.path)
        self.assertEqual(config.load(self.path).lifetime_hours, 12.0)

    def test_set_preserves_other_keys(self):
        config.set_value("lifetime_hours", "12", self.path)
        config.set_value("icon_size", "64", self.path)
        cfg = config.load(self.path)
        self.assertEqual(cfg.lifetime_hours, 12.0)
        self.assertEqual(cfg.icon_size, 64)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(KeyError):
            config.set_value("nonsense", "1", self.path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_config -v`
Expected: FAIL with `ImportError: cannot import name 'config'`

- [ ] **Step 4: Write the implementation**

Create `daemon/deskdrawer/config.py`:

```python
"""Settings shared by the daemon and the widget, stored in ~/.config/deskdrawerrc."""

import configparser
from dataclasses import dataclass
from pathlib import Path

SECTION = "deskdrawer"
DEFAULT_PATH = Path.home() / ".config" / "deskdrawerrc"

DEFAULT_LIFETIME_HOURS = 24.0
DEFAULT_DRAWER_DIR = Path.home() / ".local/share/deskdrawer"
DEFAULT_ICON_SIZE = 48

KEYS = ("lifetime_hours", "drawer_dir", "icon_size")


@dataclass(frozen=True)
class Config:
    lifetime_hours: float = DEFAULT_LIFETIME_HOURS
    drawer_dir: Path = DEFAULT_DRAWER_DIR
    icon_size: int = DEFAULT_ICON_SIZE

    @property
    def lifetime_seconds(self) -> float:
        return self.lifetime_hours * 3600.0

    @property
    def items_dir(self) -> Path:
        return self.drawer_dir / "items"

    @property
    def state_path(self) -> Path:
        return self.drawer_dir / "state.json"


def _read(path: Path) -> dict:
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except configparser.Error:
        return {}
    if not parser.has_section(SECTION):
        return {}
    return dict(parser[SECTION])


def load(path: Path | None = None) -> Config:
    raw = _read(path or DEFAULT_PATH)

    try:
        lifetime = float(raw.get("lifetime_hours", DEFAULT_LIFETIME_HOURS))
        if lifetime <= 0:
            raise ValueError
    except (TypeError, ValueError):
        lifetime = DEFAULT_LIFETIME_HOURS

    drawer = raw.get("drawer_dir")
    drawer_dir = Path(drawer).expanduser() if drawer else DEFAULT_DRAWER_DIR

    try:
        icon_size = int(raw.get("icon_size", DEFAULT_ICON_SIZE))
        if icon_size <= 0:
            raise ValueError
    except (TypeError, ValueError):
        icon_size = DEFAULT_ICON_SIZE

    return Config(lifetime_hours=lifetime, drawer_dir=drawer_dir, icon_size=icon_size)


def set_value(key: str, value: str, path: Path | None = None) -> None:
    if key not in KEYS:
        raise KeyError(f"unknown setting: {key}")
    target = path or DEFAULT_PATH
    parser = configparser.ConfigParser()
    try:
        parser.read(target)
    except configparser.Error:
        parser = configparser.ConfigParser()
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    parser[SECTION][key] = str(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as handle:
        parser.write(handle)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_config -v`
Expected: PASS, 9 tests

- [ ] **Step 6: Commit**

```bash
git add .gitignore daemon/
git commit -m "feat(daemon): configuration module"
```

---

### Task 2: Store — symlinks and state.json

Owns the drawer directory. Every mutation of `items/` and `state.json` lives here and nowhere else.

**Files:**
- Create: `daemon/deskdrawer/store.py`
- Create: `daemon/test/test_store.py`

**Interfaces:**
- Consumes: `config.Config` from Task 1.
- Produces:
  - `Item` dataclass: `name: str`, `origin: str`, `dropped: float`, `last_activity: float`, `is_dir: bool`, `exists: bool`, `icon: str`. `exists` and `icon` are recomputed on every `load()` rather than trusted from disk.
  - `icon_for(path: Path, is_dir: bool) -> str` returning a freedesktop icon name.
  - `Store(drawer_dir: Path, clock: Callable[[], float] = time.time)` with methods `load() -> dict[str, Item]`, `save(items: dict[str, Item]) -> None`, `add(origin: Path) -> Item | None` (returns `None` when the origin is already in the drawer), `remove(name: str) -> bool`, `touch(names: Iterable[str]) -> None`, `link_path(name: str) -> Path`.
  - `name` is the filename inside `items/` and is the key of the dict returned by `load()`.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_store.py`:

```python
import json
import os
import tempfile
import unittest
from pathlib import Path

from deskdrawer.store import Item, Store, icon_for


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.drawer = self.root / "drawer"
        self.clock = FakeClock()
        self.store = Store(self.drawer, clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name="report.pdf", content="x"):
        path = self.root / name
        path.write_text(content)
        return path

    def test_add_creates_symlink_pointing_at_origin(self):
        origin = self.make_file()
        item = self.store.add(origin)
        link = self.drawer / "items" / item.name
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(origin))

    def test_add_records_metadata(self):
        origin = self.make_file()
        item = self.store.add(origin)
        self.assertEqual(item.name, "report.pdf")
        self.assertEqual(item.origin, str(origin))
        self.assertEqual(item.dropped, 1000.0)
        self.assertEqual(item.last_activity, 1000.0)
        self.assertFalse(item.is_dir)

    def test_add_marks_directories(self):
        origin = self.root / "project"
        origin.mkdir()
        self.assertTrue(self.store.add(origin).is_dir)

    def test_add_resolves_symlinked_origin(self):
        real = self.make_file("real.txt")
        alias = self.root / "alias.txt"
        alias.symlink_to(real)
        self.assertEqual(self.store.add(alias).origin, str(real))

    def test_add_is_persisted(self):
        origin = self.make_file()
        self.store.add(origin)
        reloaded = Store(self.drawer, clock=self.clock).load()
        self.assertIn("report.pdf", reloaded)
        self.assertEqual(reloaded["report.pdf"].origin, str(origin))

    def test_duplicate_origin_is_a_noop(self):
        origin = self.make_file()
        self.store.add(origin)
        self.assertIsNone(self.store.add(origin))
        self.assertEqual(len(self.store.load()), 1)

    def test_name_collision_is_suffixed(self):
        first = self.make_file("report.pdf")
        (self.root / "sub").mkdir()
        second = self.root / "sub" / "report.pdf"
        second.write_text("y")
        self.store.add(first)
        item = self.store.add(second)
        self.assertEqual(item.name, "report (2).pdf")
        self.assertEqual(len(self.store.load()), 2)

    def test_remove_deletes_link_and_entry(self):
        origin = self.make_file()
        item = self.store.add(origin)
        self.assertTrue(self.store.remove(item.name))
        self.assertFalse((self.drawer / "items" / item.name).is_symlink())
        self.assertEqual(self.store.load(), {})

    def test_remove_never_touches_the_origin(self):
        origin = self.make_file(content="precious")
        item = self.store.add(origin)
        self.store.remove(item.name)
        self.assertTrue(origin.exists())
        self.assertEqual(origin.read_text(), "precious")

    def test_remove_unknown_name_returns_false(self):
        self.assertFalse(self.store.remove("nothing.txt"))

    def test_touch_updates_last_activity_only(self):
        origin = self.make_file()
        item = self.store.add(origin)
        self.clock.now = 5000.0
        self.store.touch([item.name])
        reloaded = self.store.load()[item.name]
        self.assertEqual(reloaded.last_activity, 5000.0)
        self.assertEqual(reloaded.dropped, 1000.0)

    def test_touch_ignores_unknown_names(self):
        self.store.touch(["ghost.txt"])
        self.assertEqual(self.store.load(), {})

    def test_state_file_is_written_atomically(self):
        self.store.add(self.make_file())
        leftovers = list((self.drawer).glob("*.tmp*"))
        self.assertEqual(leftovers, [])

    def test_missing_state_is_rebuilt_from_directory(self):
        origin = self.make_file()
        item = self.store.add(origin)
        (self.drawer / "state.json").unlink()
        rebuilt = self.store.load()
        self.assertIn(item.name, rebuilt)
        self.assertEqual(rebuilt[item.name].origin, str(origin))

    def test_corrupt_state_is_rebuilt_from_directory(self):
        origin = self.make_file()
        item = self.store.add(origin)
        (self.drawer / "state.json").write_text("{not json")
        rebuilt = self.store.load()
        self.assertIn(item.name, rebuilt)
        self.assertEqual(rebuilt[item.name].origin, str(origin))

    def test_state_entries_without_a_link_are_dropped(self):
        origin = self.make_file()
        item = self.store.add(origin)
        (self.drawer / "items" / item.name).unlink()
        self.assertEqual(self.store.load(), {})

    def test_dangling_link_is_kept(self):
        origin = self.make_file("doomed.txt")
        item = self.store.add(origin)
        origin.unlink()
        self.assertIn(item.name, self.store.load())

    def test_load_on_empty_drawer(self):
        self.assertEqual(self.store.load(), {})

    def test_existing_origin_is_marked_present(self):
        item = self.store.add(self.make_file())
        self.assertTrue(self.store.load()[item.name].exists)

    def test_missing_origin_is_marked_broken(self):
        origin = self.make_file("doomed.txt")
        item = self.store.add(origin)
        origin.unlink()
        self.assertFalse(self.store.load()[item.name].exists)


class IconTest(unittest.TestCase):
    def test_directory(self):
        self.assertEqual(icon_for(Path("/tmp/project"), is_dir=True), "folder")

    def test_pdf(self):
        self.assertEqual(icon_for(Path("/tmp/a.pdf"), is_dir=False), "application-pdf")

    def test_image(self):
        self.assertEqual(icon_for(Path("/tmp/a.jpg"), is_dir=False), "image-x-generic")

    def test_video(self):
        self.assertEqual(icon_for(Path("/tmp/a.mp4"), is_dir=False), "video-x-generic")

    def test_text(self):
        self.assertEqual(icon_for(Path("/tmp/a.txt"), is_dir=False), "text-x-generic")

    def test_archive(self):
        self.assertEqual(icon_for(Path("/tmp/a.zip"), is_dir=False), "application-x-archive")

    def test_unknown_extension(self):
        self.assertEqual(icon_for(Path("/tmp/a.qqq"), is_dir=False), "unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_store -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deskdrawer.store'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/store.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_store -v`
Expected: PASS, 27 tests

- [ ] **Step 5: Commit**

```bash
git add daemon/deskdrawer/store.py daemon/test/test_store.py
git commit -m "feat(daemon): drawer store with atomic state and self-healing load"
```

---

### Task 3: Expiry sweep

The component with consequences. Decides which links are past their deadline and removes them.

**Files:**
- Create: `daemon/deskdrawer/expiry.py`
- Create: `daemon/test/test_expiry.py`

**Interfaces:**
- Consumes: `Item`, `Store` from Task 2.
- Produces: `deadline(item: Item, lifetime_seconds: float) -> float`, `expired_names(items: dict[str, Item], now: float, lifetime_seconds: float) -> list[str]`, `sweep(store: Store, now: float, lifetime_seconds: float) -> list[str]` returning the names removed.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_expiry.py`:

```python
import tempfile
import unittest
from pathlib import Path

from deskdrawer import expiry
from deskdrawer.store import Item, Store

HOUR = 3600.0
DAY = 24 * HOUR


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class DeadlineTest(unittest.TestCase):
    def test_deadline_is_last_activity_plus_lifetime(self):
        item = Item("a", "/tmp/a", dropped=0.0, last_activity=100.0)
        self.assertEqual(expiry.deadline(item, DAY), 100.0 + DAY)

    def test_expired_names_selects_only_past_deadline(self):
        items = {
            "old": Item("old", "/tmp/old", 0.0, last_activity=0.0),
            "fresh": Item("fresh", "/tmp/fresh", 0.0, last_activity=DAY),
        }
        self.assertEqual(expiry.expired_names(items, now=DAY + 1, lifetime_seconds=DAY), ["old"])

    def test_exactly_at_deadline_is_not_expired(self):
        items = {"a": Item("a", "/tmp/a", 0.0, last_activity=0.0)}
        self.assertEqual(expiry.expired_names(items, now=DAY, lifetime_seconds=DAY), [])


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = FakeClock()
        self.store = Store(self.root / "drawer", clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name, content="x"):
        path = self.root / name
        path.write_text(content)
        return path

    def test_sweep_removes_the_link(self):
        item = self.store.add(self.make_file("a.txt"))
        removed = expiry.sweep(self.store, now=1000.0 + DAY + 1, lifetime_seconds=DAY)
        self.assertEqual(removed, [item.name])
        self.assertFalse(self.store.link_path(item.name).is_symlink())

    def test_sweep_never_touches_the_origin(self):
        origin = self.make_file("a.txt", content="precious")
        self.store.add(origin)
        expiry.sweep(self.store, now=1000.0 + DAY + 1, lifetime_seconds=DAY)
        self.assertTrue(origin.exists())
        self.assertEqual(origin.read_text(), "precious")

    def test_sweep_never_touches_a_directory_origin(self):
        origin = self.root / "project"
        origin.mkdir()
        (origin / "inner.txt").write_text("keep me")
        self.store.add(origin)
        expiry.sweep(self.store, now=1000.0 + DAY + 1, lifetime_seconds=DAY)
        self.assertTrue(origin.is_dir())
        self.assertEqual((origin / "inner.txt").read_text(), "keep me")

    def test_sweep_keeps_fresh_items(self):
        self.store.add(self.make_file("a.txt"))
        self.assertEqual(expiry.sweep(self.store, now=1000.0 + HOUR, lifetime_seconds=DAY), [])

    def test_activity_extends_life(self):
        """drop, 23h pass, touch, 23h more pass: still alive."""
        item = self.store.add(self.make_file("a.txt"))
        self.clock.now = 1000.0 + 23 * HOUR
        self.store.touch([item.name])
        self.assertEqual(
            expiry.sweep(self.store, now=1000.0 + 46 * HOUR, lifetime_seconds=DAY), []
        )
        self.assertTrue(self.store.link_path(item.name).is_symlink())

    def test_untouched_item_dies(self):
        """drop, 25h pass untouched: gone."""
        item = self.store.add(self.make_file("a.txt"))
        self.assertEqual(
            expiry.sweep(self.store, now=1000.0 + 25 * HOUR, lifetime_seconds=DAY),
            [item.name],
        )

    def test_dangling_link_expires_without_error(self):
        origin = self.make_file("doomed.txt")
        item = self.store.add(origin)
        origin.unlink()
        self.assertEqual(
            expiry.sweep(self.store, now=1000.0 + DAY + 1, lifetime_seconds=DAY),
            [item.name],
        )

    def test_sweep_is_selective(self):
        old = self.store.add(self.make_file("old.txt"))
        self.clock.now = 1000.0 + 20 * HOUR
        new = self.store.add(self.make_file("new.txt"))
        removed = expiry.sweep(self.store, now=1000.0 + 25 * HOUR, lifetime_seconds=DAY)
        self.assertEqual(removed, [old.name])
        self.assertTrue(self.store.link_path(new.name).is_symlink())

    def test_startup_sweep_applies_missed_deadlines(self):
        """Time passed while the daemon was not running; absolute deadlines still hold."""
        item = self.store.add(self.make_file("a.txt"))
        self.assertEqual(
            expiry.sweep(self.store, now=1000.0 + 400 * HOUR, lifetime_seconds=DAY),
            [item.name],
        )

    def test_shorter_lifetime_is_honoured(self):
        item = self.store.add(self.make_file("a.txt"))
        self.assertEqual(
            expiry.sweep(self.store, now=1000.0 + 3 * HOUR, lifetime_seconds=2 * HOUR),
            [item.name],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_expiry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deskdrawer.expiry'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/expiry.py`:

```python
"""Deadline arithmetic and the sweep that removes expired links.

This module never receives or constructs an origin path in a form it could
delete. It selects names and hands them to Store.remove, which unlinks a path
inside items/.
"""

from .store import Item, Store


def deadline(item: Item, lifetime_seconds: float) -> float:
    return item.last_activity + lifetime_seconds


def expired_names(items: dict[str, Item], now: float, lifetime_seconds: float) -> list[str]:
    return [
        name
        for name, item in sorted(items.items())
        if now > deadline(item, lifetime_seconds)
    ]


def sweep(store: Store, now: float, lifetime_seconds: float) -> list[str]:
    removed = []
    for name in expired_names(store.load(), now, lifetime_seconds):
        if store.remove(name):
            removed.append(name)
    return removed
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_expiry -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add daemon/deskdrawer/expiry.py daemon/test/test_expiry.py
git commit -m "feat(daemon): expiry sweep that removes links and never origins"
```

---

### Task 4: /proc scanner

The hourly sensor: which drawer items does some process currently hold open?

**Files:**
- Create: `daemon/deskdrawer/scanner.py`
- Create: `daemon/test/test_scanner.py`

**Interfaces:**
- Consumes: `Item` from Task 2.
- Produces: `scan_open_paths(proc_root: Path = Path("/proc")) -> set[str]`, `active_names(items: dict[str, Item], open_paths: set[str]) -> set[str]`.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_scanner.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path

from deskdrawer import scanner
from deskdrawer.store import Item


class FakeProc:
    """Builds a /proc-shaped tree so the scanner is tested deterministically."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def process(self, pid: int, fds=(), cwd=None):
        proc = self.root / str(pid)
        (proc / "fd").mkdir(parents=True)
        for index, target in enumerate(fds):
            os.symlink(target, proc / "fd" / str(index))
        if cwd is not None:
            os.symlink(cwd, proc / "cwd")
        return proc


class ScanOpenPathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proc = FakeProc(self.root / "proc")

    def tearDown(self):
        self.tmp.cleanup()

    def test_collects_fd_targets(self):
        self.proc.process(101, fds=["/home/alex/a.txt", "/home/alex/b.txt"])
        found = scanner.scan_open_paths(self.proc.root)
        self.assertIn("/home/alex/a.txt", found)
        self.assertIn("/home/alex/b.txt", found)

    def test_collects_cwd(self):
        self.proc.process(101, cwd="/home/alex/project")
        self.assertIn("/home/alex/project", scanner.scan_open_paths(self.proc.root))

    def test_ignores_non_numeric_entries(self):
        (self.proc.root / "self").mkdir()
        (self.proc.root / "meminfo").write_text("junk")
        self.proc.process(101, fds=["/home/alex/a.txt"])
        self.assertEqual(scanner.scan_open_paths(self.proc.root), {"/home/alex/a.txt"})

    def test_ignores_pipes_and_sockets(self):
        self.proc.process(101, fds=["pipe:[12345]", "socket:[678]", "/home/alex/a.txt"])
        self.assertEqual(scanner.scan_open_paths(self.proc.root), {"/home/alex/a.txt"})

    def test_ignores_anonymous_inodes(self):
        self.proc.process(101, fds=["anon_inode:[eventpoll]", "/dev/null"])
        found = scanner.scan_open_paths(self.proc.root)
        self.assertNotIn("anon_inode:[eventpoll]", found)

    def test_unreadable_process_is_skipped(self):
        proc = self.proc.process(101, fds=["/home/alex/a.txt"])
        self.proc.process(102, fds=["/home/alex/b.txt"])
        os.chmod(proc / "fd", 0o000)
        try:
            self.assertIn("/home/alex/b.txt", scanner.scan_open_paths(self.proc.root))
        finally:
            os.chmod(proc / "fd", 0o755)

    def test_missing_proc_root_yields_empty(self):
        self.assertEqual(scanner.scan_open_paths(self.root / "nope"), set())


class ActiveNamesTest(unittest.TestCase):
    def test_file_matches_exactly(self):
        items = {"a.txt": Item("a.txt", "/home/alex/a.txt", 0.0, 0.0, is_dir=False)}
        self.assertEqual(scanner.active_names(items, {"/home/alex/a.txt"}), {"a.txt"})

    def test_file_does_not_match_by_prefix(self):
        items = {"a.txt": Item("a.txt", "/home/alex/a.txt", 0.0, 0.0, is_dir=False)}
        self.assertEqual(scanner.active_names(items, {"/home/alex/a.txt.bak"}), set())

    def test_directory_matches_contents(self):
        items = {"project": Item("project", "/home/alex/project", 0.0, 0.0, is_dir=True)}
        found = scanner.active_names(items, {"/home/alex/project/deep/file.mp4"})
        self.assertEqual(found, {"project"})

    def test_directory_matches_itself(self):
        items = {"project": Item("project", "/home/alex/project", 0.0, 0.0, is_dir=True)}
        self.assertEqual(scanner.active_names(items, {"/home/alex/project"}), {"project"})

    def test_directory_does_not_match_a_sibling_with_shared_prefix(self):
        items = {"project": Item("project", "/home/alex/project", 0.0, 0.0, is_dir=True)}
        self.assertEqual(scanner.active_names(items, {"/home/alex/project-old/x"}), set())

    def test_nothing_open_yields_nothing(self):
        items = {"a.txt": Item("a.txt", "/home/alex/a.txt", 0.0, 0.0, is_dir=False)}
        self.assertEqual(scanner.active_names(items, set()), set())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_scanner -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deskdrawer.scanner'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/scanner.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_scanner -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add daemon/deskdrawer/scanner.py daemon/test/test_scanner.py
git commit -m "feat(daemon): /proc scanner for currently-open drawer items"
```

---

### Task 5: inotify watcher

The second sensor, and the reason short-lived opens are not invisible. Kate and Okular release the descriptor within milliseconds, so an hourly poll would never see them.

**Files:**
- Create: `daemon/deskdrawer/watcher.py`
- Create: `daemon/test/test_watcher.py`

**Interfaces:**
- Consumes: `Item` from Task 2.
- Produces: `InotifyWatcher()` with `sync(items: dict[str, Item]) -> None`, `poll(timeout: float) -> set[str]` returning drawer *names* that saw activity, `fileno() -> int`, `close() -> None`. Constant `WATCH_MASK`.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_watcher.py`:

```python
import tempfile
import unittest
from pathlib import Path

from deskdrawer.store import Item
from deskdrawer.watcher import InotifyWatcher


def item(name, origin, is_dir=False):
    return Item(name=name, origin=str(origin), dropped=0.0, last_activity=0.0, is_dir=is_dir)


class WatcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.watcher = InotifyWatcher()

    def tearDown(self):
        self.watcher.close()
        self.tmp.cleanup()

    def test_open_of_watched_file_is_reported(self):
        origin = self.root / "a.txt"
        origin.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", origin)})
        origin.read_text()
        self.assertEqual(self.watcher.poll(timeout=1.0), {"a.txt"})

    def test_quiet_watch_reports_nothing(self):
        origin = self.root / "a.txt"
        origin.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", origin)})
        self.assertEqual(self.watcher.poll(timeout=0.1), set())

    def test_write_is_reported(self):
        origin = self.root / "a.txt"
        origin.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", origin)})
        origin.write_text("y")
        self.assertEqual(self.watcher.poll(timeout=1.0), {"a.txt"})

    def test_activity_in_watched_directory_is_reported(self):
        origin = self.root / "project"
        origin.mkdir()
        child = origin / "inner.txt"
        child.write_text("x")
        self.watcher.sync({"project": item("project", origin, is_dir=True)})
        child.read_text()
        self.assertEqual(self.watcher.poll(timeout=1.0), {"project"})

    def test_unwatched_file_is_not_reported(self):
        watched = self.root / "a.txt"
        watched.write_text("x")
        other = self.root / "b.txt"
        other.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", watched)})
        other.read_text()
        self.assertEqual(self.watcher.poll(timeout=0.1), set())

    def test_sync_drops_watches_for_removed_items(self):
        origin = self.root / "a.txt"
        origin.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", origin)})
        self.watcher.sync({})
        origin.read_text()
        self.assertEqual(self.watcher.poll(timeout=0.1), set())

    def test_sync_is_idempotent(self):
        origin = self.root / "a.txt"
        origin.write_text("x")
        items = {"a.txt": item("a.txt", origin)}
        self.watcher.sync(items)
        self.watcher.sync(items)
        origin.read_text()
        self.assertEqual(self.watcher.poll(timeout=1.0), {"a.txt"})

    def test_missing_origin_is_skipped_without_raising(self):
        self.watcher.sync({"ghost.txt": item("ghost.txt", self.root / "ghost.txt")})
        self.assertEqual(self.watcher.poll(timeout=0.1), set())

    def test_multiple_items_are_distinguished(self):
        a = self.root / "a.txt"
        a.write_text("x")
        b = self.root / "b.txt"
        b.write_text("x")
        self.watcher.sync({"a.txt": item("a.txt", a), "b.txt": item("b.txt", b)})
        b.read_text()
        self.assertEqual(self.watcher.poll(timeout=1.0), {"b.txt"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_watcher -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deskdrawer.watcher'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/watcher.py`. `inotify` is called through `ctypes` because no inotify binding is installed and none may be added.

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_watcher -v`
Expected: PASS, 9 tests

If `test_open_of_watched_file_is_reported` fails with an empty set, check `_IN_NONBLOCK`: it is `0o4000` on Linux/x86-64. A wrong value makes `inotify_init1` return `-1` and the constructor raise, so a constructor error points at the same place.

- [ ] **Step 5: Commit**

```bash
git add daemon/deskdrawer/watcher.py daemon/test/test_watcher.py
git commit -m "feat(daemon): ctypes inotify watcher for short-lived opens"
```

---

### Task 6: Command-line interface

The only path by which the widget mutates anything. All shell quoting happens here rather than inside QML strings.

**Files:**
- Create: `daemon/deskdrawer/cli.py`
- Create: `daemon/test/test_cli.py`

**Interfaces:**
- Consumes: `config.Config`, `config.set_value`, `Store`.
- Produces: `path_from_argument(arg: str) -> Path` (accepts a plain path or a `file://` URL), `main(argv: list[str] | None = None, cfg: Config | None = None) -> int`.
- Commands: `add <path>...`, `remove <name>...`, `list`, `config set <key> <value>`.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_cli.py`:

```python
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from deskdrawer import cli
from deskdrawer.config import Config
from deskdrawer.store import Store


class PathFromArgumentTest(unittest.TestCase):
    def test_plain_path(self):
        self.assertEqual(cli.path_from_argument("/home/alex/a.txt"), Path("/home/alex/a.txt"))

    def test_file_url(self):
        self.assertEqual(cli.path_from_argument("file:///home/alex/a.txt"), Path("/home/alex/a.txt"))

    def test_percent_encoded_url(self):
        self.assertEqual(
            cli.path_from_argument("file:///home/alex/my%20report.pdf"),
            Path("/home/alex/my report.pdf"),
        )

    def test_url_with_hash_and_spaces(self):
        self.assertEqual(
            cli.path_from_argument("file:///home/alex/a%23b%20c.txt"),
            Path("/home/alex/a#b c.txt"),
        )


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = Config(lifetime_hours=24.0, drawer_dir=self.root / "drawer", icon_size=48)
        self.store = Store(self.cfg.drawer_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name="a.txt"):
        path = self.root / name
        path.write_text("x")
        return path

    def test_add_creates_a_link(self):
        origin = self.make_file()
        self.assertEqual(cli.main(["add", str(origin)], cfg=self.cfg), 0)
        self.assertIn("a.txt", self.store.load())

    def test_add_accepts_a_file_url(self):
        origin = self.make_file()
        self.assertEqual(cli.main(["add", origin.as_uri()], cfg=self.cfg), 0)
        self.assertIn("a.txt", self.store.load())

    def test_add_handles_a_path_with_spaces_and_quotes(self):
        origin = self.make_file("a file 'with' quotes.txt")
        self.assertEqual(cli.main(["add", str(origin)], cfg=self.cfg), 0)
        self.assertIn("a file 'with' quotes.txt", self.store.load())

    def test_add_missing_path_fails(self):
        self.assertEqual(cli.main(["add", str(self.root / "nope.txt")], cfg=self.cfg), 1)

    def test_add_duplicate_succeeds_without_duplicating(self):
        origin = self.make_file()
        cli.main(["add", str(origin)], cfg=self.cfg)
        self.assertEqual(cli.main(["add", str(origin)], cfg=self.cfg), 0)
        self.assertEqual(len(self.store.load()), 1)

    def test_remove_deletes_the_link_only(self):
        origin = self.make_file()
        cli.main(["add", str(origin)], cfg=self.cfg)
        self.assertEqual(cli.main(["remove", "a.txt"], cfg=self.cfg), 0)
        self.assertEqual(self.store.load(), {})
        self.assertTrue(origin.exists())

    def test_remove_unknown_name_fails(self):
        self.assertEqual(cli.main(["remove", "ghost.txt"], cfg=self.cfg), 1)

    def test_list_prints_names(self):
        cli.main(["add", str(self.make_file())], cfg=self.cfg)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["list"], cfg=self.cfg)
        self.assertIn("a.txt", buffer.getvalue())

    def test_no_command_returns_error(self):
        self.assertEqual(cli.main([], cfg=self.cfg), 2)


class ConfigCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "deskdrawerrc"

    def tearDown(self):
        self.tmp.cleanup()

    def test_config_set_writes_the_value(self):
        code = cli.main(["config", "set", "lifetime_hours", "6", "--config-path", str(self.path)])
        self.assertEqual(code, 0)
        self.assertIn("lifetime_hours = 6", self.path.read_text())

    def test_config_set_rejects_unknown_key(self):
        code = cli.main(["config", "set", "nonsense", "1", "--config-path", str(self.path)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_cli -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deskdrawer.cli'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/cli.py`:

```python
"""`deskdrawer add|remove|list|config set` — the widget's only way to mutate state."""

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config
from .config import Config
from .store import Store


def path_from_argument(arg: str) -> Path:
    if arg.startswith("file://"):
        return Path(unquote(urlparse(arg).path))
    return Path(arg).expanduser()


def _build_parser() -> argparse.ArgumentParser:
    # --config-path must work both before and after the subcommand. It is
    # declared on a shared parent with default=SUPPRESS, not None: a
    # subparser's default overwrites whatever the top-level parser already
    # stored, so a plain None default would silently discard
    # `--config-path X add ...` and fall back to the real drawer.
    config_path_parent = argparse.ArgumentParser(add_help=False)
    config_path_parent.add_argument("--config-path", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(prog="deskdrawer", parents=[config_path_parent])
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", parents=[config_path_parent])
    add.add_argument("paths", nargs="+")

    remove = sub.add_parser("remove", parents=[config_path_parent])
    remove.add_argument("names", nargs="+")

    sub.add_parser("list", parents=[config_path_parent])

    cfg = sub.add_parser("config", parents=[config_path_parent])
    cfg_sub = cfg.add_subparsers(dest="config_command")
    cfg_set = cfg_sub.add_parser("set", parents=[config_path_parent])
    cfg_set.add_argument("key")
    cfg_set.add_argument("value")

    return parser


def main(argv: list[str] | None = None, cfg: Config | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    raw_config_path = getattr(args, "config_path", None)
    config_path = Path(raw_config_path) if raw_config_path else None

    if args.command is None:
        print("usage: deskdrawer {add,remove,list,config} ...", file=sys.stderr)
        return 2

    if args.command == "config":
        if args.config_command != "set":
            print("usage: deskdrawer config set <key> <value>", file=sys.stderr)
            return 2
        try:
            config.set_value(args.key, args.value, config_path)
        except KeyError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    settings = cfg or config.load(config_path)
    store = Store(settings.drawer_dir)

    if args.command == "add":
        failed = False
        for raw in args.paths:
            origin = path_from_argument(raw)
            if not origin.exists():
                print(f"no such path: {origin}", file=sys.stderr)
                failed = True
                continue
            store.add(origin)
        return 1 if failed else 0

    if args.command == "remove":
        failed = False
        for name in args.names:
            if not store.remove(name):
                print(f"not in drawer: {name}", file=sys.stderr)
                failed = True
        return 1 if failed else 0

    if args.command == "list":
        for name in sorted(store.load()):
            print(name)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_cli -v`
Expected: PASS, 17 tests

- [ ] **Step 5: Commit**

```bash
git add daemon/deskdrawer/cli.py daemon/test/test_cli.py
git commit -m "feat(daemon): deskdrawer CLI"
```

---

### Task 7: Daemon loop and systemd unit

Wires the two sensors to the sweep. The tick is extracted as a pure-ish function so the ordering guarantee — activity is recorded *before* expiry runs — is testable without starting a daemon.

**Files:**
- Create: `daemon/deskdrawer/__main__.py`
- Create: `daemon/deskdrawer.service`
- Create: `daemon/test/test_tick.py`

**Interfaces:**
- Consumes: `Config`, `Store`, `expiry.sweep`, `scanner.scan_open_paths`, `scanner.active_names`, `InotifyWatcher`.
- Produces: `tick(store: Store, lifetime_seconds: float, now: float, proc_root: Path = Path("/proc")) -> list[str]` returning removed names; `run(config_path: Path | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `daemon/test/test_tick.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path

from deskdrawer.__main__ import tick
from deskdrawer.store import Store

HOUR = 3600.0
DAY = 24 * HOUR


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeProc:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def holding(self, pid: int, target: Path):
        fd_dir = self.root / str(pid) / "fd"
        fd_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(target, fd_dir / "0")


class TickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = FakeClock()
        self.store = Store(self.root / "drawer", clock=self.clock)
        self.proc = FakeProc(self.root / "proc")

    def tearDown(self):
        self.tmp.cleanup()

    def make_file(self, name="a.txt"):
        path = self.root / name
        path.write_text("x")
        return path

    def test_an_open_file_past_its_deadline_survives(self):
        """The ordering guarantee: activity is recorded before expiry runs."""
        origin = self.make_file()
        item = self.store.add(origin)
        self.proc.holding(101, origin)
        self.clock.now = 1000.0 + 25 * HOUR
        removed = tick(self.store, DAY, now=self.clock.now, proc_root=self.proc.root)
        self.assertEqual(removed, [])
        self.assertTrue(self.store.link_path(item.name).is_symlink())

    def test_an_open_file_gets_its_deadline_pushed_out(self):
        origin = self.make_file()
        item = self.store.add(origin)
        self.proc.holding(101, origin)
        self.clock.now = 1000.0 + 10 * HOUR
        tick(self.store, DAY, now=self.clock.now, proc_root=self.proc.root)
        self.assertEqual(self.store.load()[item.name].last_activity, self.clock.now)

    def test_a_closed_file_past_its_deadline_is_removed(self):
        item = self.store.add(self.make_file())
        self.clock.now = 1000.0 + 25 * HOUR
        removed = tick(self.store, DAY, now=self.clock.now, proc_root=self.proc.root)
        self.assertEqual(removed, [item.name])

    def test_a_closed_fresh_file_is_left_alone(self):
        item = self.store.add(self.make_file())
        self.clock.now = 1000.0 + HOUR
        self.assertEqual(tick(self.store, DAY, now=self.clock.now, proc_root=self.proc.root), [])
        self.assertTrue(self.store.link_path(item.name).is_symlink())

    def test_tick_on_empty_drawer_is_harmless(self):
        self.assertEqual(tick(self.store, DAY, now=2000.0, proc_root=self.proc.root), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd daemon && python3 -m unittest test.test_tick -v`
Expected: FAIL with `ImportError: cannot import name 'tick'`

- [ ] **Step 3: Write the implementation**

Create `daemon/deskdrawer/__main__.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd daemon && python3 -m unittest test.test_tick -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Run the whole daemon suite**

Run: `cd daemon && python3 -m unittest discover -s test -v`
Expected: PASS, 60+ tests, zero failures

- [ ] **Step 6: Write the systemd unit**

Create `daemon/deskdrawer.service`. `%h` expands to the user's home directory.

```ini
[Unit]
Description=DeskDrawer expiry daemon
Documentation=https://github.com/alex/DeskDrawer

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m deskdrawer
WorkingDirectory=%h/.local/share/deskdrawer-daemon
Environment=PYTHONPATH=%h/.local/share/deskdrawer-daemon
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

- [ ] **Step 7: Verify the daemon starts by hand**

```bash
cd daemon && timeout 5 python3 -m deskdrawer; echo "exit: $?"
```
Expected: exit 124 (killed by timeout — meaning it ran and stayed running). Any traceback is a failure.

- [ ] **Step 8: Commit**

```bash
git add daemon/deskdrawer/__main__.py daemon/deskdrawer.service daemon/test/test_tick.py
git commit -m "feat(daemon): hourly tick, event loop and systemd unit"
```

---

### Task 8: Plasmoid package and dashed frame

The visual shell: an opaque grey rounded rectangle with a dashed border, and nothing inside it yet.

**Files:**
- Create: `plasmoid/metadata.json`
- Create: `plasmoid/contents/config/main.xml`
- Create: `plasmoid/contents/config/config.qml`
- Create: `plasmoid/contents/ui/main.qml`
- Create: `plasmoid/contents/ui/DrawerFrame.qml`

**Interfaces:**
- Produces: `DrawerFrame` — an `Item` with properties `radius: real` (default 12), `dashLength: real` (default 6), `gapLength: real` (default 5), `borderWidth: real` (default 2), and a `default property alias content` that reparents children into the padded interior.

- [ ] **Step 1: Write the metadata and config keys**

The config keys are declared now, before anything reads them, so that no later
task has to hardcode a value and remember to undo it.

Create `plasmoid/metadata.json`:

```json
{
  "KPlugin": {
    "Id": "org.kde.plasma.deskdrawer",
    "Name": "DeskDrawer",
    "Description": "A drop zone whose contents disappear after you stop using them",
    "Icon": "folder",
    "Category": "Utilities",
    "License": "MIT",
    "Version": "1.0.0",
    "Authors": [{ "Name": "Alex" }]
  },
  "KPackageStructure": "Plasma/Applet",
  "X-Plasma-API-Minimum-Version": "6.0"
}
```

Create `plasmoid/contents/config/main.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<kcfg xmlns="http://www.kde.org/standards/kcfg/1.0">
  <kcfgfile name=""/>
  <group name="General">
    <entry name="lifetimeHours" type="Int">
      <default>24</default>
    </entry>
    <entry name="iconSize" type="Int">
      <default>48</default>
    </entry>
  </group>
</kcfg>
```

Create `plasmoid/contents/config/config.qml`:

```qml
import QtQuick
import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: "General"
        icon: "configure"
        source: "ConfigGeneral.qml"
    }
}
```

`ConfigGeneral.qml` is written in Task 13; the config dialog is simply empty until then, which does not affect the widget itself.

- [ ] **Step 2: Write the frame**

Create `plasmoid/contents/ui/DrawerFrame.qml`. The dashes are drawn on a `Canvas` rather than with `QtQuick.Shapes` so the code does not depend on `PathRectangle`, which is newer than the Qt floor this must run on.

```qml
import QtQuick
import org.kde.kirigami as Kirigami

Item {
    id: frame

    property real radius: 12
    property real dashLength: 6
    property real gapLength: 5
    property real borderWidth: 2
    property real padding: 12

    property color fillColor: Kirigami.Theme.backgroundColor
    property color strokeColor: Qt.rgba(Kirigami.Theme.textColor.r,
                                        Kirigami.Theme.textColor.g,
                                        Kirigami.Theme.textColor.b, 0.45)

    default property alias content: interior.data

    onFillColorChanged: canvas.requestPaint()
    onStrokeColorChanged: canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();

            const inset = frame.borderWidth / 2;
            const r = frame.radius;
            const w = width - inset;
            const h = height - inset;

            ctx.fillStyle = frame.fillColor;
            ctx.strokeStyle = frame.strokeColor;
            ctx.lineWidth = frame.borderWidth;
            ctx.setLineDash([frame.dashLength, frame.gapLength]);

            ctx.beginPath();
            ctx.moveTo(inset + r, inset);
            ctx.lineTo(w - r, inset);
            ctx.arcTo(w, inset, w, inset + r, r);
            ctx.lineTo(w, h - r);
            ctx.arcTo(w, h, w - r, h, r);
            ctx.lineTo(inset + r, h);
            ctx.arcTo(inset, h, inset, h - r, r);
            ctx.lineTo(inset, inset + r);
            ctx.arcTo(inset, inset, inset + r, inset, r);
            ctx.closePath();

            ctx.fill();
            ctx.stroke();
        }
    }

    Item {
        id: interior
        anchors.fill: parent
        anchors.margins: frame.padding
    }
}
```

If the border renders solid rather than dashed, `setLineDash` is unavailable in this Qt build; replace it by stroking each dash as its own short segment along the path. Verify before assuming — it is present in Qt 6.

- [ ] **Step 3: Write the applet root**

Create `plasmoid/contents/ui/main.qml`:

```qml
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: root

    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: fullRepresentation

    Layout.minimumWidth: 320
    Layout.minimumHeight: 160

    fullRepresentation: DrawerFrame {
        implicitWidth: 720
        implicitHeight: 340

        Text {
            anchors.centerIn: parent
            text: "DeskDrawer"
            color: "white"
        }
    }
}
```

- [ ] **Step 4: Install and look at it**

```bash
kpackagetool6 --type Plasma/Applet --install plasmoid
```
Then add the widget to the desktop (right-click desktop, Add Widgets, search "DeskDrawer") and confirm: opaque grey panel, rounded corners, visibly dashed border, "DeskDrawer" centred.

Reinstall after edits with `kpackagetool6 --type Plasma/Applet --upgrade plasmoid`, then restart the shell with `systemctl --user restart plasma-plasmashell` to pick up changes.

- [ ] **Step 5: Commit**

```bash
git add plasmoid/
git commit -m "feat(plasmoid): package skeleton and dashed drawer frame"
```

---

### Task 9: Countdown formatting

A pure function, extracted so it can be tested without a running shell.

**Files:**
- Create: `plasmoid/contents/code/format.js`
- Create: `plasmoid/contents/tests/tst_format.qml`

**Interfaces:**
- Produces: `remainingLabel(deadlineSeconds: number, nowSeconds: number) -> string` and `isUrgent(deadlineSeconds: number, nowSeconds: number) -> bool` (true under one hour remaining). Both take **seconds**, matching the units in `state.json`.

- [ ] **Step 1: Write the failing test**

Create `plasmoid/contents/tests/tst_format.qml`:

```qml
import QtQuick
import QtTest
import "../code/format.js" as Format

TestCase {
    name: "Format"

    readonly property real hour: 3600
    readonly property real now: 1000

    function test_whole_hours() {
        compare(Format.remainingLabel(now + 18 * hour, now), "18h");
    }

    function test_rounds_down_to_the_hour() {
        compare(Format.remainingLabel(now + 4.9 * hour, now), "4h");
    }

    function test_under_an_hour_shows_minutes() {
        compare(Format.remainingLabel(now + 47 * 60, now), "47m");
    }

    function test_under_a_minute_shows_less_than_a_minute() {
        compare(Format.remainingLabel(now + 30, now), "<1m");
    }

    function test_past_deadline_is_expired() {
        compare(Format.remainingLabel(now - 1, now), "expired");
    }

    function test_exactly_at_deadline_is_expired() {
        compare(Format.remainingLabel(now, now), "expired");
    }

    function test_urgent_under_an_hour() {
        compare(Format.isUrgent(now + 30 * 60, now), true);
    }

    function test_not_urgent_over_an_hour() {
        compare(Format.isUrgent(now + 3 * hour, now), false);
    }

    function test_expired_counts_as_urgent() {
        compare(Format.isUrgent(now - 5, now), true);
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `qmltestrunner -input plasmoid/contents/tests`
Expected: FAIL — `format.js` does not exist

- [ ] **Step 3: Write the implementation**

Create `plasmoid/contents/code/format.js`:

```javascript
.pragma library

function remainingLabel(deadlineSeconds, nowSeconds) {
    const left = deadlineSeconds - nowSeconds;
    if (left <= 0) {
        return "expired";
    }
    if (left < 60) {
        return "<1m";
    }
    const minutes = Math.floor(left / 60);
    if (minutes < 60) {
        return minutes + "m";
    }
    return Math.floor(minutes / 60) + "h";
}

function isUrgent(deadlineSeconds, nowSeconds) {
    return (deadlineSeconds - nowSeconds) < 3600;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `qmltestrunner -input plasmoid/contents/tests`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add plasmoid/contents/code/format.js plasmoid/contents/tests/tst_format.qml
git commit -m "feat(plasmoid): countdown formatting with tests"
```

---

### Task 10: Reading state.json, and the CLI bridge

Two small pieces of plumbing: the widget's read path and its write path.

**Files:**
- Create: `plasmoid/contents/ui/Paths.qml`
- Create: `plasmoid/contents/ui/Backend.qml`
- Create: `plasmoid/contents/ui/DrawerModel.qml`
- Modify: `plasmoid/contents/ui/main.qml`

**Interfaces:**
- Produces:
  - `Paths` (singleton-style `QtObject`): `home: string`, `drawerDir: string`, `statePath: string`, `cli: string`.
  - `Backend`: `run(command: string)` and `quote(value: string) -> string`; convenience `add(url)`, `remove(name)`, `open(path)`, `reveal(path)`, `setConfig(key, value)`.
  - `DrawerModel`: `ListModel`-shaped `model` with roles `name`, `origin`, `dropped`, `lastActivity`, `isDir`, `originExists`, `iconName`; method `reload()`; properties `lifetimeSeconds` and `now`.

- [ ] **Step 1: Write the path helper**

Create `plasmoid/contents/ui/Paths.qml`:

```qml
import QtQuick
import QtCore

QtObject {
    readonly property string home: StandardPaths.writableLocation(StandardPaths.HomeLocation).toString().replace("file://", "")
    property string drawerDir: home + "/.local/share/deskdrawer"
    readonly property string statePath: drawerDir + "/state.json"
    readonly property string cli: home + "/.local/bin/deskdrawer"
}
```

The CLI is addressed by absolute path because `plasmashell` does not reliably inherit `~/.local/bin` on `PATH`.

- [ ] **Step 2: Write the CLI bridge**

Create `plasmoid/contents/ui/Backend.qml`. Every argument is shell-quoted here: the command reaches a shell as one string, so a filename containing a quote or a space would otherwise break it or worse.

```qml
import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: backend

    property string cli: ""
    signal finished(string command, int exitCode)

    function quote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function run(command) {
        executable.connectSource(command);
    }

    function add(url) {
        run(quote(cli) + " add " + quote(url));
    }

    function remove(name) {
        run(quote(cli) + " remove " + quote(name));
    }

    function openPath(path) {
        run("xdg-open " + quote(path));
    }

    function reveal(path) {
        run("dolphin --select " + quote(path));
    }

    function setConfig(key, value) {
        run(quote(cli) + " config set " + quote(key) + " " + quote(value));
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []

        onNewData: function (source, data) {
            disconnectSource(source);
            backend.finished(source, data["exit code"]);
        }
    }
}
```

- [ ] **Step 3: Write the model**

Create `plasmoid/contents/ui/DrawerModel.qml`:

```qml
import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: drawerModel

    property string statePath: ""
    property real lifetimeSeconds: 24 * 3600
    property alias model: items
    property real now: 0

    signal loaded()

    ListModel { id: items }

    // Qt disables XMLHttpRequest GET on local files unless QML_XHR_ALLOW_FILE_READ=1
    // is set in the environment, which cannot be relied on inside plasmashell.
    // The state file is read through the executable engine instead, matching the
    // rest of the design where all filesystem access happens outside QML.
    function reload() {
        if (!statePath) {
            return;
        }
        reader.connectSource("cat -- '" + statePath.replace(/'/g, "'\\''") + "'");
    }

    P5Support.DataSource {
        id: reader
        engine: "executable"
        connectedSources: []

        onNewData: function (source, data) {
            disconnectSource(source);
            drawerModel.now = Date.now() / 1000;
            drawerModel._apply(data["stdout"] || "");
        }
    }

    function _apply(text) {
        let parsed = {};
        try {
            parsed = JSON.parse(text || "{}");
        } catch (error) {
            parsed = {};
        }

        items.clear();
        const names = Object.keys(parsed).sort();
        for (let i = 0; i < names.length; ++i) {
            const entry = parsed[names[i]];
            items.append({
                name: entry.name,
                origin: entry.origin,
                dropped: entry.dropped,
                lastActivity: entry.last_activity,
                isDir: entry.is_dir === true,
                originExists: entry.exists !== false,
                iconName: entry.icon || "unknown"
            });
        }
        loaded();
    }

    Timer {
        interval: 60000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: drawerModel.reload()
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: drawerModel.now = Date.now() / 1000
    }
}
```

The second timer advances `now` between reloads so countdowns tick without re-reading the file.

- [ ] **Step 4: Wire them into main.qml**

Replace `plasmoid/contents/ui/main.qml`:

```qml
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: root

    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: fullRepresentation

    Layout.minimumWidth: 320
    Layout.minimumHeight: 160

    readonly property Paths paths: Paths {}
    readonly property real lifetimeSeconds: Plasmoid.configuration.lifetimeHours * 3600

    Backend {
        id: cliBackend
        cli: root.paths.cli
    }

    DrawerModel {
        id: drawerModel
        statePath: root.paths.statePath
        lifetimeSeconds: root.lifetimeSeconds
    }

    fullRepresentation: DrawerFrame {
        implicitWidth: 720
        implicitHeight: 340

        Text {
            anchors.centerIn: parent
            color: "white"
            text: drawerModel.model.count + " item(s)"
        }
    }
}
```

- [ ] **Step 5: Verify by hand**

```bash
kpackagetool6 --type Plasma/Applet --upgrade plasmoid
systemctl --user restart plasma-plasmashell
~/.local/bin/deskdrawer add ~/Documents 2>/dev/null || python3 -c "print('install the CLI in Task 13 first')"
```
Expected: within 60 seconds the widget shows the item count. If the CLI is not installed yet, create a link by hand to test the read path:
```bash
mkdir -p ~/.local/share/deskdrawer/items
ln -s ~/Documents ~/.local/share/deskdrawer/items/Documents
cd daemon && PYTHONPATH=. python3 -c "
from pathlib import Path
from deskdrawer.store import Store
Store(Path.home()/'.local/share/deskdrawer').save(Store(Path.home()/'.local/share/deskdrawer').load())
"
```
Expected: the widget reads `1 item(s)`.

- [ ] **Step 6: Commit**

```bash
git add plasmoid/contents/ui/
git commit -m "feat(plasmoid): state.json model and CLI bridge"
```

---

### Task 11: The item grid

**Files:**
- Create: `plasmoid/contents/ui/ItemTile.qml`
- Create: `plasmoid/contents/ui/DrawerView.qml`
- Modify: `plasmoid/contents/ui/main.qml`

**Interfaces:**
- Consumes: `DrawerModel`, `Backend`, `format.js`.
- Produces: `ItemTile` with properties `itemName`, `origin`, `lastActivity`, `isDir`, `originExists`, `iconName`, `iconSize`, `lifetimeSeconds`, `now`; signals `activated()`, `revealRequested()`, `removeRequested()`, `draggingChanged(bool)`. `DrawerView` with properties `drawer` (a `DrawerModel`), `backend`, `iconSize`, `lifetimeHours`.

- [ ] **Step 1: Write the tile**

Create `plasmoid/contents/ui/ItemTile.qml`:

```qml
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.extras as PlasmaExtras
import "../code/format.js" as Format

Item {
    id: tile

    property string itemName: ""
    property string origin: ""
    property real lastActivity: 0
    property bool isDir: false
    property bool originExists: true
    property string iconName: "unknown"
    property int iconSize: 48
    property real lifetimeSeconds: 24 * 3600
    property real now: 0

    signal activated()
    signal revealRequested()
    signal removeRequested()
    signal draggingChanged(bool dragging)

    readonly property real deadline: lastActivity + lifetimeSeconds
    readonly property bool broken: !originExists
    readonly property bool isImage: iconName === "image-x-generic" && originExists

    implicitWidth: iconSize * 2
    implicitHeight: iconSize + Kirigami.Units.gridUnit * 3

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: tile.iconSize
            Layout.preferredHeight: tile.iconSize
            opacity: tile.broken ? 0.4 : 1.0
            source: tile.broken ? "emblem-unavailable"
                                : (tile.isImage ? "file://" + tile.origin : tile.iconName)
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideMiddle
            maximumLineCount: 1
            color: Kirigami.Theme.textColor
            font: Kirigami.Theme.smallFont
            text: tile.itemName
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            font: Kirigami.Theme.smallFont
            color: Format.isUrgent(tile.deadline, tile.now)
                   ? Kirigami.Theme.negativeTextColor
                   : Qt.rgba(Kirigami.Theme.textColor.r,
                             Kirigami.Theme.textColor.g,
                             Kirigami.Theme.textColor.b, 0.6)
            text: Format.remainingLabel(tile.deadline, tile.now)
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        hoverEnabled: true

        onClicked: function (mouse) {
            if (mouse.button === Qt.LeftButton) {
                tile.activated();
            } else if (mouse.button === Qt.MiddleButton) {
                tile.revealRequested();
            } else if (mouse.button === Qt.RightButton) {
                contextMenu.popup();
            }
        }
    }

    Item {
        id: dragProxy
        anchors.fill: parent
        Drag.active: dragHandler.active
        Drag.dragType: Drag.Automatic
        Drag.supportedActions: Qt.CopyAction | Qt.MoveAction

        // text/uri-list carries the origin so other applications receive the
        // real file; text/plain carries the drawer name so the trash corner
        // knows which entry to remove.
        Drag.mimeData: ({
            "text/uri-list": "file://" + tile.origin,
            "text/plain": tile.itemName
        })

        DragHandler {
            id: dragHandler
            target: null
            // Drag.active is an attached property and has no declarable
            // change handler; the handler's own active property does.
            onActiveChanged: tile.draggingChanged(active)
        }
    }

    PlasmaExtras.Menu {
        id: contextMenu

        PlasmaExtras.MenuItem {
            text: "Open"
            icon: "document-open"
            onClicked: tile.activated()
        }
        PlasmaExtras.MenuItem {
            text: "Reveal in Dolphin"
            icon: "folder-open"
            onClicked: tile.revealRequested()
        }
        PlasmaExtras.MenuItem {
            separator: true
        }
        PlasmaExtras.MenuItem {
            text: "Remove now"
            icon: "edit-delete"
            onClicked: tile.removeRequested()
        }
    }
}
```

The drag exposes the **origin**, not the symlink, so dropping into another application yields the real file rather than a link to a link.

- [ ] **Step 2: Write the grid view**

Create `plasmoid/contents/ui/DrawerView.qml`:

```qml
import QtQuick
import org.kde.kirigami as Kirigami

Item {
    id: view

    property var drawer: null
    property var backend: null
    property int iconSize: 48
    property real lifetimeHours: 24

    GridView {
        id: grid
        anchors.fill: parent
        clip: true
        visible: view.drawer && view.drawer.model.count > 0

        cellWidth: view.iconSize * 2 + Kirigami.Units.largeSpacing
        cellHeight: view.iconSize + Kirigami.Units.gridUnit * 3

        model: view.drawer ? view.drawer.model : null

        delegate: ItemTile {
            width: grid.cellWidth
            height: grid.cellHeight

            itemName: model.name
            origin: model.origin
            lastActivity: model.lastActivity
            isDir: model.isDir
            originExists: model.originExists
            iconName: model.iconName
            iconSize: view.iconSize
            lifetimeSeconds: view.lifetimeHours * 3600
            now: view.drawer ? view.drawer.now : 0

            onActivated: view.backend.openPath(model.origin)
            onRevealRequested: view.backend.reveal(model.origin)
            onRemoveRequested: {
                view.backend.remove(model.name);
                view.drawer.reload();
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: !grid.visible
        horizontalAlignment: Text.AlignHCenter
        color: Qt.rgba(Kirigami.Theme.textColor.r,
                       Kirigami.Theme.textColor.g,
                       Kirigami.Theme.textColor.b, 0.6)
        text: "Drop files here\nthey vanish " + Math.round(view.lifetimeHours)
              + "h after you stop using them"
    }
}
```

The empty-state interval is derived from `lifetimeHours` rather than hardcoded, so it stays truthful if the lifetime is changed.

- [ ] **Step 3: Put the view in the frame**

In `plasmoid/contents/ui/main.qml`, replace the `Text` inside `fullRepresentation` with:

```qml
    fullRepresentation: DrawerFrame {
        implicitWidth: 720
        implicitHeight: 340

        DrawerView {
            anchors.fill: parent
            drawer: drawerModel
            backend: cliBackend
            iconSize: Plasmoid.configuration.iconSize
            lifetimeHours: Plasmoid.configuration.lifetimeHours
        }
    }
```

- [ ] **Step 4: Verify by hand**

```bash
kpackagetool6 --type Plasma/Applet --upgrade plasmoid
systemctl --user restart plasma-plasmashell
```
Expected: with an empty drawer, the centred empty-state text. After creating a link by hand (as in Task 10 Step 5), a tile appears within 60 seconds showing the filename and a countdown near `24h`. Left click opens it; middle click opens Dolphin with it selected.

- [ ] **Step 5: Commit**

```bash
git add plasmoid/contents/ui/
git commit -m "feat(plasmoid): item grid with countdowns and open actions"
```

---

### Task 12: Drop target, trash corner, context menu

**Files:**
- Create: `plasmoid/contents/ui/TrashCorner.qml`
- Modify: `plasmoid/contents/ui/DrawerView.qml`
- Modify: `plasmoid/contents/ui/main.qml`

**Interfaces:**
- Consumes: `Backend`, `DrawerModel`.
- Produces: `TrashCorner` with property `active: bool` (whether an internal drag is in progress) and signal `dropped(string name)`.

- [ ] **Step 1: Write the trash corner**

Create `plasmoid/contents/ui/TrashCorner.qml`:

```qml
import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.draganddrop as DragDrop

Item {
    id: trash

    property bool active: false
    signal dropped(string name)

    implicitWidth: Kirigami.Units.iconSizes.medium + Kirigami.Units.largeSpacing
    implicitHeight: implicitWidth

    opacity: active ? 1.0 : 0.0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 120 } }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: dropArea.containsDrag
               ? Kirigami.Theme.negativeTextColor
               : Qt.rgba(Kirigami.Theme.textColor.r,
                         Kirigami.Theme.textColor.g,
                         Kirigami.Theme.textColor.b, 0.15)

        Kirigami.Icon {
            anchors.centerIn: parent
            width: Kirigami.Units.iconSizes.medium
            height: width
            source: "user-trash"
        }
    }

    DragDrop.DropArea {
        id: dropArea
        anchors.fill: parent
        onDrop: function (event) {
            const name = event.mimeData.text;
            if (name) {
                trash.dropped(name);
            }
            event.accept(Qt.MoveAction);
        }
    }
}
```

- [ ] **Step 2: Add the drop target and trash corner to the view**

In `DrawerView.qml`, wrap the contents in a drop area and add the corner:

```qml
    property bool internalDrag: false

    DragDrop.DropArea {
        id: fileDrop
        anchors.fill: parent

        onDrop: function (event) {
            const urls = event.mimeData.urls;
            for (let i = 0; i < urls.length; ++i) {
                view.backend.add(urls[i].toString());
            }
            event.accept(Qt.LinkAction);
            reloadSoon.restart();
        }
    }

    Timer {
        id: reloadSoon
        interval: 300
        onTriggered: view.drawer.reload()
    }

    TrashCorner {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Kirigami.Units.smallSpacing
        active: view.internalDrag
        onDropped: function (name) {
            view.backend.remove(name);
            reloadSoon.restart();
        }
    }
```

Add `import org.kde.draganddrop as DragDrop` to the view's imports, and in the `ItemTile` delegate wire the drag state through:

```qml
            onDraggingChanged: function (dragging) { view.internalDrag = dragging; }
```

Expose the hover state so the frame can react — add to `DrawerView`:

```qml
    readonly property bool dropHovering: fileDrop.containsDrag
```

and in `main.qml`, brighten the dashes while a file hovers over the drawer:

```qml
    fullRepresentation: DrawerFrame {
        id: frame
        implicitWidth: 720
        implicitHeight: 340

        strokeColor: view.dropHovering
                     ? Kirigami.Theme.highlightColor
                     : Qt.rgba(Kirigami.Theme.textColor.r,
                               Kirigami.Theme.textColor.g,
                               Kirigami.Theme.textColor.b, 0.45)

        DrawerView {
            id: view
            anchors.fill: parent
            drawer: drawerModel
            backend: cliBackend
            iconSize: Plasmoid.configuration.iconSize
            lifetimeHours: Plasmoid.configuration.lifetimeHours
        }
    }
```

with `import org.kde.kirigami as Kirigami` added to `main.qml`.

- [ ] **Step 3: Verify by hand**

```bash
kpackagetool6 --type Plasma/Applet --upgrade plasmoid
systemctl --user restart plasma-plasmashell
```

Check each, in order:
1. Drag a file from Dolphin onto the widget. A tile appears within a second. `ls -l ~/.local/share/deskdrawer/items/` shows a symlink to the original.
2. The original file is untouched: `ls -l` on it shows the same size and mtime.
3. Drag a tile: the trash circle fades in at the bottom-right. Drop the tile on it; the tile disappears and the original still exists.
4. Drag a tile into a Dolphin window: Dolphin offers the original file, not a link to a link.
5. Right-click a tile: Open, Reveal in Dolphin, Remove now.
6. Drop a folder: it appears with a folder icon.

- [ ] **Step 4: Commit**

```bash
git add plasmoid/contents/ui/
git commit -m "feat(plasmoid): drop target and trash corner"
```

---

### Task 13: Configuration, installer, end-to-end verification

**Files:**
- Create: `plasmoid/contents/ui/ConfigGeneral.qml`
- Create: `install.sh`
- Create: `README.md`

**Interfaces:**
- Consumes: `Backend.setConfig` from Task 10.
- Produces: config keys `lifetimeHours: int` (default 24) and `iconSize: int` (default 48), mirrored into `~/.config/deskdrawerrc` so the daemon agrees.

- [ ] **Step 1: Write the config page**

Create `plasmoid/contents/ui/ConfigGeneral.qml`. Writing `deskdrawerrc` goes through the CLI so that all file writes stay in one component.

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property alias cfg_lifetimeHours: lifetimeSpin.value
    property alias cfg_iconSize: iconSpin.value

    Backend {
        id: backend
        cli: paths.cli
    }

    Paths { id: paths }

    SpinBox {
        id: lifetimeSpin
        Kirigami.FormData.label: "Keep items for:"
        from: 1
        to: 720
        onValueChanged: backend.setConfig("lifetime_hours", value)
    }

    Label {
        text: "hours after they were last used"
        opacity: 0.7
    }

    SpinBox {
        id: iconSpin
        Kirigami.FormData.label: "Icon size:"
        from: 16
        to: 128
        stepSize: 8
        onValueChanged: backend.setConfig("icon_size", value)
    }
}
```

- [ ] **Step 2: Write the installer**

Create `install.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

DAEMON_DIR="$HOME/.local/share/deskdrawer-daemon"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$DAEMON_DIR" "$BIN_DIR" "$UNIT_DIR"

rm -rf "${DAEMON_DIR:?}/deskdrawer"
cp -r daemon/deskdrawer "$DAEMON_DIR/"

cat > "$BIN_DIR/deskdrawer" <<WRAPPER
#!/bin/sh
PYTHONPATH="$DAEMON_DIR" exec python3 -m deskdrawer.cli "\$@"
WRAPPER
chmod +x "$BIN_DIR/deskdrawer"

cp daemon/deskdrawer.service "$UNIT_DIR/deskdrawer.service"
systemctl --user daemon-reload
systemctl --user enable --now deskdrawer.service

if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -q org.kde.plasma.deskdrawer; then
    kpackagetool6 --type Plasma/Applet --upgrade plasmoid
else
    kpackagetool6 --type Plasma/Applet --install plasmoid
fi

echo
echo "Installed. Add the widget: right-click the desktop, Add Widgets, search DeskDrawer."
echo "Daemon status: systemctl --user status deskdrawer"
```

Make it executable: `chmod +x install.sh`

- [ ] **Step 3: Run the full test suite**

```bash
cd daemon && python3 -m unittest discover -s test -v
cd .. && qmltestrunner -input plasmoid/contents/tests
```
Expected: both suites pass with zero failures.

- [ ] **Step 4: Install and verify end to end**

```bash
./install.sh
systemctl --user status deskdrawer --no-pager
```
Expected: the service is `active (running)`.

Then, with the widget on the desktop:

1. Drop a file. A tile appears with a `24h` countdown.
2. `ls -l ~/.local/share/deskdrawer/items/` shows a symlink; the original is unchanged.
3. `cat ~/.local/share/deskdrawer/state.json` shows the entry with `origin`, `dropped`, `last_activity`.
4. Force an expiry without waiting a day:
   ```bash
   ~/.local/bin/deskdrawer config set lifetime_hours 0.001
   systemctl --user restart deskdrawer
   sleep 2
   ls ~/.local/share/deskdrawer/items/
   ```
   Expected: the link is gone, the original file still exists. Restore with
   `~/.local/bin/deskdrawer config set lifetime_hours 24`.
5. Confirm the origin survived: the file dropped in step 1 is still present with its original content.

- [ ] **Step 5: Write the README**

Create `README.md`:

~~~markdown
# DeskDrawer

A KDE Plasma 6 desktop widget that holds files temporarily. Drop a file or
folder on it and you get a link, the way dropping onto the desktop does. The
link disappears 24 hours after you stop using the file.

**Your files are never touched.** The drawer holds symlinks. Expiry removes the
link and nothing else — the original stays exactly where it was, unmodified.

## The rule

Every item has a deadline of `last activity + 24 hours`. Anything that touches
the origin resets it. An item you keep using stays; an item you ignore for a day
goes away.

Activity is detected two ways, because one is not enough:

- **An hourly scan of `/proc`** catches applications that hold a file open for
  their whole session — VLC, LibreOffice, a running VM.
- **inotify watches** catch applications that read a file and release the
  descriptor within milliseconds — Kate, Okular, GIMP. These would be invisible
  to an hourly poll, so without the watches an item you reopened ten times would
  still expire.

Deadlines are absolute timestamps, so time spent logged out needs no special
handling; the daemon sweeps once at startup and everything lands correctly.

## Install

    ./install.sh

This copies the daemon to `~/.local/share/deskdrawer-daemon`, installs the
`deskdrawer` CLI to `~/.local/bin`, enables the `deskdrawer` systemd user
service, and installs the widget. Add it with right-click desktop -> Add Widgets
-> DeskDrawer.

No pip packages and no system packages are required. inotify is called through
`ctypes`; tests use stdlib `unittest`.

## Using it

| Action | Result |
|---|---|
| Drop a file or folder | Creates a link |
| Left click | Opens it |
| Middle click | Reveals it in Dolphin |
| Drag out | Gives the receiving application the original file |
| Drag onto the trash corner | Removes the link now |
| Right click | Open, Reveal in Dolphin, Remove now |

## Configuration

Right-click the widget -> Configure, or from the command line:

    deskdrawer config set lifetime_hours 48
    deskdrawer config set icon_size 64

Settings live in `~/.config/deskdrawerrc` and are re-read on each hourly tick.

## Where things live

- `~/.local/share/deskdrawer/items/` — the symlinks
- `~/.local/share/deskdrawer/state.json` — origin, drop time, last activity
- `~/.config/deskdrawerrc` — settings

The directory is the source of truth for what exists; `state.json` only supplies
metadata, and is rebuilt from the directory if it is lost or corrupted.

## Troubleshooting

    systemctl --user status deskdrawer
    journalctl --user -u deskdrawer -n 50
    deskdrawer list

## Tests

    cd daemon && python3 -m unittest discover -s test -v
    qmltestrunner -input plasmoid/contents/tests
~~~

- [ ] **Step 6: Commit**

```bash
git add plasmoid/contents/ui/ConfigGeneral.qml install.sh README.md
git commit -m "feat: configuration page, installer and documentation"
```
