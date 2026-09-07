import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property string role: ""
    property var policy: ({})
    Layout.fillWidth: true
    spacing: 6
    CheckBox { id: expanded; text: "等待与重试设置" }
    ColumnLayout {
        visible: expanded.checked
        Layout.fillWidth: true
        Text {
            text: "留空继承上级设置。状态检查不重发请求；收到消息仅重置无消息计时。"
            color: "#64748b"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Repeater {
            model: appController.requestPolicyFields
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                Text { text: modelData.label; Layout.fillWidth: true; color: "#64748b" }
                AppTextField {
                    Layout.preferredWidth: 110
                    text: editor.policy[modelData.key] === undefined ? "" : String(editor.policy[modelData.key])
                    placeholderText: "继承"
                    onEditingFinished: appController.updateRequestPolicy(editor.role, modelData.key, text)
                }
            }
        }
    }
}
