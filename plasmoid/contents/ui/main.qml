import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: fullRepresentation

    Layout.minimumWidth: 320
    Layout.minimumHeight: 160

    readonly property Paths paths: Paths {}
    readonly property real lifetimeSeconds: Plasmoid.configuration.lifetimeHours * 3600

    Backend {
        id: cliBackend
        cli: root.paths.cli
    }

    DrawerModel {
        id: drawerModel
        statePath: root.paths.statePath
        lifetimeSeconds: root.lifetimeSeconds
    }

    fullRepresentation: DrawerFrame {
        id: frame
        implicitWidth: 720
        implicitHeight: 340

        strokeColor: view.dropHovering
                     ? Kirigami.Theme.highlightColor
                     : Qt.rgba(Kirigami.Theme.textColor.r,
                               Kirigami.Theme.textColor.g,
                               Kirigami.Theme.textColor.b, 0.45)

        DrawerView {
            id: view
            anchors.fill: parent
            drawer: drawerModel
            backend: cliBackend
            iconSize: Plasmoid.configuration.iconSize
            lifetimeHours: Plasmoid.configuration.lifetimeHours
        }
    }
}
