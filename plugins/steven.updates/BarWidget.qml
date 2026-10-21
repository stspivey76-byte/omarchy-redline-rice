import QtQuick
import Quickshell.Io
import qs.Ui

BarWidget {
  id: root
  moduleName: "steven.updates"
  property int count: 0
  property int errors: 0
  property bool checked: false
  property string details: "Checking for software updates…"
  visible: count > 0
  implicitWidth: visible ? button.implicitWidth : 0
  implicitHeight: visible ? button.implicitHeight : 0

  function refresh() {
    if (!checker.running) checker.running = true
  }

  Process {
    id: checker
    command: ["python3", Qt.resolvedUrl("check.py").toString().replace("file://", "")]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var data = JSON.parse(text)
          root.count = data.count
          root.errors = data.errors
          root.details = data.tooltip
          root.checked = true
        } catch (error) {
          root.errors = 1
          root.details = "Update check failed. Right click to retry."
        }
      }
    }
  }

  Timer {
    interval: 1800000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf021 " + (checker.running && !root.checked ? "…" : root.count) + (root.errors ? " !" : "")
    active: root.count > 0 || root.errors > 0
    tooltipText: root.details + (checker.running && root.checked ? "\nRefreshing…" : "")
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton && root.bar)
        root.bar.run("omarchy-launch-floating-terminal-with-presentation omarchy-update")
      else root.refresh()
    }
  }
}
