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
        color: control.enabled ? "#25282D" : "#9AA0A8"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        font: control.font
    }
    indicator: Text {
        x: control.width - width - 12
        y: (control.height - height) / 2 - 1
        text: "⌄"
        color: "#666C74"
        font.pixelSize: 17
    }
    background: Rectangle {
        radius: 8
        color: control.enabled ? "#FFFFFF" : "#F0F2F4"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#3B6FF5" : "#D9DDE2"
    }
}
