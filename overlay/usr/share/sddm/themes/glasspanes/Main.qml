// Glass Panes sign-in screen: a lock screen with the clock, then (any key or click) the blurred
// sign-in view with the avatar and password box, like Windows 11.
import QtQuick

Item {
    id: root
    width: 1920
    height: 1080

    property bool signingIn: false
    property string message: ""
    property int sessionIndex: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0
    property color textColor: "white"
    property string fontFamily: config.font || "Selawik"
    property real unit: Math.max(0.75, Math.min(height / 1080, width / 1920))

    function showSignIn() {
        if (!signingIn) {
            signingIn = true
            password.forceActiveFocus()
        }
    }

    function login() {
        if (!users.currentItem)
            return
        message = ""
        busy.running = true
        sddm.login(users.currentItem.userName, password.text, sessionIndex)
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            busy.running = false
            password.text = ""
            root.message = "The password is incorrect. Try again."
            shake.start()
        }
        function onLoginSucceeded() {
            busy.running = false
        }
    }

    Image {
        anchors.fill: parent
        source: config.background
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
    }
    Image {
        anchors.fill: parent
        source: config.backgroundBlur
        fillMode: Image.PreserveAspectCrop
        opacity: root.signingIn ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }
    }

    Timer {
        interval: 1000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: {
            var now = new Date()
            clock.text = Qt.formatTime(now, "h:mm")
            date.text = Qt.formatDate(now, "dddd, d MMMM")
        }
    }

    // ---- lock screen ---------------------------------------------------------------------------
    Column {
        id: lockView
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.signingIn ? -height : parent.height * 0.12
        opacity: root.signingIn ? 0 : 1
        spacing: 0
        Behavior on y { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 300 } }
        Text {
            id: clock
            anchors.horizontalCenter: parent.horizontalCenter
            color: root.textColor
            font.family: root.fontFamily
            font.weight: Font.DemiBold
            font.pixelSize: 128 * root.unit
        }
        Text {
            id: date
            anchors.horizontalCenter: parent.horizontalCenter
            color: root.textColor
            font.family: root.fontFamily
            font.pixelSize: 26 * root.unit
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: !root.signingIn
        onClicked: root.showSignIn()
    }

    // ---- sign in ---------------------------------------------------------------------------------
    Column {
        id: signInView
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: root.signingIn ? -40 * root.unit : 60 * root.unit
        opacity: root.signingIn ? 1 : 0
        visible: opacity > 0
        spacing: 18 * root.unit
        Behavior on opacity { NumberAnimation { duration: 300 } }
        Behavior on anchors.verticalCenterOffset { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }

        // Canvas clipping works with every Qt Quick renderer, including software (VMs, safe graphics).
        Canvas {
            id: avatar
            anchors.horizontalCenter: parent.horizontalCenter
            width: 192 * root.unit
            height: width
            property string picture: ""
            Image {
                id: face
                visible: false
                source: users.currentItem ? users.currentItem.userIcon : ""
                onStatusChanged: {
                    if (status === Image.Error)
                        source = Qt.resolvedUrl("user.png")
                    else if (status === Image.Ready) {
                        avatar.picture = source.toString()
                        avatar.loadImage(avatar.picture)
                        avatar.requestPaint()
                    }
                }
            }
            onImageLoaded: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                if (!picture || !isImageLoaded(picture))
                    return
                var w = face.implicitWidth, h = face.implicitHeight, s = Math.min(w, h)
                ctx.save()
                ctx.beginPath()
                ctx.arc(width / 2, height / 2, width / 2, 0, 2 * Math.PI)
                ctx.closePath()
                ctx.clip()
                ctx.drawImage(picture, (w - s) / 2, (h - s) / 2, s, s, 0, 0, width, height)
                ctx.restore()
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: users.currentItem ? users.currentItem.displayName : ""
            color: root.textColor
            font.family: root.fontFamily
            font.weight: Font.DemiBold
            font.pixelSize: 28 * root.unit
        }

        Item {
            id: passwordRow
            anchors.horizontalCenter: parent.horizontalCenter
            width: 296 * root.unit
            height: 36 * root.unit
            visible: root.message === ""
            SequentialAnimation {
                id: shake
                loops: 2
                NumberAnimation { target: passwordRow; property: "anchors.horizontalCenterOffset"; to: -12; duration: 50 }
                NumberAnimation { target: passwordRow; property: "anchors.horizontalCenterOffset"; to: 12; duration: 100 }
                NumberAnimation { target: passwordRow; property: "anchors.horizontalCenterOffset"; to: 0; duration: 50 }
            }
            Rectangle {
                anchors.fill: parent
                radius: 4
                color: password.activeFocus ? Qt.rgba(1, 1, 1, 0.95) : Qt.rgba(1, 1, 1, 0.7)
                border.color: Qt.rgba(0, 0, 0, 0.1)
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 1
                    height: password.activeFocus ? 2 : 1
                    color: password.activeFocus ? "#0067c0" : Qt.rgba(0, 0, 0, 0.45)
                }
            }
            TextInput {
                id: password
                anchors.left: parent.left
                anchors.right: submit.left
                anchors.leftMargin: 11 * root.unit
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                echoMode: reveal.pressed ? TextInput.Normal : TextInput.Password
                passwordCharacter: "\u25CF"
                color: "#1a1a1a"
                font.family: root.fontFamily
                font.pixelSize: 15 * root.unit
                clip: true
                focus: root.signingIn
                Keys.onReturnPressed: root.login()
                Keys.onEnterPressed: root.login()
                Keys.onEscapePressed: { root.signingIn = false; text = "" }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !parent.text
                    text: keyboard.capsLock ? "Password (Caps Lock is on)" : "Password"
                    color: "#5f5f5f"
                    font: parent.font
                }
            }
            Image {
                id: revealIcon
                anchors.right: submit.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: 4
                visible: password.text.length > 0
                width: 16 * root.unit; height: width
                source: "icons/eye-dark.svg"
                sourceSize: Qt.size(32, 32)
                MouseArea { id: reveal; anchors.fill: parent; anchors.margins: -6 }
            }
            Rectangle {
                id: submit
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: 3
                width: height
                radius: 3
                color: submitArea.containsMouse ? "#e6e6e6" : "transparent"
                Image {
                    anchors.centerIn: parent
                    width: 16 * root.unit; height: width
                    source: "icons/arrow_right-dark.svg"
                    sourceSize: Qt.size(32, 32)
                }
                MouseArea { id: submitArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.login() }
            }
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.message !== ""
            spacing: 18 * root.unit
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.message
                color: root.textColor
                font.family: root.fontFamily
                font.pixelSize: 15 * root.unit
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 296 * root.unit
                height: 34 * root.unit
                radius: 4
                color: okArea.containsMouse ? Qt.rgba(1, 1, 1, 0.3) : Qt.rgba(1, 1, 1, 0.2)
                border.color: Qt.rgba(1, 1, 1, 0.3)
                Text { anchors.centerIn: parent; text: "OK"; color: root.textColor; font.family: root.fontFamily; font.pixelSize: 15 * root.unit }
                MouseArea {
                    id: okArea; anchors.fill: parent; hoverEnabled: true
                    onClicked: { root.message = ""; password.forceActiveFocus() }
                }
            }
            Keys.onReturnPressed: { root.message = ""; password.forceActiveFocus() }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: busy.running
            text: "Welcome"
            color: root.textColor
            font.family: root.fontFamily
            font.pixelSize: 20 * root.unit
            Timer { id: busy; interval: 30000 }
        }
    }

    // ---- other users (bottom left) ---------------------------------------------------------------
    ListView {
        id: users
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 24 * root.unit
        width: 280 * root.unit
        height: Math.min(contentHeight, parent.height * 0.4)
        model: userModel
        currentIndex: userModel.lastIndex >= 0 ? userModel.lastIndex : 0
        opacity: root.signingIn && count > 1 ? 1 : 0
        visible: opacity > 0
        interactive: false
        spacing: 2
        Behavior on opacity { NumberAnimation { duration: 300 } }
        delegate: Rectangle {
            property string userName: model.name
            property string displayName: model.realName || model.name
            property url userIcon: model.icon
            width: users.width
            height: 52 * root.unit
            radius: 4
            color: ListView.isCurrentItem ? Qt.rgba(1, 1, 1, 0.25) : (rowArea.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent")
            Row {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 10
                spacing: 12
                Image {
                    width: 32 * root.unit; height: width
                    source: model.icon
                    sourceSize.width: 64
                    fillMode: Image.PreserveAspectCrop
                    onStatusChanged: if (status === Image.Error) source = "user.png"
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.realName || model.name
                    color: root.textColor
                    font.family: root.fontFamily
                    font.pixelSize: 15 * root.unit
                }
            }
            MouseArea {
                id: rowArea; anchors.fill: parent; hoverEnabled: true
                onClicked: { users.currentIndex = index; password.text = ""; root.message = ""; password.forceActiveFocus() }
            }
        }
    }

    // ---- network / accessibility / power (bottom right) --------------------------------------------
    Row {
        id: corner
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 24 * root.unit
        spacing: 8 * root.unit
        opacity: root.signingIn ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 300 } }
        Repeater {
            model: ["wifi", "accessibility", "power"]
            Rectangle {
                width: 40 * root.unit; height: width; radius: 4
                color: btnArea.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : "transparent"
                Image {
                    anchors.centerIn: parent
                    width: 20 * root.unit; height: width
                    source: "icons/" + modelData + ".svg"
                    sourceSize: Qt.size(40, 40)
                }
                MouseArea {
                    id: btnArea; anchors.fill: parent; hoverEnabled: true
                    onClicked: if (modelData === "power") powerMenu.visible = !powerMenu.visible
                }
            }
        }
    }

    Rectangle {
        id: powerMenu
        visible: false
        anchors.right: corner.right
        anchors.bottom: corner.top
        anchors.bottomMargin: 8
        width: 200 * root.unit
        height: menuCol.height + 8
        radius: 8
        color: "#f9f9f9"
        border.color: Qt.rgba(0, 0, 0, 0.1)
        Column {
            id: menuCol
            anchors.centerIn: parent
            width: parent.width - 8
            Repeater {
                model: [
                    { label: "Sleep", icon: "weather_moon", ok: sddm.canSuspend, act: function() { sddm.suspend() } },
                    { label: "Shut down", icon: "power", ok: sddm.canPowerOff, act: function() { sddm.powerOff() } },
                    { label: "Restart", icon: "arrow_clockwise", ok: sddm.canReboot, act: function() { sddm.reboot() } }
                ]
                Rectangle {
                    width: menuCol.width
                    height: 36 * root.unit
                    radius: 4
                    visible: modelData.ok
                    color: itemArea.containsMouse ? "#ebebeb" : "transparent"
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        spacing: 12
                        Image { width: 16 * root.unit; height: width; source: "icons/" + modelData.icon + "-dark.svg"; sourceSize: Qt.size(32, 32) }
                        Text { text: modelData.label; color: "#1a1a1a"; font.family: root.fontFamily; font.pixelSize: 14 * root.unit }
                    }
                    MouseArea { id: itemArea; anchors.fill: parent; hoverEnabled: true; onClicked: { powerMenu.visible = false; modelData.act() } }
                }
            }
        }
    }

    focus: true
    Keys.onPressed: function(event) {
        if (!root.signingIn) {
            root.showSignIn()
            if (event.text.length > 0 && event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter
                    && event.key !== Qt.Key_Space && event.key !== Qt.Key_Escape)
                password.text = event.text
            event.accepted = true
        }
    }
    Component.onCompleted: forceActiveFocus()
}
