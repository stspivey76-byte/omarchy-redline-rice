import QtQuick
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "steven.workspaces"
  readonly property var ids: {
    var result = []
    var workspaces = Hyprland.workspaces.values
    for (var i = 0; i < workspaces.length; i++) {
      var workspace = workspaces[i]
      var focused = Hyprland.focusedWorkspace && Hyprland.focusedWorkspace.id === workspace.id
      if (workspace.id > 0 && (workspace.toplevels.values.length > 0 || workspace.active || focused) && result.indexOf(workspace.id) < 0) result.push(workspace.id)
    }
    return result.sort(function(a,b) { return a-b })
  }
  implicitWidth: row.implicitWidth + 12
  implicitHeight: barSize
  Row {
    id: row
    anchors.centerIn: parent
    spacing: 5
    Repeater {
      model: root.ids
      delegate: Item {
        required property int modelData
        readonly property bool focused: Hyprland.focusedWorkspace && Hyprland.focusedWorkspace.id === modelData
        readonly property bool occupied: {
          var workspaces = Hyprland.workspaces.values
          for (var i = 0; i < workspaces.length; i++) {
            if (workspaces[i].id === modelData)
              return workspaces[i].toplevels.values.length > 0
          }
          return false
        }
        width: focused ? 20 : 12
        height: root.barSize
        Behavior on width { NumberAnimation { duration: 150 } }
        // Soft orange halo around the active pill.
        Rectangle {
          anchors.centerIn: parent
          width: parent.width + 8
          height: 17
          radius: height / 2
          color: "#ff1f40"
          opacity: parent.focused ? 0.14 : 0
          Behavior on opacity { NumberAnimation { duration: 150 } }
        }
        Rectangle {
          anchors.centerIn: parent
          width: parent.width + 4
          height: 13
          radius: height / 2
          color: "#ff2f4d"
          opacity: parent.focused ? 0.3 : 0
          Behavior on opacity { NumberAnimation { duration: 150 } }
        }
        Rectangle {
          anchors.centerIn: parent
          width: parent.width
          height: 9
          radius: height / 2
          color: parent.focused ? "#ff2f4d" : parent.occupied ? "#ea6c7e" : "#701d29"
          opacity: 1
          Behavior on color { ColorAnimation { duration: 150 } }
        }
        MouseArea {
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: if (root.bar) root.bar.run("hyprctl dispatch " + Util.shellQuote('hl.dsp.focus({ workspace = "' + modelData + '" })'))
          onEntered: if (root.bar) root.bar.showTooltip(root, "Workspace " + modelData)
          onExited: if (root.bar) root.bar.hideTooltip(root)
        }
      }
    }
  }
}
