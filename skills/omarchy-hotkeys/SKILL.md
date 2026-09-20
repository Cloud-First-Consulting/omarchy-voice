---
name: omarchy-hotkeys
description: >
  REQUIRED before answering what key does something on an Omarchy machine, or
  saying that nothing is bound to it. Use for: "what's the shortcut for X",
  "what key does X", "is there a keybinding for X", "how do I X" about the
  desktop, "what does SUPER+X do", and any answer that names a key combination.
  Triggers: keybinding, key binding, hotkey, shortcut, key combo, what key,
  which key, press, bound to, hyprctl binds, tmux keys, Neovim keys, Ghostty
  keys, file manager keys. Covers reading what is bound; for *changing* a
  binding use the `omarchy` skill instead.
---

# Omarchy hotkeys

Answer from this machine, never from memory.

Omarchy moves quickly and users rebind things. A key combination recalled from
training data describes some other install, and being confidently wrong about a
keystroke is worse than saying you do not know - the person presses it, nothing
happens, and they cannot tell whether they misheard you or the key is gone.

## Get the bindings

    omarchy-voice-reference --print

That prints every command on this machine plus two layers of keybindings. If
that command is not installed, fall back to:

    hyprctl binds -j                 # live window-manager bindings
    omarchy commands --all --json    # every command and its arguments

## The two layers are not interchangeable

**Live bindings** come from `hyprctl binds`. This is what the machine actually
does, including anything the user rebound. It is authoritative.

**Documented hotkeys** come from <https://omarchy.org/manual/hotkeys>. These
are upstream defaults. They are the *only* source for keys bound inside
programs - tmux, Neovim, Ghostty, the file manager - because those are bound by
the program rather than by the window manager, so `hyprctl binds` cannot see
them at all. It knows the key that opens tmux and nothing about what any key
does once tmux has it.

Where the two disagree, live wins. The manual carries no version marker, so it
may describe a newer Omarchy than the one installed.

## Answering well

Lead with the key, not the command. This is a desktop: "how do I take a
screenshot" is answered by "Press PRINT", not by `omarchy capture screenshot`,
which is true and useless to someone learning their way around.

When nothing is bound to what was asked, do not stop at "there is no shortcut".
Give three things:

1. That there is no shortcut for it.
2. The command that does do it, with a real argument from the reference - never
   an invented one.
3. The nearest keys that get close, each with what it *actually* does.

Order those alternatives by what they achieve, not by which words they share
with the question. Asked to make text bigger on a machine with no text-size
binding, display scaling (`SUPER+/`) is a better answer than the screen
magnifier (`SUPER+CTRL+Z`), because it lasts - however much "zoom" sounds like
the question.

Never describe a near neighbour as doing the thing that was asked. Text size
and screen zoom are different things, and "press SUPER+CTRL+Z to scale text
everywhere" is simply false.

## Do not write bindings down

Do not paste a binding table into a repo, a README, or a memory file. It is
wrong for every other machine and stale on this one the moment Omarchy updates
or a key is rebound. Run the command again instead.
