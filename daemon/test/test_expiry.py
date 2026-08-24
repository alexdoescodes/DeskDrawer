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
