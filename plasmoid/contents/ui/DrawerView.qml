import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.draganddrop as DragDrop

Item {
    id: view

    property var drawer: null
    property var backend: null
    property int iconSize: 48
    property real lifetimeHours: 24
    property bool internalDrag: false

    // Serialized name -> point map, owned by the widget configuration.
    property string savedPositions: "{}"
    signal positionsPersistRequested(string json)

    readonly property bool dropHovering: fileDrop.containsDrag

    // Drop points waiting for the names the daemon will give them. A dropped
    // file only gets its name once the store has linked it, which is a reload
    // later, so the point is parked here until the entry appears.
    property var pendingDrops: []

    onSavedPositionsChanged: positions.load(view.savedPositions)

    PositionMap {
        id: positions
        tileWidth: view.iconSize * 2
        tileHeight: view.iconSize + Kirigami.Units.gridUnit * 3
        canvasWidth: board.width
        canvasHeight: board.height
        onUpdated: view.positionsPersistRequested(positions.serialize())
    }

    function _names() {
        const names = [];
        if (!view.drawer) {
            return names;
        }
        for (let i = 0; i < view.drawer.model.count; ++i) {
            names.push(view.drawer.model.get(i).name);
        }
        return names;
    }

    // Give every entry a home and forget the ones that have left the drawer.
    function _syncPositions() {
        const names = view._names();
        positions.prune(names);
        for (let i = 0; i < names.length; ++i) {
            if (positions.has(names[i])) {
                continue;
            }
            const point = view.pendingDrops.length > 0 ? view.pendingDrops.shift() : null;
            if (point) {
                positions.place(names[i], point.x, point.y);
            } else {
                positions.autoPlace(names[i]);
            }
        }
    }

    function _overTrash(x, y) {
        return x >= trashCorner.x && x <= trashCorner.x + trashCorner.width
                && y >= trashCorner.y && y <= trashCorner.y + trashCorner.height;
    }

    Connections {
        target: view.drawer
        function onLoaded() { view._syncPositions(); }
    }

    Item {
        id: board
        anchors.fill: parent

        onWidthChanged: positions.clampAll()
        onHeightChanged: positions.clampAll()

        Repeater {
            model: view.drawer ? view.drawer.model : null

            delegate: ItemTile {
                width: positions.tileWidth
                height: positions.tileHeight
                canvas: board

                homeX: {
                    const point = positions.points[model.name];
                    return point ? point.x : 0;
                }
                homeY: {
                    const point = positions.points[model.name];
                    return point ? point.y : 0;
                }

                itemName: model.name
                origin: model.origin
                lastActivity: model.lastActivity
                isDir: model.isDir
                originExists: model.originExists
                iconName: model.iconName
                iconSize: view.iconSize
                lifetimeSeconds: view.lifetimeHours * 3600
                now: view.drawer ? view.drawer.now : 0

                onActivated: view.backend.openPath(model.origin)
                onRevealRequested: view.backend.reveal(model.origin)
                onRemoveRequested: {
                    view.backend.remove(model.name);
                    view.drawer.reload();
                }
                onDraggingChanged: function (dragging) {
                    view.internalDrag = dragging;
                    if (!dragging) {
                        trashCorner.hovered = false;
                    }
                }
                onDragMoved: function (centerX, centerY) {
                    trashCorner.hovered = view._overTrash(centerX, centerY);
                }
                onDroppedAt: function (centerX, centerY) {
                    if (view._overTrash(centerX, centerY)) {
                        view.backend.remove(model.name);
                        reloadSoon.restart();
                    } else {
                        positions.place(model.name, x, y);
                    }
                }
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: !view.drawer || view.drawer.model.count === 0
        horizontalAlignment: Text.AlignHCenter
        color: Qt.rgba(Kirigami.Theme.textColor.r,
                       Kirigami.Theme.textColor.g,
                       Kirigami.Theme.textColor.b, 0.6)
        text: "Drop files here\nthey vanish " + Math.round(view.lifetimeHours)
              + "h after you stop using them"
    }

    DragDrop.DropArea {
        id: fileDrop
        anchors.fill: parent

        onDrop: function (event) {
            const urls = event.mimeData.urls;
            for (let i = 0; i < urls.length; ++i) {
                // Centre the tile on the cursor rather than hanging it off to
                // the lower right of where the file was let go.
                view.pendingDrops.push({
                    x: event.x - positions.tileWidth / 2,
                    y: event.y - positions.tileHeight / 2
                });
                view.backend.add(urls[i].toString());
            }
            event.accept(Qt.LinkAction);
            reloadSoon.restart();
        }
    }

    Timer {
        id: reloadSoon
        interval: 300
        onTriggered: view.drawer.reload()
    }

    TrashCorner {
        id: trashCorner
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Kirigami.Units.smallSpacing
        active: view.internalDrag
        onDropped: function (name) {
            view.backend.remove(name);
            reloadSoon.restart();
        }
    }
}
