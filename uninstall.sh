#!/bin/bash

# Undo install.sh. Stops the listener, takes the widget out of the bar, and
# removes every link install.sh made - and nothing else. Your config and the
# things it learned stay unless you ask for them to go:
#
#   ./uninstall.sh          keep ~/.config/omarchy/voice-wake.json and state
#   ./uninstall.sh --purge  remove those too
#
# The wake word venv (~/.local/share/omarchy-wakeword) and piper
# (~/.local/share/piper) were installed by hand, so they are removed by hand:
#
#   rm -rf ~/.local/share/omarchy-wakeword ~/.local/share/piper

set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user/omarchy-voice-wake.service"
PLUGIN_DIR="$HOME/.config/omarchy/plugins"
CONFIG_DIR="$HOME/.config/omarchy"
purge=0
[[ ${1:-} == --purge ]] && purge=1

# The listener first, so nothing below pulls a script out from under it.
if systemctl --user is-enabled omarchy-voice-wake >/dev/null 2>&1 \
   || systemctl --user is-active omarchy-voice-wake >/dev/null 2>&1; then
  systemctl --user disable --now omarchy-voice-wake 2>/dev/null
  echo "  stopped omarchy-voice-wake"
fi
if [[ -f $UNIT ]]; then
  rm -f "$UNIT"
  systemctl --user daemon-reload
  echo "  removed omarchy-voice-wake.service"
fi

# Only links that point into this repo. A same-named script that came from
# somewhere else is not ours to delete.
for script in "$REPO"/bin/*; do
  [[ -f $script && -x $script ]] || continue
  link="$BIN/$(basename "$script")"
  if [[ -L $link && $(readlink -f "$link") == "$(readlink -f "$script")" ]]; then
    rm -f "$link"
    echo "  unlinked $(basename "$script")"
  fi
done

for skill in "$REPO"/skills/*/; do
  [[ -d $skill ]] || continue
  name=$(basename "$skill")
  for dir in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"; do
    link="$dir/$name"
    if [[ -L $link && $(readlink -f "$link") == "$(readlink -f "${skill%/}")" ]]; then
      rm -f "$link"
      echo "  unlinked skill $name from ${dir/#$HOME/\~}"
    fi
  done
done

# The bar widget. Disable it so the shell stops loading it, then remove the
# plugin directory only if it is our link. A clone made by `omarchy plugin add`
# is the directory this script is running from, and deleting the running script's
# own directory is the shell's job: `omarchy plugin remove` does it cleanly.
id=$(jq -r '.id' "$REPO/manifest.json" 2>/dev/null)
if [[ -n $id ]]; then
  omarchy plugin disable "$id" >/dev/null 2>&1 && echo "  disabled bar widget $id"
  if [[ -L $PLUGIN_DIR/$id ]]; then
    rm -f "$PLUGIN_DIR/$id"
    echo "  unlinked plugin $id"
  elif [[ -d $PLUGIN_DIR/$id ]]; then
    echo "  plugin directory is a clone; finish with: omarchy plugin remove $id --yes"
  fi
fi

if (( purge )); then
  rm -f "$CONFIG_DIR/voice-wake.json" "$CONFIG_DIR/voice-learned.json" \
        "$CONFIG_DIR/voice-mic-levels.json" "$CONFIG_DIR/voice-mic-known-good" \
        "$CONFIG_DIR/reference.txt" "$CONFIG_DIR/reference.version" \
        "$CONFIG_DIR/topics.txt" "$CONFIG_DIR/hotkeys.txt" \
        "$CONFIG_DIR/last-answer.md" "$CONFIG_DIR/last-diagnosis.md"
  rm -rf "${XDG_RUNTIME_DIR:-/run/user/$UID}/omarchy-voice"
  echo "  removed config, learned phrases and cached references"
else
  echo "  kept ~/.config/omarchy/voice-wake.json and learned state (--purge removes them)"
fi

echo
echo "  done. the clone itself is untouched."
