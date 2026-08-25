import QtQuick
import QtQuick.Controls

Button {
    id: control
    property string kind: "secondary"
    property color primaryColor: "#3B6FF5"
    property color borderColor: "#E3E6EA"
    property color dangerColor: "#C63C3C"
    leftPadding: 16
    rightPadding: 16
    topPadding: 9
    bottomPadding: 9
    font.pixelSize: 13
    font.weight: Font.DemiBold
    contentItem: Text {
        text: control.text
        color: control.kind === "primary" || control.kind === "danger" ? "white" : "#272A2F"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font: control.font
        opacity: control.enabled ? 1 : 0.45
    }
    background: Rectangle {
        radius: 8
        color: {
            if (!control.enabled) return "#EEF0F2"
            if (control.kind === "primary") return control.down ? "#2856CC" : control.primaryColor
            if (control.kind === "danger") return control.down ? "#A92F2F" : control.dangerColor
            return control.hovered ? "#F1F3F5" : "#FFFFFF"
        }
        border.color: control.kind === "secondary" ? control.borderColor : color
    }
}
