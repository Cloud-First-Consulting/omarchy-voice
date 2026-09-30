#!/bin/bash

# Link this repo into place and start the listener.
#
# Symlinks rather than copies, so editing the repo edits the running system and
# there is never a stale duplicate in ~/.local/bin to wonder about.
#
#   ./install.sh                      scripts, unit, bar widget, config
#   ./install.sh --skills claude      also the agent skill, for the tools named
#   ./install.sh --skills all         ... for every tool whose directory exists
#
# Nothing here ever replaces something it did not make. A file or link that is
# already at a target path and does not point into this clone is left alone
# and reported, so a same-named tool from elsewhere survives an install.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
CONFIG="$HOME/.config/omarchy/voice-wake.json"

# Agent skill directories, by the name you would say. `agents` is the
# agent-agnostic ~/.agents/skills that several tools read.
declare -A SKILL_DIRS=(
  [agents]="$HOME/.agents/skills"
  [claude]="$HOME/.claude/skills"
  [codex]="$HOME/.codex/skills"
)

skills=""
while (($#)); do
  case $1 in
    --skills)
      [[ -n ${2:-} ]] || { echo "usage: $0 [--skills all|agents,claude,codex]" >&2; exit 2; }
      skills=$2; shift 2 ;;
    --skills=*) skills=${1#--skills=}; shift ;;
    -h|--help) sed -n '3,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; echo "usage: $0 [--skills all|agents,claude,codex]" >&2; exit 2 ;;
  esac
done

# Make $2 a link to $1, but only if $2 is absent or already a link into this
# clone. Anything else at that path belongs to someone else and stays.
link() {
  local target=$1 path=$2
  if [[ -L $path ]]; then
    case $(readlink -f "$path") in
      "$REPO"/*|"$REPO") ;;
      *) echo "  kept $path: a link to somewhere else"; return 1 ;;
    esac
  elif [[ -e $path ]]; then
    echo "  kept $path: not ours to replace"; return 1
  fi
  ln -sfn "$target" "$path"
}

mkdir -p "$BIN" "$UNIT" "$(dirname "$CONFIG")"

# Executable files only. A bare bin/* glob also matches __pycache__, which
# python drops next to the scripts it imports, and linking that into ~/.local/bin
# puts a directory on your PATH for no reason.
for script in "$REPO"/bin/*; do
  [[ -f $script && -x $script ]] || continue
  name=$(basename "$script")
  link "$script" "$BIN/$name" && echo "  linked $name"
done

# Copied, not linked: systemd manages unit enablement with symlinks of its own,
# and a unit file that is itself a symlink makes `enable` behave unpredictably.
install -m 644 "$REPO/systemd/omarchy-voice-wake.service" "$UNIT/omarchy-voice-wake.service"
echo "  installed omarchy-voice-wake.service"

# The agent skill, only when asked for and only for the tools named. It is
# linked the way Omarchy links its own: one copy in the repo, one link per
# tool. A directory that does not exist is skipped rather than created, so
# this never invents a config location for a tool that is not installed.
#
# ~/.agents/skills is the agent-agnostic one, which is the point - the answer
# to "what key does this" should not depend on which coding agent you run.
#
# This complements Omarchy's own `omarchy` skill rather than overlapping it:
# that one covers *changing* a binding, and never tells an agent to read the
# live ones.
if [[ -n $skills ]]; then
  [[ $skills == all ]] && skills=$(IFS=,; echo "${!SKILL_DIRS[*]}")
  IFS=, read -ra wanted <<<"$skills"
  for tool in "${wanted[@]}"; do
    dir=${SKILL_DIRS[$tool]:-}
    [[ -n $dir ]] || { echo "  unknown tool '$tool' (choose from: ${!SKILL_DIRS[*]})" >&2; exit 2; }
    [[ -d $dir ]] || { echo "  skipped $tool: ${dir/#$HOME/\~} does not exist"; continue; }
    for skill in "$REPO"/skills/*/; do
      [[ -d $skill ]] || continue
      name=$(basename "$skill")
      link "${skill%/}" "$dir/$name" && echo "  linked skill $name -> ${dir/#$HOME/\~}"
    done
  done
else
  echo "  agent skill not installed (opt in with: $0 --skills all, or --skills claude,codex)"
fi

# The bar widget. This repo *is* the plugin: manifest.json and Panel.qml sit at
# the root, so `omarchy plugin add <repo-url>` clones it straight into
# ~/.config/omarchy/plugins/<id>, and this script is then run from there. When
# it is run from a clone kept somewhere else, the plugin directory is linked to
# that clone instead - the same one-copy rule as the scripts above. Linking
# makes it discoverable; it never puts it in your bar, which is your decision.
# (`omarchy plugin validate` on the link reports the link itself; validate the
# clone. `omarchy plugin add` validates a real checkout, so that is unaffected.)
PLUGIN_DIR="$HOME/.config/omarchy/plugins"
id=$(jq -r '.id' "$REPO/manifest.json")
if [[ $(readlink -f "$PLUGIN_DIR/$id" 2>/dev/null) != "$REPO" ]]; then
  mkdir -p "$PLUGIN_DIR"
  if link "$REPO" "$PLUGIN_DIR/$id"; then
    echo "  linked plugin $id"
  else
    echo "    (a clone made by omarchy plugin add? remove it with: omarchy plugin remove $id)"
  fi
fi
echo "    enable the bar icon with: omarchy plugin enable $id right"

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
