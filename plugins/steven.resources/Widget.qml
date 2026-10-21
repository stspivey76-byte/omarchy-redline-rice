import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "steven.resources"
  implicitWidth: vertical ? barSize : Style.space(52)
  implicitHeight: vertical ? Style.space(52) : barSize
  property var metrics: ({levels: [0, 0, 0], download: 0, upload: 0, rx: 0, tx: 0})

  function rate(value) {
    return value >= 1048576 ? (value / 1048576).toFixed(1) + " MiB/s" : (value / 1024).toFixed(1) + " KiB/s"
  }
  function tooltip() {
    return "CPU " + Math.round(metrics.levels[0] * 100) + "% · RAM " + Math.round(metrics.levels[1] * 100)
      + "% · Disk " + Math.round(metrics.levels[2] * 100) + "%\nNetwork ↓ " + rate(metrics.rx) + "  ↑ " + rate(metrics.tx)
  }

  Process {
    id: sampler
    command: ["python3", decodeURIComponent(Qt.resolvedUrl("metrics.py").toString().replace(/^file:\/\//, ""))]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        try { root.metrics = JSON.parse(line) } catch (error) {}
      }
    }
    onExited: retry.restart()
  }
  Timer { id: retry; interval: 3000; onTriggered: sampler.running = true }

  Item {
    id: display
    anchors.centerIn: parent
    width: root.vertical ? Style.space(22) : Style.space(44)
    height: root.vertical ? Style.space(44) : Math.min(Style.space(22), root.height - Style.space(6))
    Repeater {
      // Three usage meters, followed by download and upload in the fourth slot.
      model: 5
      Rectangle {
        id: track
        required property int index
        readonly property bool network: index >= 3
        readonly property real usage: Math.max(0, Math.min(1, network
          ? (index === 3 ? root.metrics.download : root.metrics.upload)
          : root.metrics.levels[index] || 0))
        readonly property real level: Math.max(0.04, usage)
        readonly property bool critical: !network && usage >= 0.95
        readonly property color energy: network ? "#FF8C42" : critical ? "#C1121F"
          : usage >= 0.8 ? "#FF453A" : usage >= 0.5 ? "#FFBF47" : "#FF8C42"
        readonly property real offset: index < 3 ? index * 12 : 36 + (index - 3) * 4
        width: root.vertical ? display.width : Style.space(network ? 3 : 7)
        height: root.vertical ? Style.space(network ? 3 : 7) : display.height
        x: root.vertical ? 0 : Style.space(offset)
        y: root.vertical ? Style.space(offset) : 0
        radius: Math.min(width, height) / 2
        color: "#321015"

        Rectangle {
          id: fill
          anchors.bottom: parent.bottom
          anchors.left: parent.left
          width: root.vertical ? parent.width * track.level : parent.width
          height: root.vertical ? parent.height : parent.height * track.level
          radius: Math.min(width, height) / 2
          color: track.energy
          Behavior on color { ColorAnimation { duration: 250 } }
          Behavior on height { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }
          Behavior on width { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }
          SequentialAnimation on opacity {
            running: track.critical
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.5; duration: 700; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.5; to: 1; duration: 700; easing.type: Easing.InOutSine }
            onRunningChanged: if (!running) fill.opacity = 1
          }
          // Simple translucent halo; no blur pass or extra sampling process.
          Rectangle {
            anchors.fill: parent
            anchors.margins: -Style.space(1)
            radius: Math.min(width, height) / 2
            color: track.energy
            opacity: track.usage > 0.01 ? 0.16 : 0
            z: -1
          }
        }
      }
    }
  }
  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltip())
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }
}
