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
