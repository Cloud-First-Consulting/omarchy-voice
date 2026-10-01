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

# The listener first, so nothing below pulls a script out from under it - but
# only if the unit at that path is the one install.sh wrote. install.sh marks
# its copy with a first line naming itself and the sha256 of the body; the
# same name with no marker (and not byte-identical to the repo's unit, which
# earlier releases copied unmarked) is somebody else's service, and this
# script neither stops nor removes it. A marked unit that has been edited is
# stopped and disabled, since it runs the scripts unlinked below, but the file
# itself is kept.
UNIT_SRC="$REPO/systemd/omarchy-voice-wake.service"
UNIT_MARK="# omarchy-voice: written by install.sh; body sha256 "
unit_recorded_hash() { head -n 1 "$1" | sed -n "s/^${UNIT_MARK}\([0-9a-f]\{64\}\)\$/\1/p"; }
unit_body_hash()     { tail -n +2 "$1" | sha256sum | cut -c1-64; }
unit_owner() {
  local recorded; recorded=$(unit_recorded_hash "$1")
  if [[ -z $recorded ]]; then cmp -s "$1" "$UNIT_SRC" && return 0; return 2; fi
  [[ $recorded == "$(unit_body_hash "$1")" ]] && return 0 || return 1
}
if [[ -f $UNIT && ! -L $UNIT ]]; then
  unit_owner "$UNIT" && rc=0 || rc=$?
  if (( rc == 2 )); then
    echo "  kept $UNIT: not written by install.sh, so the service is left as it is"
  else
    systemctl --user disable --now omarchy-voice-wake 2>/dev/null
    echo "  stopped omarchy-voice-wake"
    if (( rc == 0 )); then
      rm -f "$UNIT"
      systemctl --user daemon-reload
      echo "  removed omarchy-voice-wake.service"
    else
      echo "  kept $UNIT: edited since it was installed (disabled, not deleted)"
    fi
  fi
elif [[ -L $UNIT ]]; then
  echo "  kept $UNIT: a link, not a file install.sh wrote"
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
