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

    def test_add_honours_config_path_before_the_subcommand(self):
        """A --config-path given before the subcommand must not be discarded."""
        rc = self.root / "rc"
        drawer = self.root / "elsewhere"
        rc.write_text(f"[deskdrawer]\ndrawer_dir = {drawer}\n")
        origin = self.make_file()
        self.assertEqual(cli.main(["--config-path", str(rc), "add", str(origin)]), 0)
        self.assertTrue((drawer / "items" / "a.txt").is_symlink())

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

    def test_config_set_accepts_the_flag_before_the_subcommand(self):
        code = cli.main(["--config-path", str(self.path), "config", "set", "lifetime_hours", "6"])
        self.assertEqual(code, 0)
        self.assertIn("lifetime_hours = 6", self.path.read_text())

    def test_config_set_rejects_unknown_key(self):
        code = cli.main(["config", "set", "nonsense", "1", "--config-path", str(self.path)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
