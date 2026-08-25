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
| Drop a file or folder | Creates a link where you dropped it |
| Double left click | Opens it |
| Ctrl + left click | Reveals it in Dolphin |
| Middle click | Removes the link now |
| Drag inside the drawer | Moves the icon; positions are free, not on a grid |
| Drag out | Gives the receiving application the original file |
| Drag onto the trash corner | Removes the link now |
| Right click | Open, Reveal in Dolphin, Remove now |

A single left click only selects, leaving press-and-drag as the natural
gesture. Icon positions are stored in the widget's own configuration, not in
the drawer state, and are pulled back inside the frame when the widget shrinks.

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

## Reloading after a change

`kpackagetool6 --upgrade` writes the new files but a running plasmashell keeps
the QML it loaded at startup, so the widget goes on behaving exactly as before
and the change looks like it failed:

    kquitapp6 plasmashell && kstart plasmashell

Stale compiled QML can also survive in `~/.cache/plasmashell/qmlcache`; delete
it if a change still refuses to appear.

## Tests

    cd daemon && python3 -m unittest discover -s test -v
    QT_FORCE_STDERR_LOGGING=1 /usr/lib/qt6/bin/qmltestrunner -input plasmoid/contents/tests

`qmltestrunner` on `$PATH` is the Qt 5 build and rejects the unversioned
imports these tests use; the Qt 6 binary lives under `/usr/lib/qt6/bin`.
`QT_FORCE_STDERR_LOGGING=1` is what makes QML warnings visible at all -
without it Qt sends them to the journal and every run looks clean.

Mouse gestures that depend on event timing - the double click that opens an
item - cannot be tested there: qmltestrunner's synthetic events carry
timestamps that never advance, so a double click arrives as two unrelated
single clicks and `mouseDoubleClickSequence()` fakes the result. Drive real
input instead, with the widget running under XWayland:

    QT_QPA_PLATFORM=xcb plasmoidviewer -a org.kde.plasma.deskdrawer &
    python3 plasmoid/contents/tests/manual-input.py double <x> <y>
    python3 plasmoid/contents/tests/manual-input.py single <x> <y> Control_L
