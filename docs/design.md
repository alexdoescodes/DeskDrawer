# DeskDrawer — Design

**Date:** 2026-08-24
**Status:** Approved, ready for implementation planning

## Summary

DeskDrawer is a KDE Plasma 6 desktop widget that acts as a temporary parking
spot for files. Dropping a file or folder onto it creates a symlink, the way
dropping onto the desktop does. Each item disappears 24 hours after you stop
using it. Only the link is removed; the original file is never touched.

The widget renders as an opaque grey rounded rectangle with a dashed border,
sitting on the desktop as a wide landscape panel.

## Motivation

Files that matter for a day — a downloaded PDF, an installer, a folder from a
current task — accumulate on the desktop and stay there for months. DeskDrawer
gives them a place that cleans itself up, without risking the files themselves.

## Requirements

1. Dropping a file or folder creates a link to it in the drawer.
2. An item expires 24 hours after its last activity.
3. Activity means the file is open, or was opened, since the last check.
4. Expiry removes the link only. Origins are never modified, moved, or deleted.
5. Items are shown as an icon grid with a visible countdown.
6. Items can be opened, revealed in Dolphin, dragged out, and removed by hand.
7. Expiry is correct across logout, reboot, and daemon restarts.

### Non-goals

- No pinning or exemption. Items are temporary by definition.
- No sync, history, or undo of expired items.
- No reuse of `org.kde.plasma.folder`. The widget is built clean.

## Architecture

Two components sharing a directory. No socket, no IPC protocol, no versioned
message format.

    ~/.local/share/deskdrawer/
    |-- items/
    |   |-- report.pdf   -> /home/user/Downloads/report.pdf
    |   `-- project      -> /home/user/Documents/project
    `-- state.json

The plasmoid owns the UI and two trivial operations (create link, remove link),
both delegated to a helper CLI. The daemon owns everything with real logic:
activity detection, deadline bookkeeping, and the expiry sweep. The daemon
writes `state.json`; the widget reads it.

This split exists so that the component which deletes things is a plain Python
module that runs under unit test, rather than logic embedded in QML.

### Repository layout

    DeskDrawer/
    |-- daemon/
    |   |-- deskdrawer/
    |   |   |-- __main__.py    wiring, hourly tick
    |   |   |-- cli.py         `deskdrawer add|remove <path>`
    |   |   |-- store.py       state.json + symlink CRUD
    |   |   |-- watcher.py     ctypes inotify wrapper
    |   |   |-- scanner.py     /proc/*/fd + /proc/*/cwd sweep
    |   |   `-- expiry.py      deadline logic + sweep
    |   |-- test/
    |   `-- deskdrawer.service
    |-- plasmoid/
    |   |-- metadata.json      org.kde.plasma.deskdrawer
    |   `-- contents/
    |       |-- config/
    |       `-- ui/
    `-- install.sh

## Environment findings

These were verified on the target machine and constrain the design:

- `/` is mounted `noatime`. Access times never update, so atime cannot be used
  as an activity signal. inotify is required, not optional.
- No `inotify_simple`, `pyinotify`, or `inotify-tools` are installed. inotify is
  implemented directly over the syscalls via `ctypes`.
- No `pytest`. Tests use stdlib `unittest`.
- `qmltestrunner` is available for the QML side.
- Python 3.14.6, Plasma 6.7.2. `org.kde.draganddrop` and
  `org.kde.plasma.plasma5support` are present; there is no `org.kde.kio` QML
  module, so file operations go through the helper CLI.

The project has no pip and no pacman dependencies.

## Component: the widget

An opaque rounded `Rectangle` with a dashed border drawn using `QtQuick.Shapes`
(`ShapePath.DashLine`), giving real dashes rather than a border-image
approximation. Background and dash colours derive from the Plasma theme so the
widget follows light and dark themes.

Contents are a `GridView` of item tiles. Each tile shows a file-type icon (or an
image thumbnail where applicable), the elided filename, and the remaining time
beneath it, formatted as `18h`, `4h`, or `47m`. Under one hour the countdown
turns to the theme's negative colour.

### Interactions

| Action | Result |
|---|---|
| Drop file or folder | Creates a link via `deskdrawer add` |
| Left click | Opens the origin with `xdg-open` |
| Middle click | `dolphin --select <origin>` |
| Drag out | Provides `text/uri-list` of the **origin** path |
| Drag onto trash corner | Removes the link |
| Right click | Context menu: Open, Reveal in Dolphin, Remove |

Dragging out exposes the origin rather than the symlink, so dropping into
another application yields the real file rather than a link to a link.

The trash corner is a small `DropArea` in the bottom-right that becomes visible
and highlights while an internal drag is in progress.

Empty state shows centred text: "Drop files here - they vanish 24h after you
stop using them", with the interval taken from `lifetime_hours` rather than
hardcoded, so it stays truthful if the lifetime is changed.

### Reading state

The widget reads `state.json` over `file://` with `XMLHttpRequest` and refreshes
every 60 seconds, which is sufficient granularity for an hour-resolution
countdown. Countdown labels are recomputed locally between reads.

## Component: the daemon

A single long-running process under a systemd **user** service, with an internal
hourly tick. A long-running process is required because inotify watches must
persist; a systemd timer firing a one-shot would lose them.

### Adding an item

`deskdrawer add <path>` resolves the origin with `realpath`, creates a symlink in
`items/`, and records the entry. Name collisions are suffixed (`report (2).pdf`).
Adding a path already present in the drawer is a no-op rather than a duplicate.

Path quoting happens once, inside the CLI, rather than being composed into shell
strings inside QML.

### Activity detection

The deadline for an item is always `lastActivity + 24h`, stored as an absolute
timestamp. Because deadlines are absolute, time spent logged out needs no
special handling: the daemon sweeps once at startup and every item lands
correctly.

Two sensors feed one rule. Either stamps `lastActivity = now`.

**Hourly `/proc` scan.** Walks `/proc/*/fd/` and `/proc/*/cwd`, resolves each
link, and matches against known origins. Files match exactly. Folders match by
path prefix, so a video playing inside a dropped folder keeps that folder alive,
as does a terminal whose working directory is inside it. Only the user's own
processes are readable, which is exactly the set that matters.

**inotify watch.** `IN_OPEN | IN_ACCESS | IN_MODIFY | IN_CLOSE_WRITE |
IN_CLOSE_NOWRITE` on each origin. This exists because applications split into
two camps: some hold the file open for their whole session (VLC, LibreOffice)
and are caught by the poll, while others read and release the descriptor within
milliseconds (Kate, Okular, GIMP) and would be invisible to an hourly poll
entirely. Without this watch, items you actively reopen would still expire.

Folders are watched one level deep. Deeper activity is covered by the
prefix-matching `/proc` scan.

### Expiry sweep

Runs on the hourly tick and once at startup. For each item where
`now > lastActivity + lifetime`, the sweep calls `os.unlink` on the **symlink
path** and removes the entry from `state.json`. `os.unlink` on a symlink removes
the link itself and never follows it, which is what makes the non-destructive
guarantee structural rather than a matter of care.

No code path in this project deletes, moves, or writes to an origin. `expiry.py`
receives symlink paths only and never resolves them to origins. This is asserted
by test.

Dangling links, where the origin was moved or deleted, render dimmed with a
broken-link icon and age out on the normal schedule.

### State file

`state.json` maps drawer filename to `{origin, dropped, lastActivity}`. It is
written to a temporary file and `rename`d into place, so a crash mid-write
cannot leave it corrupt. A missing or unparseable state file is rebuilt from the
directory contents with `lastActivity` seeded to the symlink's own mtime, rather
than being treated as fatal.

## Configuration

Settings shared by both components live in `~/.config/deskdrawerrc`, a plain
INI file. The widget's config dialog does not write it directly; it calls
`deskdrawer config set <key> <value>`, keeping all file writes in one component.
The daemon re-reads the file on each hourly tick, so changes take effect without
a restart.

- `lifetime_hours`, default 24.
- `drawer_dir`, default `~/.local/share/deskdrawer`.
- `icon_size`, default 48.

Purely visual settings with no daemon relevance (icon size) also live in the
plasmoid's own Plasma config; `deskdrawerrc` is the source of truth only for
what both components need to agree on.

## Testing

`store.py`, `scanner.py`, and `expiry.py` take an injected clock and root
directory, so the entire core runs against a temporary directory with no daemon,
no real `/proc`, and no sleeping.

Cases:

- Expiry removes the link and leaves the origin present and unmodified.
- Activity from the poll sensor pushes the deadline.
- Activity from the inotify sensor pushes the deadline.
- Timeline: drop, 23h pass, touch, 23h more pass, item still alive.
- Timeline: drop, 25h pass untouched, item gone.
- Name collisions produce distinct entries.
- Re-adding an existing origin is a no-op.
- Dangling links expire without error.
- Corrupt or missing `state.json` is rebuilt rather than crashing.
- Folder prefix matching: an fd inside a dropped folder counts as activity.
- Startup sweep applies deadlines missed while the daemon was not running.

`scanner.py` is tested against a fabricated `/proc`-shaped tree rather than the
real one, so the tests are deterministic.

QML tests under `qmltestrunner` cover the item model and countdown formatting.

## Installation

`./install.sh`:

1. `kpackagetool6 --install plasmoid` (or `--upgrade` when already present).
2. Copy `deskdrawer.service` into `~/.config/systemd/user/`.
3. `systemctl --user enable --now deskdrawer`.

## Risks

**A file open for over 24h continuously.** The poll sees it open each hour and
keeps resetting the deadline, so it survives — correct under the stated rule.

**Very large dropped folders.** Prefix matching is a string comparison against a
small set of origins, so cost scales with open descriptors rather than folder
size. One-level inotify watches bound the watch count.

**Clock changes.** Deadlines use wall-clock time, so a large manual clock change
shifts expiry. Accepted; the alternative complicates the state file for a rare
event.
