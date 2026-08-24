import QtQuick
import org.kde.kirigami as Kirigami

Item {
    id: frame

    property real radius: 12
    property real dashLength: 6
    property real gapLength: 5
    property real borderWidth: 2
    property real padding: 12

    property real backgroundOpacity: 0.35
    property color fillColor: Qt.rgba(Kirigami.Theme.backgroundColor.r,
                                      Kirigami.Theme.backgroundColor.g,
                                      Kirigami.Theme.backgroundColor.b,
                                      frame.backgroundOpacity)
    property color strokeColor: Qt.rgba(Kirigami.Theme.textColor.r,
                                        Kirigami.Theme.textColor.g,
                                        Kirigami.Theme.textColor.b, 0.45)

    default property alias content: interior.data

    onBackgroundOpacityChanged: canvas.requestPaint()
    onFillColorChanged: canvas.requestPaint()
    onStrokeColorChanged: canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();

            const inset = frame.borderWidth / 2;
            const r = frame.radius;
            const w = width - inset;
            const h = height - inset;

            ctx.fillStyle = frame.fillColor;
            ctx.strokeStyle = frame.strokeColor;
            ctx.lineWidth = frame.borderWidth;
            ctx.setLineDash([frame.dashLength, frame.gapLength]);

            ctx.beginPath();
            ctx.moveTo(inset + r, inset);
            ctx.lineTo(w - r, inset);
            ctx.arcTo(w, inset, w, inset + r, r);
            ctx.lineTo(w, h - r);
            ctx.arcTo(w, h, w - r, h, r);
            ctx.lineTo(inset + r, h);
            ctx.arcTo(inset, h, inset, h - r, r);
            ctx.lineTo(inset, inset + r);
            ctx.arcTo(inset, inset, inset + r, inset, r);
            ctx.closePath();

            ctx.fill();
            ctx.stroke();
        }
    }

    Item {
        id: interior
        anchors.fill: parent
        anchors.margins: frame.padding
    }
}
