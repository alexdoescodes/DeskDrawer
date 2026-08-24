import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.extras as PlasmaExtras
import "../code/format.js" as Format

Item {
    id: tile

    property string itemName: ""
    property string origin: ""
    property real lastActivity: 0
    property bool isDir: false
    property bool originExists: true
    property string iconName: "unknown"
    property int iconSize: 48
    property real lifetimeSeconds: 24 * 3600
    property real now: 0

    signal activated()
    signal revealRequested()
    signal removeRequested()
    signal draggingChanged(bool dragging)

    readonly property real deadline: lastActivity + lifetimeSeconds
    readonly property bool broken: !originExists
    readonly property bool isImage: iconName === "image-x-generic" && originExists

    implicitWidth: iconSize * 2
    implicitHeight: iconSize + Kirigami.Units.gridUnit * 3

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: tile.iconSize
            Layout.preferredHeight: tile.iconSize
            opacity: tile.broken ? 0.4 : 1.0
            source: tile.broken ? "emblem-unavailable"
                                : (tile.isImage ? "file://" + tile.origin : tile.iconName)
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideMiddle
            maximumLineCount: 1
            color: Kirigami.Theme.textColor
            font: Kirigami.Theme.smallFont
            text: tile.itemName
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            font: Kirigami.Theme.smallFont
            color: Format.isUrgent(tile.deadline, tile.now)
                   ? Kirigami.Theme.negativeTextColor
                   : Qt.rgba(Kirigami.Theme.textColor.r,
                             Kirigami.Theme.textColor.g,
                             Kirigami.Theme.textColor.b, 0.6)
            text: Format.remainingLabel(tile.deadline, tile.now)
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        hoverEnabled: true

        onClicked: function (mouse) {
            if (mouse.button === Qt.LeftButton) {
                tile.activated();
            } else if (mouse.button === Qt.MiddleButton) {
                tile.revealRequested();
            } else if (mouse.button === Qt.RightButton) {
                contextMenu.popup();
            }
        }
    }

    Item {
        id: dragProxy
        anchors.fill: parent
        Drag.active: dragHandler.active
        Drag.dragType: Drag.Automatic
        Drag.supportedActions: Qt.CopyAction | Qt.MoveAction

        // text/uri-list carries the origin so other applications receive the
        // real file; text/plain carries the drawer name so the trash corner
        // knows which entry to remove.
        Drag.mimeData: ({
            "text/uri-list": "file://" + tile.origin,
            "text/plain": tile.itemName
        })

        DragHandler {
            id: dragHandler
            target: null
            // Drag.active is an attached property and has no declarable
            // change handler; the handler's own active property does.
            onActiveChanged: tile.draggingChanged(active)
        }
    }

    PlasmaExtras.Menu {
        id: contextMenu

        PlasmaExtras.MenuItem {
            text: "Open"
            icon: "document-open"
            onClicked: tile.activated()
        }
        PlasmaExtras.MenuItem {
            text: "Reveal in Dolphin"
            icon: "folder-open"
            onClicked: tile.revealRequested()
        }
        PlasmaExtras.MenuItem {
            separator: true
        }
        PlasmaExtras.MenuItem {
            text: "Remove now"
            icon: "edit-delete"
            onClicked: tile.removeRequested()
        }
    }
}
