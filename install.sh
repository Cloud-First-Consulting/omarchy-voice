#!/bin/bash

# Link this repo into place and start the listener.
#
# Symlinks rather than copies, so editing the repo edits the running system and
# there is never a stale duplicate in ~/.local/bin to wonder about.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
CONFIG="$HOME/.config/omarchy/voice-wake.json"

mkdir -p "$BIN" "$UNIT" "$(dirname "$CONFIG")"

# Executable files only. A bare bin/* glob also matches __pycache__, which
# python drops next to the scripts it imports, and linking that into ~/.local/bin
# puts a directory on your PATH for no reason.
for script in "$REPO"/bin/*; do
  [[ -f $script && -x $script ]] || continue
  name=$(basename "$script")
  ln -sfn "$script" "$BIN/$name"
  echo "  linked $name"
done

# Copied, not linked: systemd manages unit enablement with symlinks of its own,
# and a unit file that is itself a symlink makes `enable` behave unpredictably.
install -m 644 "$REPO/systemd/omarchy-voice-wake.service" "$UNIT/omarchy-voice-wake.service"
echo "  installed omarchy-voice-wake.service"

# Skills, linked the way Omarchy links its own: one copy in the repo, symlinked
# into each agent's skill directory that already exists.
#
# ~/.agents/skills is the agent-agnostic one, which is the point - the answer to
# "what key does this" should not depend on which coding agent you happen to
# run. Only directories that already exist are touched, so this never invents a
# config location for an agent that is not installed.
#
# This complements Omarchy's own `omarchy` skill rather than overlapping it:
# that one covers *changing* a binding, and never tells an agent to read the
# live ones.
for skill in "$REPO"/skills/*/; do
  [[ -d $skill ]] || continue
  name=$(basename "$skill")
  for dir in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"; do
    [[ -d $dir ]] || continue
    ln -sfn "${skill%/}" "$dir/$name"
    echo "  linked skill $name -> ${dir/#$HOME/\~}"
  done
done

# Shell plugins, linked the same way. Only into a directory that already
# exists, so this never creates a plugin folder on a machine whose shell does
# not use one. The shell picks the change up on its own; `omarchy restart shell`
# forces it.
PLUGIN_DIR="$HOME/.config/omarchy/plugins"
for plugin in "$REPO"/plugins/*/; do
  [[ -f $plugin/manifest.json ]] || continue
  id=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['id'])" "$plugin/manifest.json" 2>/dev/null) || continue
  [[ -n $id ]] || continue
  mkdir -p "$PLUGIN_DIR"
  ln -sfn "${plugin%/}" "$PLUGIN_DIR/$id"
  echo "  linked plugin $id"
  echo "    enable it with: omarchy plugin enable $id right"
done

# Never overwrite a real config: it names this machine's microphone.
if [[ ! -f $CONFIG ]]; then
  cp "$REPO/config/voice-wake.json.example" "$CONFIG"
  echo "  created $CONFIG from the example"
else
  echo "  kept the existing $CONFIG"
fi

missing=()
[[ -x $HOME/.local/share/omarchy-wakeword/venv/bin/python ]] || missing+=("openwakeword venv (~/.local/share/omarchy-wakeword/venv)")
[[ -x $HOME/.local/share/piper/piper ]] || missing+=("piper (~/.local/share/piper)")
command -v voxtype >/dev/null || missing+=("voxtype")
if ((${#missing[@]})); then
  echo
  echo "  still needed before this will run:"
  printf '    - %s\n' "${missing[@]}"
  echo "  see README.md > Dependencies"
  exit 1
fi

systemctl --user daemon-reload
systemctl --user enable --now omarchy-voice-wake
echo
echo "  started. check it with: omarchy-voice-wake-check"
