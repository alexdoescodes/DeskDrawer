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
