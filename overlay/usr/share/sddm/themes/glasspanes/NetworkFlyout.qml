// The sign-in screen's network flyout, like Windows 11: Wi-Fi on/off, nearby networks, and joining
// one with its password. Loaded by Main.qml through a Loader, so if KDE's network module can't be
// loaded the rest of the sign-in screen still works.
import QtQuick
import org.kde.plasma.networkmanagement as PlasmaNM

Rectangle {
    id: flyout
    width: 360 * root.unit
    height: Math.min(content.height + 16 * root.unit, root.height * 0.7)
    radius: 8
    color: "#f9f9f9"
    border.color: Qt.rgba(0, 0, 0, 0.1)

    property string expanded: ""
    property string error: ""

    PlasmaNM.Handler {
        id: handler
        onConnectionActivationFailed: function(connectionPath, message) { flyout.error = message }
    }
    PlasmaNM.EnabledConnections { id: enabledConnections }
    PlasmaNM.NetworkModel { id: networkModel }
    PlasmaNM.AppletProxyModel { id: proxyModel; sourceModel: networkModel }

    Component.onCompleted: {
        // Networks joined here are saved for every account on the PC, as in Windows.
        PlasmaNM.Configuration.systemConnectionsByDefault = true
        handler.requestScan()
    }
    Timer { interval: 10000; repeat: true; running: flyout.visible; onTriggered: handler.requestScan() }

    function signalIcon(strength) {
        return strength >= 75 ? "wifi_1" : strength >= 50 ? "wifi_2" : strength >= 25 ? "wifi_3" : "wifi_4"
    }

    Column {
        id: content
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 8 * root.unit
        spacing: 4 * root.unit

        Item {
            width: parent.width
            height: 40 * root.unit
            Text {
                anchors.left: parent.left
                anchors.leftMargin: 8 * root.unit
                anchors.verticalCenter: parent.verticalCenter
                text: "Wi-Fi"
                color: "#1a1a1a"
                font.family: root.fontFamily
                font.weight: Font.DemiBold
                font.pixelSize: 15 * root.unit
            }
            Rectangle {
                id: wifiSwitch
                visible: enabledConnections.wirelessHwEnabled
                anchors.right: parent.right
                anchors.rightMargin: 8 * root.unit
                anchors.verticalCenter: parent.verticalCenter
                width: 40 * root.unit; height: 20 * root.unit; radius: height / 2
                color: enabledConnections.wirelessEnabled ? "#0067c0" : "transparent"
                border.color: enabledConnections.wirelessEnabled ? "#0067c0" : "#5f5f5f"
                Rectangle {
                    width: 12 * root.unit; height: width; radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    x: enabledConnections.wirelessEnabled ? parent.width - width - 4 * root.unit : 4 * root.unit
                    color: enabledConnections.wirelessEnabled ? "white" : "#5f5f5f"
                    Behavior on x { NumberAnimation { duration: 120 } }
                }
                MouseArea { anchors.fill: parent; onClicked: handler.enableWireless(!enabledConnections.wirelessEnabled) }
            }
        }

        ListView {
            id: list
            width: parent.width
            height: Math.min(contentHeight, root.height * 0.7 - 120 * root.unit)
            clip: true
            model: proxyModel
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            delegate: Rectangle {
                id: row
                readonly property bool open: flyout.expanded === model.ItemUniqueName
                readonly property bool wired: model.Type === PlasmaNM.Enums.Wired
                readonly property bool connected: model.ConnectionState === PlasmaNM.Enums.Activated
                readonly property bool connecting: model.ConnectionState === PlasmaNM.Enums.Activating
                readonly property bool secured: model.SecurityType > PlasmaNM.Enums.NoneSecurity
                readonly property bool saved: model.ConnectionPath !== ""
                width: list.width
                height: rowContent.height + 16 * root.unit
                radius: 4
                color: open ? "#ebebeb" : (rowArea.containsMouse ? "#f0f0f0" : "transparent")

                MouseArea {
                    id: rowArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        flyout.error = ""
                        flyout.expanded = row.open ? "" : model.ItemUniqueName
                    }
                }

                Column {
                    id: rowContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8 * root.unit
                    spacing: 10 * root.unit

                    Row {
                        spacing: 12 * root.unit
                        Image {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20 * root.unit; height: width
                            sourceSize: Qt.size(40, 40)
                            source: "icons/" + (row.wired ? "plug_connected" : flyout.signalIcon(model.Signal)) + "-dark.svg"
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                text: row.wired ? "Ethernet" : model.Name
                                color: "#1a1a1a"
                                font.family: root.fontFamily
                                font.pixelSize: 14 * root.unit
                            }
                            Text {
                                text: row.connected ? (row.secured ? "Connected, secured" : "Connected")
                                    : row.connecting ? "Connecting…"
                                    : row.wired ? "Not connected"
                                    : row.secured ? "Secured" : "Open"
                                color: "#5f5f5f"
                                font.family: root.fontFamily
                                font.pixelSize: 12 * root.unit
                            }
                        }
                    }

                    // Password box, for a secured network that isn't saved yet.
                    Rectangle {
                        id: keyBox
                        visible: row.open && !row.connected && !row.saved && row.secured
                        width: parent.width
                        height: 32 * root.unit
                        radius: 4
                        color: "white"
                        border.color: Qt.rgba(0, 0, 0, 0.15)
                        onVisibleChanged: if (visible) key.forceActiveFocus()
                        Rectangle {
                            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                            anchors.margins: 1
                            height: key.activeFocus ? 2 : 1
                            color: key.activeFocus ? "#0067c0" : Qt.rgba(0, 0, 0, 0.45)
                        }
                        TextInput {
                            id: key
                            anchors.fill: parent
                            anchors.leftMargin: 10 * root.unit
                            anchors.rightMargin: 10 * root.unit
                            verticalAlignment: TextInput.AlignVCenter
                            echoMode: TextInput.Password
                            passwordCharacter: "\u25CF"
                            color: "#1a1a1a"
                            font.family: root.fontFamily
                            font.pixelSize: 14 * root.unit
                            clip: true
                            Keys.onReturnPressed: actionButton.trigger()
                            Keys.onEnterPressed: actionButton.trigger()
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: !parent.text
                                text: "Enter the network security key"
                                color: "#5f5f5f"
                                font: parent.font
                            }
                        }
                    }

                    Text {
                        visible: row.open && flyout.error !== ""
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Can't connect to this network. " + flyout.error
                        color: "#c42b1c"
                        font.family: root.fontFamily
                        font.pixelSize: 12 * root.unit
                    }

                    Item {
                        visible: row.open && !(row.wired && !row.connected)
                        width: parent.width
                        height: 32 * root.unit
                        Rectangle {
                            id: actionButton
                            anchors.right: parent.right
                            width: 120 * root.unit
                            height: parent.height
                            radius: 4
                            color: row.connected ? (actionArea.containsMouse ? "#f6f6f6" : "#fbfbfb")
                                                 : (actionArea.containsMouse ? "#1975c5" : "#0067c0")
                            border.color: row.connected ? Qt.rgba(0, 0, 0, 0.12) : "transparent"
                            function trigger() {
                                flyout.error = ""
                                if (row.connected)
                                    handler.deactivateConnection(model.ConnectionPath, model.DevicePath)
                                else if (row.saved)
                                    handler.activateConnection(model.ConnectionPath, model.DevicePath, model.SpecificPath)
                                else
                                    handler.addAndActivateConnection(model.DevicePath, model.SpecificPath, key.text)
                                key.text = ""
                            }
                            Text {
                                anchors.centerIn: parent
                                text: row.connected ? "Disconnect" : keyBox.visible ? "Next" : "Connect"
                                color: row.connected ? "#1a1a1a" : "white"
                                font.family: root.fontFamily
                                font.pixelSize: 14 * root.unit
                            }
                            MouseArea { id: actionArea; anchors.fill: parent; hoverEnabled: true; onClicked: actionButton.trigger() }
                        }
                    }
                }
            }
        }

        Text {
            visible: list.count === 0
            width: parent.width
            topPadding: 8 * root.unit
            bottomPadding: 12 * root.unit
            horizontalAlignment: Text.AlignHCenter
            text: enabledConnections.wirelessEnabled || !enabledConnections.wirelessHwEnabled
                ? "No networks found" : "Wi-Fi is turned off"
            color: "#5f5f5f"
            font.family: root.fontFamily
            font.pixelSize: 13 * root.unit
        }
    }
}
