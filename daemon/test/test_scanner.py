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
