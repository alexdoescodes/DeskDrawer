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

    readonly property bool dropHovering: fileDrop.containsDrag

    GridView {
        id: grid
        anchors.fill: parent
        clip: true
        visible: view.drawer && view.drawer.model.count > 0

        cellWidth: view.iconSize * 2 + Kirigami.Units.largeSpacing
        cellHeight: view.iconSize + Kirigami.Units.gridUnit * 3

        model: view.drawer ? view.drawer.model : null

        delegate: ItemTile {
            width: grid.cellWidth
            height: grid.cellHeight

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
            onDraggingChanged: function (dragging) { view.internalDrag = dragging; }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: !grid.visible
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
