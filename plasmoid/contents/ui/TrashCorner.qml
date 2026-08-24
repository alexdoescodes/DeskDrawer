import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.draganddrop as DragDrop

Item {
    id: trash

    property bool active: false
    signal dropped(string name)

    implicitWidth: Kirigami.Units.iconSizes.medium + Kirigami.Units.largeSpacing
    implicitHeight: implicitWidth

    opacity: active ? 1.0 : 0.0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 120 } }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: dropArea.containsDrag
               ? Kirigami.Theme.negativeTextColor
               : Qt.rgba(Kirigami.Theme.textColor.r,
                         Kirigami.Theme.textColor.g,
                         Kirigami.Theme.textColor.b, 0.15)

        Kirigami.Icon {
            anchors.centerIn: parent
            width: Kirigami.Units.iconSizes.medium
            height: width
            source: "user-trash"
        }
    }

    DragDrop.DropArea {
        id: dropArea
        anchors.fill: parent
        onDrop: function (event) {
            const name = event.mimeData.text;
            if (name) {
                trash.dropped(name);
            }
            event.accept(Qt.MoveAction);
        }
    }
}
