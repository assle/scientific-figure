import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property string role: ""
    property var policy: ({})
    Layout.fillWidth: true
    CheckBox { id: expanded; text: "阶段输出额度" }
    ColumnLayout {
        visible: expanded.checked
        Layout.fillWidth: true
        Text {
            text: "各阶段独立；同阶段恢复沿用已发出的额度。额度包含模型推理与最终输出，不是固定消耗量。"
            color: "#64748b"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Repeater {
            model: appController.outputTokenFields
            RowLayout {
                required property var modelData
                property var configured: modelData.key === "max_tokens" ? editor.policy.max_tokens : (editor.policy.phase_initial_tokens || ({}))[modelData.key]
                Layout.fillWidth: true
                Text { text: modelData.label; color: "#64748b"; Layout.fillWidth: true }
                AppTextField {
                    Layout.preferredWidth: 190
                    text: configured === undefined ? "" : String(configured)
                    placeholderText: modelData.hint
                    onEditingFinished: appController.updateOutputTokens(editor.role, modelData.key, text)
                }
            }
        }
    }
}
