import QtQuick
import QtQuick.Controls

TextField {
    id: control
    leftPadding: 12
    rightPadding: 12
    topPadding: 9
    bottomPadding: 9
    font.pixelSize: 13
    color: "#1D2939"
    placeholderTextColor: "#98A2B3"
    selectionColor: "#BFD3FF"
    selectedTextColor: "#101828"
    background: Rectangle {
        radius: 9
        color: control.enabled ? "#FFFFFF" : "#EEF2F7"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#2563EB" : "#D7DEE8"
    }
}
