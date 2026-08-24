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
