# The private runtime directory, for the shell scripts. Source this, then:
#
#   RUN_DIR=$(omarchy_voice_run_dir) || exit 1
#
# Recordings, the last transcript and the listener's state live there, so it
# has to be ours and nobody else's. $XDG_RUNTIME_DIR is that by construction.
# Without it the fallback is /tmp/omarchy-voice-<uid>, and a name is not
# ownership: another local user can create that path first. So the directory
# is created with mode 700 if absent, and then *checked* - a real directory,
# not a symlink, owned by this user, mode 700 after a chmod that must succeed.
# Anything else fails, and the caller stops before recording or writing.

_omarchy_voice_private_dir() {
  local dir=$1
  mkdir -m 700 "$dir" 2>/dev/null || true
  if [[ -L $dir || ! -d $dir || ! -O $dir ]]; then
    echo "omarchy-voice: $dir exists but is not a private directory of ours; refusing to use it" >&2
    return 1
  fi
  chmod 700 "$dir" 2>/dev/null || { echo "omarchy-voice: cannot make $dir private" >&2; return 1; }
  [[ $(stat -c %a "$dir" 2>/dev/null) == 700 ]] || { echo "omarchy-voice: $dir is not mode 700" >&2; return 1; }
}

omarchy_voice_run_dir() {
  local base
  if [[ -n ${XDG_RUNTIME_DIR:-} ]]; then
    base=$XDG_RUNTIME_DIR
  else
    base=/tmp/omarchy-voice-$(id -u)
    _omarchy_voice_private_dir "$base" || return 1
  fi
  _omarchy_voice_private_dir "$base/omarchy-voice" || return 1
  printf '%s\n' "$base/omarchy-voice"
}
