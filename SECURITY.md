# Security model

Written for marketplace reviewers and for anyone deciding whether to run
this. It maps what the plugin does to the capabilities the
[Omarchy marketplace security baseline](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SECURITY.md)
detects, and states what is written, executed and contacted. The longer
reasoning is in the README's [Safety](README.md#safety) section.

## What runs where

| Component | Process | Started by |
|---|---|---|
| Bar widget and panel (`Panel.qml`) | inside the Omarchy shell | the shell, when the widget is enabled |
| Wake-word listener (`bin/omarchy-voice-wake`) | `omarchy-voice-wake.service`, a **user** unit | `install.sh` (an explicit step after `omarchy plugin add`) |
| Dispatcher, planner, manual, diagnoser, speech (`bin/omarchy-voice-*`) | short-lived processes | the listener on a wake word, or a keybinding the user adds |
| Voice browser (`bin/omarchy-voice-browser`) | a separate Chromium profile with the DevTools port on loopback | only on a spoken request |

`omarchy plugin add` installs the bar widget only. Nothing runs until
`./install.sh` is run by hand, and nothing is downloaded by any script:
the two dependencies that are not packaged (the wake-word model's Python
environment, piper and one voice) are fetched by commands the user runs
from the README, at pinned versions and a pinned repository revision.

## What `install.sh` writes (capability: `installer`)

- `~/.local/bin/omarchy-voice-*`, `~/.local/bin/omarchy-browser-control` - symlinks into the clone
- `~/.config/systemd/user/omarchy-voice-wake.service` - a copy, with a first line naming the script and the sha256 of the body
- `~/.config/omarchy/plugins/omarchy-voice.marvin` - a link to the clone, when the clone is not already that directory
- `~/.config/omarchy/voice-wake.json` - from the example, only if absent
- `~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills` - a link to one skill, **only with `--skills <tools>`**, only into directories that already exist

Nothing is ever written over a path the script did not make. A link that
points elsewhere, a file that is not ours, a unit without our marker or
with an edited body: all are kept and reported. `uninstall.sh` removes
only what resolves to this clone, and the plugin registration only when it
resolves here; `--purge` additionally removes the config, the learned
phrases and the cached references. It never touches `~/.config/hypr`.

## Privileges

No `sudo`, `pkexec` or sudoers change anywhere. The two `sudo pacman -S`
lines in the README are for the user to install `jq` and
`python-websockets` themselves. The listener's unit runs with
`NoNewPrivileges`, `LockPersonality`, `RestrictSUIDSGID` and `UMask=0077`.
The word `sudo` also appears in two prompts, telling the model that
anything needing it is not available to voice.

## Service management (capability: `service-management`)

`systemctl --user` only, on `omarchy-voice-wake` and, from the planner,
on one named user unit at a time (start, stop, restart, status). The
planner cannot enable, link, edit or set environment for a unit.

## Runtime state

Recordings, the last transcript, the conversation history and the
listener's state live in `$XDG_RUNTIME_DIR/omarchy-voice`. Without that
variable the fallback `/tmp/omarchy-voice-<uid>` is created mode 700 and
then checked - a real directory, not a symlink, owned by this user, mode
700 - by one helper every script uses; anything else is refused before
recording, transcribing, writing or reading. Transcripts and command
output are **not written to the journal** unless `log_transcripts` is set
in `voice-wake.json`; the journal records lengths, stages and refusals.
Text that came from a model or a transcript is stripped of control and
format characters before it reaches a notification.

## Network endpoints

| Endpoint | When |
|---|---|
| the backend of the user's own `claude` CLI | every request the phrase table does not cover, every question about Omarchy, every diagnosis: the transcript text and the prompt go to the account the user is logged into. Audio never leaves the machine |
| `wttr.in` over HTTPS | only when the planner answers "what's the weather" with the one `curl` shape it may use |
| `omarchy.org/manual/hotkeys` over HTTPS | once a week, to refresh the list of keys bound inside programs rather than by the compositor; cached in `~/.config/omarchy/hotkeys.txt` |
| whatever URL a spoken request names | opened in the browser, as a URL only |

Wake-word detection (openWakeWord), transcription (voxtype's whisper) and
speech (piper) run locally. Nothing is recorded until the wake word fires.

## Model machine access

The model is asked for words and nothing else. `claude` is invoked with
`--restricted --tools "" --strict-mcp-config --setting-sources ""
--permission-mode manual --max-turns 1 --no-session-persistence`, from an
empty runtime directory: no built-in tool, no MCP server, no hook, no
settings file, no project instructions. If the installed CLI's `--help`
does not list every one of those flags, it is not asked at all - never
asked in a looser form. No other agent is used as the engine, because
none of the others could be shown to meet the same bar (the README's
Safety section says which fell where). The deliberate "ask the agent to
..." handoff opens the user's agent interactively, through `omarchy
agent`, only on a sentence the user spoke; nothing a model composes can
start it.

What the model returns is an argv array, checked whole against one
shape-based boundary (`lib/omarchy_voice_vet.py`, cases in
`tests/test_vet.py`) before it runs, including replays from the learned
cache. The boundary is a table of exact command shapes, not a list of
program names; `curl` additionally runs with `-q --proto =http,https
--proto-redir =http,https`.

## Tests

    python3 -m unittest discover -s tests

Standard library only: the command boundary, the agent flags, the runtime
directory helpers in both languages.
