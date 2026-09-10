import QtQuick

Rectangle {
    id: root
    default property alias content: contentItem.data
    color: "#FFFFFF"
    radius: 14
    border.color: "#DCE4EF"
    border.width: 1
    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: 20
    }
}
