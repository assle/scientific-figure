import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool active: false
    property bool onDark: false
    checkable: false
    leftPadding: 14
    rightPadding: 14
    topPadding: 11
    bottomPadding: 11
    contentItem: Text {
        text: control.text
        color: control.active ? (control.onDark ? "#FFFFFF" : "#1D4ED8")
                              : (control.onDark ? "#B7C2D3" : "#475467")
        font.pixelSize: 14
        font.weight: control.active ? Font.DemiBold : Font.Medium
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 9
        color: control.active ? (control.onDark ? "#1F5EDB" : "#E8F0FF")
                               : control.hovered ? (control.onDark ? "#162238" : "#F4F7FB") : "transparent"
    }
}
