import QtQuick
import QtQuick.Controls

Button {
    id: control
    property string kind: "secondary"
    property color primaryColor: "#2563EB"
    property color borderColor: "#DCE4EF"
    property color dangerColor: "#D14343"
    leftPadding: 16
    rightPadding: 16
    topPadding: 9
    bottomPadding: 9
    font.pixelSize: 13
    font.weight: Font.DemiBold
    contentItem: Text {
        text: control.text
        color: control.kind === "primary" || control.kind === "danger" ? "white" : "#1D2939"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font: control.font
        opacity: control.enabled ? 1 : 0.45
    }
    background: Rectangle {
        radius: 9
        color: {
            if (!control.enabled) return "#EEF2F7"
            if (control.kind === "primary") return control.down ? "#1E40AF" : control.primaryColor
            if (control.kind === "danger") return control.down ? "#B42323" : control.dangerColor
            return control.hovered ? "#F4F7FB" : "#FFFFFF"
        }
        border.color: control.kind === "secondary" ? control.borderColor : color
    }
}
