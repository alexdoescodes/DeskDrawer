#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

DAEMON_DIR="$HOME/.local/share/deskdrawer-daemon"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$DAEMON_DIR" "$BIN_DIR" "$UNIT_DIR"

rm -rf "${DAEMON_DIR:?}/deskdrawer"
cp -r daemon/deskdrawer "$DAEMON_DIR/"

cat > "$BIN_DIR/deskdrawer" <<WRAPPER
#!/bin/sh
PYTHONPATH="$DAEMON_DIR" exec python3 -m deskdrawer.cli "\$@"
WRAPPER
chmod +x "$BIN_DIR/deskdrawer"

cp daemon/deskdrawer.service "$UNIT_DIR/deskdrawer.service"
systemctl --user daemon-reload
systemctl --user enable --now deskdrawer.service

if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -q org.kde.plasma.deskdrawer; then
    kpackagetool6 --type Plasma/Applet --upgrade plasmoid
else
    kpackagetool6 --type Plasma/Applet --install plasmoid
fi

echo
echo "Installed. Add the widget: right-click the desktop, Add Widgets, search DeskDrawer."
echo "Daemon status: systemctl --user status deskdrawer"
