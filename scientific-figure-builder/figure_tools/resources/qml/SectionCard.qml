import QtQuick

Rectangle {
    id: root
    default property alias content: contentItem.data
    color: "#FFFFFF"
    radius: 12
    border.color: "#E3E6EA"
    border.width: 1
    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: 20
    }
}
