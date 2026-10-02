// Glass Panes lock screen (Win+L, after the screen turns off): the clock over the wallpaper, then
// (any key or click) the blurred sign-in view with the avatar and password box, like Windows 11.
// Replaces the Plasma shell's LockScreen.qml (see hooks/30-apps.sh); the greeter draws the
// wallpaper underneath and provides `authenticator`, `kscreenlocker_userName`/`_userImage`.
import QtQuick
import QtQuick.Effects

Item {
    id: root

    // Properties and signals kscreenlocker looks for.
    property bool viewVisible: false
    property bool suspendToRamSupported: false
    property bool suspendToDiskSupported: false
    property string notification
    signal suspendToDisk()
    signal suspendToRam()
    signal clearPassword()
    signal notificationRepeated()

    implicitWidth: 800
    implicitHeight: 600

    readonly property string themeDir: "file:///usr/share/sddm/themes/glasspanes/"
    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    property bool signingIn: false
    property bool busy: false
    property string message: ""
    property string fontFamily: "Selawik"
    property real unit: Math.max(0.75, Math.min(height / 1080, width / 1920))

    function showSignIn() {
        if (!signingIn) {
            signingIn = true
            authenticator.startAuthenticating()
        }
        password.forceActiveFocus()
        idle.restart()
    }

    function submit() {
        if (busy || message !== "")
            return
        busy = true
        authenticator.respond(password.text)
    }

    onClearPassword: password.text = ""

    Connections {
        target: authenticator
        function onFailed(kind) {
            if (kind !== 0)  // fingerprint/smartcard readers, not the password
                return
            root.busy = false
            password.text = ""
            root.message = "The password is incorrect. Try again."
            root.forceActiveFocus()
            shake.start()
            restartAuth.restart()
        }
        function onSucceeded() {
            Qt.quit()
        }
        function onPromptForSecretChanged() {
            root.busy = false
            if (root.signingIn && root.message === "")
                password.forceActiveFocus()
            else
                root.forceActiveFocus()
        }
    }

    // A failed attempt ends the PAM conversation; start a new one for the next password.
    Timer {
        id: restartAuth
        interval: 500
        onTriggered: authenticator.startAuthenticating()
    }

    // Back to the clock after a while without input, like Windows.
    Timer {
        id: idle
        interval: 30000
        onTriggered: if (password.text === "" && root.message === "") root.signingIn = false
    }

    // Dim, then blur the wallpaper for the sign-in view.
    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: root.signingIn ? 0.25 : 0.08
        Behavior on opacity { NumberAnimation { duration: 350 } }
    }
    Loader {
        anchors.fill: parent
        active: !root.software && typeof wallpaper !== "undefined" && wallpaper !== null
        opacity: root.signingIn ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }
        sourceComponent: MultiEffect {
            source: ShaderEffectSource { sourceItem: wallpaper; hideSource: false }
            blurEnabled: true
            blur: 1.0
            blurMax: 64
            brightness: -0.05
        }
    }

    Timer {
        interval: 1000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: {
            var now = new Date()
            // 12-hour without am/pm, as Windows shows it (Qt's "h" is 24-hour unless "AP" is present).
            clock.text = Qt.formatTime(now, "h:mm AP").replace(/\s*\D+$/, "")
            date.text = Qt.formatDate(now, "dddd, d MMMM")
        }
    }

    // ---- lock view -----------------------------------------------------------------------------
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.signingIn ? -height : parent.height * 0.12
        opacity: root.signingIn ? 0 : 1
        Behavior on y { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 300 } }
        Text {
            id: clock
            anchors.horizontalCenter: parent.horizontalCenter
            color: "white"
            font.family: root.fontFamily
            font.weight: Font.DemiBold
            font.pixelSize: 128 * root.unit
        }
        Text {
            id: date
            anchors.horizontalCenter: parent.horizontalCenter
            color: "white"
            font.family: root.fontFamily
            font.pixelSize: 26 * root.unit
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.showSignIn()
        onPositionChanged: if (root.signingIn) idle.restart()
        hoverEnabled: true
    }

    // ---- sign-in view ----------------------------------------------------------------------------
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: root.signingIn ? -40 * root.unit : 60 * root.unit
        opacity: root.signingIn ? 1 : 0
        visible: root.signingIn || opacity > 0  // visible at once, so the password box can take focus
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
                source: kscreenlocker_userImage ? "file://" + kscreenlocker_userImage : root.themeDir + "user.png"
                onStatusChanged: {
                    if (status === Image.Error)
                        source = root.themeDir + "user.png"
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
            text: kscreenlocker_userName
            color: "white"
            font.family: root.fontFamily
            font.weight: Font.DemiBold
            font.pixelSize: 28 * root.unit
        }

        Item {
            id: passwordRow
            anchors.horizontalCenter: parent.horizontalCenter
            width: 296 * root.unit
            height: 36 * root.unit
            visible: root.message === "" && !root.busy
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
                anchors.right: submitButton.left
                anchors.leftMargin: 11 * root.unit
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                echoMode: reveal.pressed ? TextInput.Normal : TextInput.Password
                passwordCharacter: "\u25CF"
                color: "#1a1a1a"
                font.family: root.fontFamily
                font.pixelSize: 15 * root.unit
                clip: true
                onTextChanged: idle.restart()
                Keys.onReturnPressed: root.submit()
                Keys.onEnterPressed: root.submit()
                Keys.onEscapePressed: { text = ""; root.signingIn = false }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !parent.text
                    text: "Password"
                    color: "#5f5f5f"
                    font: parent.font
                }
            }
            Image {
                anchors.right: submitButton.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: 4
                visible: password.text.length > 0
                width: 16 * root.unit; height: width
                source: root.themeDir + "icons/eye-dark.svg"
                sourceSize: Qt.size(32, 32)
                MouseArea { id: reveal; anchors.fill: parent; anchors.margins: -6 }
            }
            Rectangle {
                id: submitButton
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
                    source: root.themeDir + "icons/arrow_right-dark.svg"
                    sourceSize: Qt.size(32, 32)
                }
                MouseArea { id: submitArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.submit() }
            }
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.message !== ""
            spacing: 18 * root.unit
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.message
                color: "white"
                font.family: root.fontFamily
                font.pixelSize: 15 * root.unit
            }
            Rectangle {
                id: okButton
                anchors.horizontalCenter: parent.horizontalCenter
                width: 296 * root.unit
                height: 34 * root.unit
                radius: 4
                color: okArea.containsMouse ? Qt.rgba(1, 1, 1, 0.3) : Qt.rgba(1, 1, 1, 0.2)
                border.color: Qt.rgba(1, 1, 1, 0.3)
                Text { anchors.centerIn: parent; text: "OK"; color: "white"; font.family: root.fontFamily; font.pixelSize: 15 * root.unit }
                MouseArea {
                    id: okArea; anchors.fill: parent; hoverEnabled: true
                    onClicked: { root.message = ""; password.forceActiveFocus() }
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.busy
            text: "Welcome"
            color: "white"
            font.family: root.fontFamily
            font.pixelSize: 20 * root.unit
        }
    }

    // ---- sleep (bottom right) -------------------------------------------------------------------
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 24 * root.unit
        width: 40 * root.unit; height: width; radius: 4
        visible: root.signingIn && root.suspendToRamSupported
        color: sleepArea.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : "transparent"
        Image {
            anchors.centerIn: parent
            width: 20 * root.unit; height: width
            source: root.themeDir + "icons/power.svg"
            sourceSize: Qt.size(40, 40)
        }
        MouseArea { id: sleepArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.suspendToRam() }
    }

    focus: true
    Keys.onPressed: function(event) {
        if (root.message !== "" && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
            root.message = ""
            password.forceActiveFocus()
            event.accepted = true
            return
        }
        if (!root.signingIn) {
            if (event.key === Qt.Key_Escape)
                return  // kscreenlocker turns the screen off
            root.showSignIn()
            if (event.text.length > 0 && event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter
                    && event.key !== Qt.Key_Space)
                password.text = event.text
            event.accepted = true
        }
    }
    Component.onCompleted: forceActiveFocus()
}
