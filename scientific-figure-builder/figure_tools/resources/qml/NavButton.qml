import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool active: false
    checkable: false
    leftPadding: 14
    rightPadding: 14
    topPadding: 11
    bottomPadding: 11
    contentItem: Text {
        text: control.text
        color: control.active ? "#244FB9" : "#555B63"
        font.pixelSize: 14
        font.weight: control.active ? Font.DemiBold : Font.Medium
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 9
        color: control.active ? "#EAF0FF" : control.hovered ? "#F2F4F6" : "transparent"
    }
}
