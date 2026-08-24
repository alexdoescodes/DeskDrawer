import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property alias cfg_lifetimeHours: lifetimeSpin.value
    property alias cfg_iconSize: iconSpin.value

    Backend {
        id: backend
        cli: paths.cli
    }

    Paths { id: paths }

    SpinBox {
        id: lifetimeSpin
        Kirigami.FormData.label: "Keep items for:"
        from: 1
        to: 720
        onValueChanged: backend.setConfig("lifetime_hours", value)
    }

    Label {
        text: "hours after they were last used"
        opacity: 0.7
    }

    SpinBox {
        id: iconSpin
        Kirigami.FormData.label: "Icon size:"
        from: 16
        to: 128
        stepSize: 8
        onValueChanged: backend.setConfig("icon_size", value)
    }
}
