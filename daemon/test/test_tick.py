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
