import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "qmlRoot"
    width: 1120
    height: 760
    minimumWidth: 940
    minimumHeight: 640
    visible: true
    title: "Scientific Figure Builder" + (appController.dirty ? "  •" : "")
    color: theme.canvas

    Theme { id: theme }
    property int pageIndex: appController.page === "models" ? 0
                            : appController.page === "about" ? 2 : 1

    onClosing: function(close) {
        if (appController.dirty) {
            close.accepted = false
            closeDialog.open()
        }
    }

    Rectangle {
        id: sidebar
        objectName: "sidebar"
        width: 224
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        color: theme.surface
        border.color: theme.border

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 20
                spacing: 11
                Rectangle {
                    width: 38; height: 38; radius: 10; color: theme.primary
                    Text {
                        anchors.centerIn: parent
                        text: "SF"
                        color: "white"
                        font.pixelSize: 13
                        font.bold: true
                    }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    Text { text: "Scientific Figure"; color: theme.text; font.pixelSize: 14; font.bold: true }
                    Text { text: "全局配置"; color: theme.textMuted; font.pixelSize: 12 }
                }
            }

            NavButton {
                Layout.fillWidth: true
                text: "模型路由"
                active: appController.page === "models"
                onClicked: appController.setPage("models")
            }
            NavButton {
                Layout.fillWidth: true
                text: "Providers"
                active: appController.page === "providers"
                onClicked: appController.setPage("providers")
            }
            NavButton {
                Layout.fillWidth: true
                text: "凭据与连接"
                active: appController.page === "credentials"
                onClicked: appController.setPage("credentials")
            }
            NavButton {
                Layout.fillWidth: true
                text: "关于"
                active: appController.page === "about"
                onClicked: appController.setPage("about")
            }
            Item { Layout.fillHeight: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
            Text {
                Layout.fillWidth: true
                text: "配置文件\n" + appController.configPath
                color: theme.textMuted
                font.pixelSize: 11
                wrapMode: Text.WrapAnywhere
                lineHeight: 1.35
            }
        }
    }

    ColumnLayout {
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: footer.top
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            color: theme.canvas
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 32
                anchors.rightMargin: 32
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: appController.page === "models" ? "模型路由"
                              : appController.page === "about" ? "关于"
                              : appController.page === "credentials" ? "凭据与连接" : "Providers"
                        color: theme.text
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        text: appController.page === "models" ? "为每个模型角色选择 Provider 和模型 ID"
                              : appController.page === "about" ? "本地、安全、Provider-neutral"
                              : "管理端点、能力和系统凭据"
                        color: theme.textMuted
                        font.pixelSize: 13
                    }
                }
                Rectangle {
                    radius: 12
                    implicitWidth: statusText.implicitWidth + 20
                    implicitHeight: 28
                    color: appController.dirty ? theme.warningSoft : theme.successSoft
                    Text {
                        id: statusText
                        anchors.centerIn: parent
                        text: appController.dirty ? "有未保存修改" : "已保存"
                        color: appController.dirty ? theme.warning : theme.success
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
        }

        Rectangle {
            visible: appController.notification.length > 0
            Layout.fillWidth: true
            Layout.leftMargin: 32
            Layout.rightMargin: 32
            Layout.bottomMargin: 10
            implicitHeight: notificationText.implicitHeight + 18
            radius: 8
            color: appController.notificationKind === "error" ? theme.dangerSoft
                   : appController.notificationKind === "success" ? theme.successSoft
                   : theme.primarySoft
            Text {
                id: notificationText
                anchors.fill: parent
                anchors.margins: 9
                text: appController.notification
                color: appController.notificationKind === "error" ? theme.danger
                       : appController.notificationKind === "success" ? theme.success : "#3158B4"
                wrapMode: Text.Wrap
                font.pixelSize: 12
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.pageIndex

            // Model routes
            Flickable {
                objectName: "modelsPage"
                contentWidth: width
                contentHeight: routeGrid.implicitHeight + 48
                clip: true
                ScrollBar.vertical: ScrollBar { }
                GridLayout {
                    id: routeGrid
                    x: 32; y: 12
                    width: parent.width - 64
                    columns: width > 720 ? 2 : 1
                    rowSpacing: 16
                    columnSpacing: 16
                    Repeater {
                        model: appController.roles
                        delegate: SectionCard {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 238
                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 12
                                RowLayout {
                                    Layout.fillWidth: true
                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Text { text: modelData.label; color: theme.text; font.pixelSize: 16; font.bold: true }
                                        Text { text: modelData.description; color: theme.textMuted; font.pixelSize: 12 }
                                    }
                                    Switch {
                                        visible: modelData.role === "image_edit"
                                        text: "继承生成"
                                        checked: modelData.inherit
                                        onToggled: appController.setRoleInheritance(modelData.role, checked)
                                    }
                                }
                                Text { text: "Provider"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                                AppComboBox {
                                    Layout.fillWidth: true
                                    enabled: !modelData.inherit
                                    model: appController.providerIds
                                    currentIndex: appController.providerIds.indexOf(modelData.provider)
                                    onActivated: appController.updateRole(modelData.role, "provider", currentText)
                                }
                                Text { text: "模型 ID"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                                AppTextField {
                                    Layout.fillWidth: true
                                    enabled: !modelData.inherit
                                    text: modelData.model
                                    placeholderText: "输入固定模型或 Endpoint ID"
                                    onEditingFinished: appController.updateRole(modelData.role, "model", text)
                                }
                            }
                        }
                    }
                    Rectangle {
                        visible: appController.warningText.length > 0
                        Layout.columnSpan: routeGrid.columns
                        Layout.fillWidth: true
                        Layout.preferredHeight: warningText.implicitHeight + 24
                        color: theme.warningSoft
                        radius: 10
                        Text {
                            id: warningText
                            anchors.fill: parent
                            anchors.margins: 12
                            text: appController.warningText
                            color: theme.warning
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }

            // Providers and credentials
            RowLayout {
                objectName: "providersPage"
                spacing: 16
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.bottomMargin: 24

                SectionCard {
                    Layout.preferredWidth: 290
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "Providers"; color: theme.text; font.pixelSize: 15; font.bold: true; Layout.fillWidth: true }
                            AppButton { text: "+ 新增"; onClicked: addDialog.open() }
                        }
                        ListView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 6
                            clip: true
                            model: appController.providers
                            delegate: ItemDelegate {
                                required property var modelData
                                width: ListView.view.width
                                height: 66
                                onClicked: appController.selectProvider(modelData.id)
                                background: Rectangle {
                                    radius: 9
                                    color: modelData.id === appController.selectedProviderId ? theme.primarySoft
                                           : parent.hovered ? theme.surfaceMuted : "transparent"
                                }
                                contentItem: Column {
                                    spacing: 4
                                    Text { text: modelData.id; color: theme.text; font.pixelSize: 13; font.bold: true }
                                    Row {
                                        spacing: 8
                                        Text { text: modelData.type; color: theme.textMuted; font.pixelSize: 11 }
                                        Text { text: "• " + modelData.credential_status; color: theme.textMuted; font.pixelSize: 11 }
                                    }
                                }
                            }
                        }
                        Text {
                            visible: appController.providers.length === 0
                            Layout.fillWidth: true
                            Layout.topMargin: 24
                            horizontalAlignment: Text.AlignHCenter
                            text: "还没有 Provider\n点击右上角开始配置"
                            color: theme.textMuted
                            font.pixelSize: 12
                            lineHeight: 1.4
                        }
                    }
                }

                SectionCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: appController.selectedProviderId.length > 0
                    Flickable {
                        anchors.fill: parent
                        contentWidth: width
                        contentHeight: providerForm.implicitHeight
                        clip: true
                        ScrollBar.vertical: ScrollBar { }
                        ColumnLayout {
                            id: providerForm
                            width: parent.width
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Column {
                                    Layout.fillWidth: true
                                    Text { text: appController.selectedProviderId; color: theme.text; font.pixelSize: 19; font.bold: true }
                                    Text { text: appController.selectedProvider.credential_status || "未配置"; color: theme.textMuted; font.pixelSize: 12 }
                                }
                                AppButton { text: "重命名"; onClicked: renameDialog.open() }
                                AppButton { text: "删除"; kind: "danger"; onClicked: deleteDialog.open() }
                            }
                            Text { text: "Provider 类型"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                            AppComboBox {
                                Layout.fillWidth: true
                                model: ["openai", "anthropic"]
                                currentIndex: model.indexOf(appController.selectedProvider.type || "openai")
                                onActivated: appController.updateProvider("type", currentText)
                            }
                            Text { text: "Base URL"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                            AppTextField {
                                Layout.fillWidth: true
                                text: appController.selectedProvider.base_url || ""
                                placeholderText: "https://api.example.com/v1"
                                onEditingFinished: appController.updateProvider("base_url", text)
                            }
                            Text { text: "环境变量回退"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                            AppTextField {
                                Layout.fillWidth: true
                                text: appController.selectedProvider.key_env || ""
                                placeholderText: "PROVIDER_API_KEY"
                                onEditingFinished: appController.updateProvider("key_env", text)
                            }
                            Text { text: "API Key"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                            AppTextField {
                                Layout.fillWidth: true
                                text: appController.selectedProvider.api_key || ""
                                echoMode: TextInput.Password
                                placeholderText: "留空保留现有凭据"
                                onEditingFinished: appController.updateProvider("api_key", text)
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                AppButton {
                                    text: appController.connectionRunning ? "测试中…" : "测试连接"
                                    enabled: !appController.connectionRunning
                                    kind: "primary"
                                    onClicked: appController.testConnection()
                                }
                                AppButton {
                                    visible: appController.connectionRunning
                                    text: "取消"
                                    onClicked: appController.cancelConnection()
                                }
                                Item { Layout.fillWidth: true }
                                AppButton { text: "移除凭据"; onClicked: appController.clearCredential() }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border; Layout.topMargin: 6; Layout.bottomMargin: 4 }
                            Text { text: "高级设置"; color: theme.text; font.pixelSize: 14; font.bold: true }
                            Text { text: "认证方式"; color: theme.textMuted; font.pixelSize: 11; font.bold: true }
                            AppComboBox {
                                Layout.fillWidth: true
                                model: ["x-api-key", "bearer"]
                                currentIndex: model.indexOf(appController.selectedProvider.auth_scheme || "x-api-key")
                                onActivated: appController.updateProvider("auth_scheme", currentText)
                            }
                            AppTextField {
                                Layout.fillWidth: true
                                text: appController.selectedProvider.messages_path || "/messages"
                                placeholderText: "Messages path"
                                onEditingFinished: appController.updateProvider("messages_path", text)
                            }
                            AppTextField {
                                Layout.fillWidth: true
                                text: appController.selectedProvider.anthropic_version || "2023-06-01"
                                placeholderText: "Anthropic version"
                                onEditingFinished: appController.updateProvider("anthropic_version", text)
                            }
                            Switch {
                                text: "支持参考图编辑"
                                checked: appController.selectedProvider.supports_image_edit || false
                                onToggled: appController.updateProviderBool("supports_image_edit", checked)
                            }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }
                }
                SectionCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: appController.selectedProviderId.length === 0
                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "创建第一个 Provider"
                            color: theme.text
                            font.pixelSize: 18
                            font.bold: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "配置端点、模型能力和系统凭据"
                            color: theme.textMuted
                            font.pixelSize: 12
                        }
                        AppButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "+ 新增 Provider"
                            kind: "primary"
                            onClicked: addDialog.open()
                        }
                    }
                }
            }

            // About
            Item {
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(560, parent.width - 64)
                    spacing: 16
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 64; height: 64; radius: 18; color: theme.primary
                        Text { anchors.centerIn: parent; text: "SF"; color: "white"; font.pixelSize: 20; font.bold: true }
                    }
                    Text { Layout.alignment: Qt.AlignHCenter; text: "Scientific Figure Builder"; color: theme.text; font.pixelSize: 22; font.bold: true }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: "模型路由、Provider 与系统凭据的本地配置工具。\n不启动浏览器，不监听端口，配置保存不会联网。"
                        color: theme.textMuted
                        font.pixelSize: 13
                        lineHeight: 1.45
                    }
                }
            }
        }
    }

    Rectangle {
        id: footer
        objectName: "footer"
        height: 72
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        color: theme.surface
        border.color: theme.border
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 32
            anchors.rightMargin: 32
            Text {
                Layout.fillWidth: true
                text: appController.dirty ? "修改仅保存在本窗口草稿中" : "配置与凭据状态已同步"
                color: theme.textMuted
                font.pixelSize: 12
            }
            AppButton { text: "放弃修改"; visible: appController.dirty; onClicked: appController.discardChanges() }
            AppButton {
                objectName: "saveButton"
                text: "保存配置"
                kind: "primary"
                enabled: appController.dirty
                onClicked: appController.save()
            }
        }
    }

    Dialog {
        id: addDialog
        width: 400
        title: "新增 Provider"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        onOpened: addField.forceActiveFocus()
        onAccepted: {
            if (appController.addProvider(addField.text)) addField.text = ""
            else open()
        }
        contentItem: AppTextField { id: addField; width: 320; placeholderText: "例如 deepseek_vision" }
    }
    Dialog {
        id: renameDialog
        width: 400
        title: "重命名 Provider"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        anchors.centerIn: parent
        onOpened: { renameField.text = appController.selectedProviderId; renameField.selectAll(); renameField.forceActiveFocus() }
        onAccepted: { if (!appController.renameSelectedProvider(renameField.text)) open() }
        contentItem: AppTextField { id: renameField; width: 320 }
    }
    Dialog {
        id: deleteDialog
        width: 400
        title: "删除 Provider"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        contentItem: Text { text: "确定删除 “" + appController.selectedProviderId + "” 吗？"; color: theme.text }
        onAccepted: appController.deleteSelectedProvider()
    }
    Dialog {
        id: costDialog
        width: 420
        title: "可能产生费用"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        contentItem: Text { width: 360; wrapMode: Text.Wrap; text: "当前只有图像生成路径可用，连接测试可能产生 Provider 费用。继续？" }
        onAccepted: appController.confirmConnectionTest(true)
        onRejected: appController.confirmConnectionTest(false)
    }
    Dialog {
        id: closeDialog
        width: 400
        title: "有未保存修改"
        modal: true
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel
        anchors.centerIn: parent
        contentItem: Text { text: "关闭前是否保存当前配置？"; color: theme.text }
        onAccepted: { if (appController.save()) root.close() }
        onDiscarded: { appController.discardChanges(); root.close() }
    }
    Connections {
        target: appController
        function onCostConfirmationRequested() { costDialog.open() }
    }
}
