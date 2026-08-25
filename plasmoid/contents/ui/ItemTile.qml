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

    // The area the tile is allowed to move within. Also the frame of reference
    // for every coordinate reported by the signals below.
    property Item canvas: null

    // Where the tile belongs when it is not being dragged. Applied rather than
    // bound, because dragging writes x/y directly and would break a binding.
    property real homeX: 0
    property real homeY: 0

    signal activated()
    signal revealRequested()
    signal removeRequested()
    signal draggingChanged(bool dragging)
    signal dragMoved(real centerX, real centerY)
    signal droppedAt(real centerX, real centerY)

    readonly property real deadline: lastActivity + lifetimeSeconds
    readonly property bool broken: !originExists
    readonly property bool isImage: iconName === "image-x-generic" && originExists

    // True once the gesture has left the widget and Qt has taken over with a
    // native drag; the tile then belongs to the drop target, not to us.
    property bool handedOff: false

    implicitWidth: iconSize * 2
    implicitHeight: iconSize + Kirigami.Units.gridUnit * 3

    Drag.dragType: Drag.Automatic
    Drag.supportedActions: Qt.CopyAction | Qt.LinkAction

    // text/uri-list carries the origin so other applications receive the real
    // file; text/plain carries the drawer name so a drop target of ours knows
    // which entry it was handed.
    Drag.mimeData: ({
        "text/uri-list": "file://" + tile.origin,
        "text/plain": tile.itemName
    })

    Component.onCompleted: {
        x = homeX;
        y = homeY;
    }

    onHomeXChanged: if (!dragHandler.active) x = homeX
    onHomeYChanged: if (!dragHandler.active) y = homeY

    function _goHome() {
        x = homeX;
        y = homeY;
    }

    function _centerInCanvas() {
        return { x: tile.x + tile.width / 2, y: tile.y + tile.height / 2 };
    }

    // The pointer, not the tile: the tile is clamped to the canvas, so only the
    // pointer can tell us the gesture has left the widget.
    function _pointerLeftCanvas() {
        if (!tile.canvas) {
            return false;
        }
        const point = tile.canvas.mapFromItem(null, dragHandler.centroid.scenePosition);
        return point.x < 0 || point.y < 0
                || point.x > tile.canvas.width || point.y > tile.canvas.height;
    }

    // Hand the gesture to the window system so other applications can receive
    // the file. grabToImage gives the drag a picture of the actual tile, which
    // Drag.Automatic otherwise leaves empty.
    function _handOff() {
        tile.handedOff = true;
        tile.grabToImage(function (result) {
            tile.Drag.imageSource = result.url;
            tile.Drag.active = true;
        });
    }

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

    // Middle and right only. The left button belongs to the TapHandler and the
    // DragHandler below: a MouseArea that also claimed it never saw a single
    // doubleClicked, because the DragHandler's grab on the left button
    // suppresses Qt's double-click synthesis entirely.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.MiddleButton | Qt.RightButton
        hoverEnabled: true

        onClicked: function (mouse) {
            if (mouse.button === Qt.MiddleButton) {
                tile.removeRequested();
            } else if (mouse.button === Qt.RightButton) {
                // QMenuProxy has no popup(); open() takes a position in the
                // visualParent's coordinates.
                contextMenu.open(mouse.x, mouse.y);
            }
        }
    }

    // Opening takes a deliberate double click, so that press-and-drag stays the
    // natural left-button gesture. A TapHandler counts the taps itself rather
    // than relying on the double-click event the DragHandler would swallow.
    // NoModifier, so that a Ctrl-click below is never also an open.
    TapHandler {
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        gesturePolicy: TapHandler.DragThreshold
        onDoubleTapped: tile.activated()
    }

    // Ctrl-click reveals in Dolphin, the same as the context menu entry.
    TapHandler {
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.ControlModifier
        gesturePolicy: TapHandler.DragThreshold
        onSingleTapped: tile.revealRequested()
    }

    // A sibling of the MouseArea, never a child in an overlaying Item: an
    // overlay stacked above the MouseArea swallows the press outright and the
    // tile stops reacting to clicks altogether.
    DragHandler {
        id: dragHandler
        target: tile

        xAxis.minimum: 0
        xAxis.maximum: tile.canvas ? Math.max(0, tile.canvas.width - tile.width) : 0
        yAxis.minimum: 0
        yAxis.maximum: tile.canvas ? Math.max(0, tile.canvas.height - tile.height) : 0

        // Drag.active is an attached property and has no declarable change
        // handler; the handler's own active property does.
        onActiveChanged: {
            tile.draggingChanged(active);
            if (active) {
                tile.handedOff = false;
                return;
            }
            if (tile.handedOff) {
                tile._goHome();
            } else {
                const center = tile._centerInCanvas();
                tile.droppedAt(center.x, center.y);
            }
        }

        onCentroidChanged: {
            if (!active || tile.handedOff) {
                return;
            }
            const center = tile._centerInCanvas();
            tile.dragMoved(center.x, center.y);
            if (tile._pointerLeftCanvas()) {
                tile._handOff();
            }
        }
    }

    // Qt clears Drag.active itself once the native drag finishes.
    Drag.onActiveChanged: if (!Drag.active && tile.handedOff) tile._goHome()

    PlasmaExtras.Menu {
        id: contextMenu
        visualParent: tile

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
