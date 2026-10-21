import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "steven.spectrum"
  implicitWidth: vertical ? barSize : Style.space(108)
  implicitHeight: vertical ? Style.space(108) : barSize
  property var levels: Array(20).fill(0)

  Process {
    id: analyzer
    command: ["python3", decodeURIComponent(Qt.resolvedUrl("spectrum.py").toString().replace(/^file:\/\//, ""))]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        try { root.levels = JSON.parse(line); watchdog.restart() } catch (error) {}
      }
    }
    onExited: retry.restart()
  }
  Timer { id: retry; interval: 3000; onTriggered: analyzer.running = true }
  Timer { id: watchdog; interval: 600; onTriggered: root.levels = Array(20).fill(0) }

  Rectangle {
    id: display
    anchors.centerIn: parent
    width: root.vertical ? Style.space(22) : root.width - Style.space(8)
    height: root.vertical ? root.height - Style.space(8) : Math.min(Style.space(24), root.height - Style.space(6))
    color: root.bar && root.bar.transparent ? "transparent" : "#0c0709"

    Repeater {
      model: 20
      Item {
        id: band
        required property int index
        readonly property real level: Math.max(0, Math.min(1, root.levels[index] || 0))
        readonly property real shownLevel: Math.max(0.025, level)
        width: root.vertical ? display.width : display.width / 20 - Style.space(1)
        height: root.vertical ? display.height / 20 - Style.space(1) : display.height
        x: root.vertical ? 0 : index * display.width / 20
        y: root.vertical ? index * display.height / 20 : 0

        Item {
          id: fill
          width: root.vertical ? band.width * band.shownLevel : band.width
          height: root.vertical ? band.height : band.height * band.shownLevel
          y: root.vertical ? 0 : band.height - height
          clip: true
          Behavior on height { NumberAnimation { duration: 60 } }
          Behavior on width { NumberAnimation { duration: 60 } }

          Rectangle {
            anchors.fill: parent
            // Crimson eclipse: bright rim above deep red shadows.
            gradient: Gradient {
              GradientStop { position: 0.0; color: "#ffb09a" }
              GradientStop { position: 0.25; color: "#ff493b" }
              GradientStop { position: 0.65; color: "#d51b36" }
              GradientStop { position: 1.0; color: "#791525" }
            }
          }
        }
      }
    }
  }
}
