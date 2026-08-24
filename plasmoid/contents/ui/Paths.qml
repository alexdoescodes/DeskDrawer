import QtQuick
import QtCore

QtObject {
    readonly property string home: StandardPaths.writableLocation(StandardPaths.HomeLocation).toString().replace("file://", "")
    property string drawerDir: home + "/.local/share/deskdrawer"
    readonly property string statePath: drawerDir + "/state.json"
    readonly property string cli: home + "/.local/bin/deskdrawer"
}
