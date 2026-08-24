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
    # A shared parent so --config-path is accepted both before and after the
    # subcommand (argparse subparsers otherwise swallow the remaining argv
    # and only recognize options declared on the matching subparser).
    config_path_parent = argparse.ArgumentParser(add_help=False)
    config_path_parent.add_argument("--config-path", default=None)

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
    config_path = Path(args.config_path) if args.config_path else None

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
