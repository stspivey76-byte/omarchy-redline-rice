import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "steven.active-window"


  readonly property var toplevel: ToplevelManager.activeToplevel
  readonly property string title: {
    if (!toplevel) return ""
    const appId = toplevel.appId || ""
    // Cliamp runs in a terminal and puts the current song in its window title.
    if (/(?:^|\|\s*)cliamp\s*$/i.test(toplevel.title || "")) return "Cliamp"
    // Chromium webapps identify themselves with their site in the app id.
    const webAppId = appId.replace(/^(?:brave|chromium|google-chrome|chrome|microsoft-edge)-/i, "")
    if (/^192\.168\.1\.80(?::8096)?(?:__|$)/i.test(webAppId)) return "Emby"
    if (/^discord\.com(?:__|$)/i.test(webAppId)) return "Discord"
    if (/^(?:www\.)?youtube\.com(?:__|$)/i.test(webAppId)) return "YouTube"
    if (/^music\.amazon\.com(?:__|$)/i.test(webAppId)) return "Amazon Music"
    // Other webapps still show their site name, never the current page title.
    const site = webAppId.match(/^(?:www\.)?([^_]+)__/)
    if (site) {
      const name = site[1].split(".").slice(0, -1).join(" ")
      return name.charAt(0).toUpperCase() + name.slice(1)
    }
    const entries = DesktopEntries.applications.values || []
    const normalizedId = appId.toLowerCase().replace(/\.desktop$/, "")
    for (const entry of entries) {
      if (String(entry.id || "").toLowerCase().replace(/\.desktop$/, "") === normalizedId)
        return entry.name || appId
    }
    // Give unmatched app IDs a readable name without using the window title.
    const name = appId.split(".").pop().replace(/[-_]/g, " ")
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : ""
  }
  readonly property int maxLabelWidth: Number(setting("maxWidth", 280))

  visible: title !== "" && !vertical
  implicitWidth: visible ? Math.min(maxLabelWidth, labelText.implicitWidth) + Style.spacing.controlPaddingX * 2 : 0
  implicitHeight: barSize

  Behavior on implicitWidth {
    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
  }

  Item {
    anchors.fill: parent
    anchors.leftMargin: Style.space(8)
    anchors.rightMargin: Style.space(8)
    clip: true

    Text {
      id: labelText
      textFormat: Text.PlainText
      anchors.verticalCenter: parent.verticalCenter
      anchors.left: parent.left
      width: parent.width
      text: root.title
      color: root.bar ? root.bar.barForeground : Color.foreground
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
      opacity: 0.85
    }
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
    cursorShape: Qt.PointingHandCursor

    onClicked: function(mouse) {
      if (!root.toplevel) return
      if (mouse.button === Qt.MiddleButton) {
        root.toplevel.close()
      } else if (mouse.button === Qt.RightButton) {
        root.toplevel.close()
      } else {
        root.toplevel.activate()
      }
    }
    onEntered: if (root.bar) root.bar.showTooltip(root, root.title)
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }
}
