import QtQuick
import QtQuick.Controls

TextField {
    id: control
    leftPadding: 12
    rightPadding: 12
    topPadding: 9
    bottomPadding: 9
    font.pixelSize: 13
    color: "#25282D"
    placeholderTextColor: "#9AA0A8"
    selectionColor: "#BFD0FF"
    selectedTextColor: "#17191C"
    background: Rectangle {
        radius: 8
        color: control.enabled ? "#FFFFFF" : "#F0F2F4"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? "#3B6FF5" : "#D9DDE2"
    }
}
