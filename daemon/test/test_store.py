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
