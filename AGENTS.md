# Notes for coding agents

Guidance for an agent working on this repo. Portable on purpose: `CLAUDE.md`
points here rather than repeating it, because this project deliberately works
with any of the agents Omarchy supports.

## Never write a keybinding or a command from memory

This is the one rule that matters. Everything this project does is grounded in
what is installed on the machine it is running on, and an answer recalled from
training data describes some other version of a fast-moving distribution.

Get the live list instead:

    omarchy-voice-reference --print      # keybindings + every command, this machine
    omarchy-voice-reference --force      # rebuild now, and refresh the manual
    hyprctl binds -j                     # just the bindings, raw
    omarchy commands --all --json        # just the commands, raw

That reference is regenerated whenever the installed version changes, and it
includes anything the user has rebound.

It has two layers, and they are not interchangeable:

- **Live bindings**, from `hyprctl binds`. What this machine actually does,
  rebinds included. Authoritative.
- **Documented hotkeys**, from <https://omarchy.org/manual/hotkeys>, cached for
  a week. Upstream defaults - but the only source for keys bound *inside*
  programs (tmux, Neovim, the terminal, the file manager), which `hyprctl`
  cannot see at all. Where the two overlap, live wins.

**Do not paste the output of those into this repo.** A committed snapshot is
wrong for everyone else and stale here the moment Omarchy updates or the user
rebinds a key. For scale: this README recorded 356 commands and 233 bindings
when it was written, and the same machine a few releases later measures 367 and
174. A table checked in "for reference" would have been misleading within
weeks, and would publish that machine's personal bindings as though they were
everyone's.

The same applies to counts in prose. If you write "174 bindings" into a
document, you have just created something that goes stale silently.

## There is also a skill, for agents not working in this repo

`skills/omarchy-hotkeys/` is linked by `install.sh` into `~/.agents/skills`,
`~/.claude/skills` and `~/.codex/skills` - whichever exist. `~/.agents/skills`
is Omarchy's agent-agnostic location, so the answer to "what key does this" does
not depend on which coding agent is running.

This file only applies to an agent working *in this repo*. The skill applies
anywhere on the machine, which is where the question usually gets asked.

It complements Omarchy's own `omarchy` skill rather than overlapping it: that
one covers *changing* a binding and never tells an agent to read the live ones.

## What lives where

    bin/omarchy-voice-wake         always-on listener: detect, record, dispatch
    bin/omarchy-voice-command      phrase table, routing, normalising speech
    bin/omarchy-voice-plan         model fallback, allowlist, learned cache
    bin/omarchy-voice-help         answers questions about Omarchy itself
    bin/omarchy-voice-diagnose     probes the machine, then explains what broke
    bin/omarchy-voice-reference    builds the reference the two above answer from
    lib/omarchy_voice_agent.py     which coding agent answers, and how to ask it

## Conventions that are load-bearing

- **argv arrays, never shell strings.** Nothing reaches a shell. If you find
  yourself building a command as a string, that is the bug.
- **The allowlist is the boundary, and it vets shape, not just names.** Several
  allowed programs will do anything given the right flag, so `curl`, `nmcli`
  and `xdg-open` are checked by the shape they are used in. Test changes
  against `vet()` directly.
- **Window titles reaching the planner are attacker-controlled.** A web page
  sets its own title, and that list lands in a prompt whose output becomes
  commands. Do not widen what the planner may run on the strength of something
  it was *told*; in particular do not put anything that acts on a page back on
  its allowlist. A browser action requires the user to have spoken one.
- **The assistant's name comes from config**, never from a literal in the
  source. `wake_words` and `wake_aliases` in `~/.config/omarchy/voice-wake.json`
  drive every regex that matches it.
- **Which agent answers comes from `omarchy-default-agent`**, not from a
  hardcoded binary. `lib/omarchy_voice_agent.py` owns the per-agent invocation.
- **Questions default to the manual.** A "how do I" question goes to
  `omarchy-voice-help` unless it is plainly about the world. The manual leads
  with the key to press, because on a desktop that is the answer.

## Before you claim something works

    omarchy-voice-wake-test      # detector, against real audio, with margins
    omarchy-voice-wake-check     # did the service come up healthy
    bash -n bin/omarchy-voice-command && python3 -m compileall -q bin lib

The detector suite reports the margin between the worst real wake and the best
near-miss. A change that narrows that margin is a regression even if every case
still passes.
