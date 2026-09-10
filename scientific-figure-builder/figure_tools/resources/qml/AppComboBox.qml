import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    leftPadding: 12
    rightPadding: 34
    topPadding: 9
    bottomPadding: 9
    font.pixelSize: 13
    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: control.displayText
        color: control.enabled ? "#1D2939" : "#98A2B3"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        font: control.font
    }
    indicator: Text {
        x: control.width - width - 12
        y: (control.height - height) / 2 - 1
        text: "⌄"
        color: "#667085"
        font.pixelSize: 17
    }
    background: Rectangle {
        radius: 9
        color: control.enabled ? "#FFFFFF" : "#EEF2F7"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#2563EB" : "#D7DEE8"
    }
}
