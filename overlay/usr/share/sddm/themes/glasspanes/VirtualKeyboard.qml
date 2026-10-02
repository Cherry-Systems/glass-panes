// On-screen keyboard for the sign-in screen (Accessibility > On-screen keyboard).
import QtQuick
import QtQuick.VirtualKeyboard

InputPanel {
    property bool activated: false
    active: activated && Qt.inputMethod.visible
    visible: active
}
