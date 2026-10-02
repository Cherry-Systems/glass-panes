// Shown while the desktop loads after signing in: "Welcome" and the spinning dots, like Windows.
import QtQuick

Rectangle {
    id: root
    color: "#1b3a5c"
    property int stage

    Image {
        anchors.fill: parent
        source: "file:///usr/share/sddm/themes/glasspanes/background-blur.png"
        fillMode: Image.PreserveAspectCrop
    }

    Column {
        anchors.centerIn: parent
        spacing: 28

        Item {
            id: spinner
            anchors.horizontalCenter: parent.horizontalCenter
            width: 48
            height: 48
            property real t: 0
            NumberAnimation on t { from: 0; to: 1; duration: 2200; loops: Animation.Infinite; running: true }
            Repeater {
                model: 5
                Rectangle {
                    // Each dot lags the one before it and speeds up through the bottom of the circle.
                    property real p: Math.max(0, Math.min(1, (spinner.t * 1.35) - index * 0.07))
                    property real eased: p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
                    property real angle: (eased * 2 * Math.PI) - Math.PI / 2
                    width: 6
                    height: 6
                    radius: 3
                    color: "white"
                    opacity: p > 0 && p < 1 ? 1 : 0
                    x: spinner.width / 2 + Math.cos(angle) * 20 - 3
                    y: spinner.height / 2 + Math.sin(angle) * 20 - 3
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Welcome"
            color: "white"
            font.family: "Selawik"
            font.pixelSize: 30
        }
    }
}
