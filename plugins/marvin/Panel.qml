import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// The wake word listener, in the bar.
//
// Everything shown here is read from the state file the listener writes on
// every transition, rather than scraped out of the journal. The journal records
// what happened; this asks what is true now, and "which microphone is open" has
// exactly one answer at a time.
//
// Nothing here works out anything for itself. The glyph is a function of the
// state file, and each button shells out to the same command a person would
// type - so the bar and the terminal cannot drift into disagreeing.
Panel {
  id: root
  moduleName: "omarchy-voice.marvin"
  ipcTarget: "omarchy-voice.marvin"
  // The base class provides open/close/toggle on this target, which is what a
  // keybinding wants:
  //   omarchy-shell ipc call omarchy-voice.marvin toggle
  manageIpc: true

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // The bar sizes each slot from the widget's implicit size, so without these
  // the module loads, runs, and occupies nothing - present in the layout and
  // invisible on screen.
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // Deliberately no self-hiding. A module with nothing to say can reasonably
  // leave the bar, but this one's quietest state - not listening - is exactly
  // when you need somewhere to click to start it again.

  property var state: null
  property var sources: []
  property var sinks: []
  property string configuredOutput: ""
  property bool speaks: true

  readonly property bool listening: !!state && state.listening === true
  readonly property string openMic: state ? String(state.mic || "") : ""
  readonly property string configuredMic: state ? String(state.configured_mic || "") : ""
  // On a microphone other than the one asked for. Worth surfacing rather than
  // hiding: it is the difference between "not hearing you" and "hearing you on
  // the laptop lid".
  readonly property bool onFallback: !!state && state.on_fallback === true
  readonly property string agentName: state && state.name ? String(state.name) : "Marvin"

  // A node name means nothing to anyone; the description is what is on the box.
  function describe(node) {
    if (!node) return "a built-in microphone"
    for (var i = 0; i < sources.length; i++)
      if (sources[i].node === node) return String(sources[i].description)
    return node  // present in the config but not plugged in right now
  }

  function stateLine() {
    if (!state) return "not running"
    if (!listening) return "asleep"
    return onFallback ? "listening, on a fallback" : "listening"
  }

  FileView {
    // The listener rewrites this whole, so a read is either the old state or the
    // new one and never half of each.
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/omarchy-voice/state.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        root.state = JSON.parse(String(text() || ""))
      } catch (e) {
        root.state = null
      }
    }
    // Absent means the listener has never run this boot, which is a state worth
    // drawing rather than an error worth logging.
    onLoadFailed: root.state = null
  }

  // The device list is asked for, not watched: it only changes when hardware
  // comes and goes, and the panel is the only thing that needs it.
  Process {
    id: micList
    running: false
    command: ["omarchy-voice-audio", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var parsed = JSON.parse(String(text || "{}"))
          root.sources = parsed.sources || []
          root.sinks = parsed.sinks || []
          root.configuredOutput = String(parsed.configured_output || "")
          root.speaks = parsed.speak !== false
        } catch (e) {
          root.sources = []
          root.sinks = []
        }
      }
    }
  }

  Process {
    id: toggleListening
    running: false
    command: ["omarchy-voice-wake-toggle"]
  }

  Process {
    id: setDevice
    running: false
    command: []
    // The command may restart the listener, which rewrites the state file this
    // panel watches; re-reading the device list keeps the ticks honest.
    onExited: root.refresh()
  }

  function describeSink(node) {
    if (!node) return "the system default"
    for (var i = 0; i < sinks.length; i++)
      if (sinks[i].node === node) return String(sinks[i].description)
    return node
  }

  function refresh() {
    if (!micList.running) micList.running = true
  }

  function setSpeech(on) {
    setDevice.command = ["omarchy-voice-audio", "speech", on ? "on" : "off"]
    setDevice.running = true
  }

  function choose(what, node) {
    // The command writes the preference; for the microphone it also restarts the
    // listener, so the state file this panel watches updates itself a moment
    // later. The panel stays open, because picking a device is often two tries.
    setDevice.command = ["omarchy-voice-audio", what, node === "" ? "default" : node]
    setDevice.running = true
  }

  onOpenedChanged: if (opened) refresh()

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Not a microphone: Omarchy's own Microphone widget already draws exactly
    // that pair of glyphs, and two identical icons in one bar teach nobody
    // anything. A figure speaking is what this actually is, and the zeds are
    // what the code already calls the other state - asleep.
    text: root.listening ? "󰗋" : "󰒲"
    // Reserved for "listening, but not where you asked" - being deaf is obvious
    // from the crossed-out glyph, whereas this is the case you cannot see.
    active: root.listening && root.onFallback
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) toggleListening.running = true
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    // Tall enough that a machine with a few outputs shows every one without
    // scrolling: the whole point of the list is picking from it at a glance.
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(760))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent

      // Deliberately not wired to the listening toggle. A stray Enter reaching a
      // focused panel should not be able to switch the assistant off, and this
      // one is opened by a keybinding, so stray Enters are not hypothetical.
      onActivateRequested: root.refresh()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "r" || t === "R") root.refresh() }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(9)

          PanelHero {
            width: parent.width
            title: root.agentName
            meta: root.stateLine()
            detail: root.listening ? root.describe(root.openMic) : "say nothing; it is not listening"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          PanelSeparator {
            width: parent.width
            foreground: root.foreground
          }

          // ---------- Listening ----------
          Row {
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: parent.width - toggle.width - Style.space(10)
              text: root.listening
                    ? "Stop listening. Frees the microphone entirely."
                    : "Start listening for “Hey " + root.agentName + "”."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
            }

            PanelActionButton {
              id: toggle
              iconText: root.listening ? "󰒲" : "󰗋"
              tooltipText: root.listening ? "Stop listening" : "Start listening"
              foreground: root.foreground
              fontFamily: root.fontFamily
              bordered: true
              onClicked: {
                toggleListening.running = true
                root.close()
              }
            }
          }

          PanelSeparator {
            width: parent.width
            foreground: root.foreground
          }

          // ---------- Microphone ----------
          PanelSectionHeader {
            width: parent.width
            text: "MICROPHONE"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Text {
            width: parent.width
            visible: root.onFallback
            // Says which way round it is, because "on a fallback" alone does not
            // tell you whether to go and switch a headset on.
            text: "Asked for " + root.describe(root.configuredMic) + ", using "
                  + root.describe(root.openMic)
                  + (root.state && root.state.fallback_reason
                     ? " (" + root.state.fallback_reason + ")" : "")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
          }

          Repeater {
            model: root.sources

            Rectangle {
              width: column.width
              height: Style.space(28)
              radius: Style.space(6)
              color: mouse.containsMouse ? Qt.rgba(root.foreground.r, root.foreground.g,
                                                   root.foreground.b, 0.10) : "transparent"

              Row {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Style.space(8)
                spacing: Style.space(8)

                Text {
                  // Ticked when it is the one actually open, not merely the one
                  // configured: this list answers "what am I hearing you on".
                  text: modelData.node === root.openMic ? "󰄬"
                        : modelData.bluetooth ? "󰂯" : "󰍬"
                  color: modelData.node === root.openMic ? root.foreground : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.icon
                }

                Text {
                  text: String(modelData.description)
                  color: modelData.node === root.openMic ? root.foreground : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  width: column.width - Style.space(50)
                }
              }

              MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.choose("mic", String(modelData.node))
              }
            }
          }

          PanelSeparator {
            width: parent.width
            foreground: root.foreground
          }

          // ---------- Speech ----------
          Row {
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: parent.width - speechToggle.width - Style.space(10)
              // A separate switch from listening on purpose: not wanting to be
              // spoken to is not the same as not wanting to be heard.
              text: root.speaks
                    ? "Answers are spoken. Turn off to read them instead."
                    : "Answers are written only - the notification still appears."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
            }

            PanelActionButton {
              id: speechToggle
              iconText: root.speaks ? "󰕿" : "󰝟"
              tooltipText: root.speaks ? "Stop speaking answers" : "Speak answers again"
              foreground: root.foreground
              fontFamily: root.fontFamily
              bordered: true
              onClicked: root.setSpeech(!root.speaks)
            }
          }

          // ---------- Speaker ----------
          PanelSectionHeader {
            width: parent.width
            text: "SPEAKER"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Text {
            width: parent.width
            // Says what "default" resolves to rather than leaving it abstract:
            // following the system default is the usual right answer, and the
            // only way to know it is right is to see what it currently means.
            text: root.speaks
                  ? "Answering through " + root.describeSink(root.configuredOutput) + "."
                  : "Speech is off, so nothing is played. This is what it would use."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
          }

          Repeater {
            model: root.sinks

            Rectangle {
              width: column.width
              height: Style.space(28)
              radius: Style.space(6)
              color: sinkMouse.containsMouse ? Qt.rgba(root.foreground.r, root.foreground.g,
                                                       root.foreground.b, 0.10) : "transparent"

              Row {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Style.space(8)
                spacing: Style.space(8)

                Text {
                  // Ticked on the configured sink, not an open one: unlike the
                  // microphone there is no stream held open to ask, because the
                  // speaker is chosen fresh for each thing it says.
                  text: modelData.node === root.configuredOutput ? "󰄬"
                        : modelData.bluetooth ? "󰂯" : "󰓃"
                  color: modelData.node === root.configuredOutput ? root.foreground : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.icon
                }

                Text {
                  text: String(modelData.description)
                  color: modelData.node === root.configuredOutput ? root.foreground : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  width: column.width - Style.space(50)
                }
              }

              MouseArea {
                id: sinkMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.choose("output", String(modelData.node))
              }
            }
          }

          Rectangle {
            width: column.width
            height: Style.space(28)
            radius: Style.space(6)
            color: defMouse.containsMouse ? Qt.rgba(root.foreground.r, root.foreground.g,
                                                    root.foreground.b, 0.10) : "transparent"
            Text {
              anchors.verticalCenter: parent.verticalCenter
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              text: (root.configuredOutput === "" ? "󰄬  " : "󰕺  ") + "Follow the system default"
              color: root.configuredOutput === "" ? root.foreground : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              textFormat: Text.PlainText
            }
            MouseArea {
              id: defMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.choose("output", "")
            }
          }

          Text {
            width: parent.width
            visible: root.sources.length === 0
            text: "No capture devices found."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            textFormat: Text.PlainText
          }

          PanelSeparator {
            width: parent.width
            foreground: root.foreground
          }

          Text {
            width: parent.width
            text: (root.state && root.state.model ? root.state.model + " · " : "")
                  + "click a device to switch · r to rescan"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
          }
        }
      }
    }
  }
}
