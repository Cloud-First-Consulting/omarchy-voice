"""The one boundary between what a model says and what this machine runs.

Three scripts execute argv arrays that a language model composed:
omarchy-voice-plan (a spoken request), omarchy-voice-help --run (an answer
about Omarchy) and omarchy-voice-diagnose --fix (a proposed repair). Each used
to carry its own allowlist, and each list was a set of program names - which
is not a boundary, because several of those programs will do anything at all
given the right first argument: `hyprctl dispatch exec` runs a shell command,
`hyprctl plugin load` loads a shared object into the compositor, `omarchy
plugin add` installs code from a URL, `omarchy launch terminal` takes a command
to run, and `omarchy-voice-browser` passed its arguments straight to Chromium,
flags included.

So this is one module, one function, and one rule: every program is allowed
only in the shapes the catalogue actually offers, and anything else about it
is refused. Unknown subcommands are refused, not merely dangerous ones. The
model's prompt may be steered by a window title or a web page - that is why
the agent is run with no tools - but the worst a steered plan can do is pick
from this table.

    vet(argv) -> None if it may run, else a short reason it may not

The table is exercised by tests/test_vet.py, which is the place to add a case
before widening anything here.
"""

import re

# Programs the planner may name at all. Deliberately small.
ALLOWED = {
    "omarchy", "omarchy-window", "omarchy-voice-browser", "hyprctl",
    "systemctl", "wpctl", "pactl", "playerctl", "brightnessctl",
    "bluetoothctl", "nmcli", "voxtype", "xdg-open", "curl", "notify-send",
    "date", "cal", "uptime", "free", "df", "du", "ip",
}

# Never acceptable from a mishearing, whichever program.
FORBIDDEN_WORDS = re.compile(r"^(poweroff|halt|shutdown|reboot|logout)$", re.I)

# `omarchy <group> <verb>`: the verbs each group may be used with. A group that
# is not here is refused, which covers pkg, plugin, update, install, webapp,
# dev, default, config, menu and whatever is added next. `agent` is refused on
# purpose: starting a coding agent on a model-composed task is the one thing
# the phrase table does only on a sentence the user actually spoke.
OMARCHY = {
    "launch":    {"browser", "terminal", "nautilus", "editor", "spotify",
                  "signal", "1password", "about", "screensaver", "discord"},
    "theme":     {"set", "bg", "current", "list"},
    "toggle":    None,            # every toggle is a desktop switch
    "audio":     None,
    "bluetooth": {"power", "device"},
    "capture":   None,
    "reminder":  None,
    "display":   None,
    "hyprland":  {"monitor", "focus", "workspace", "window"},
    "window":    None,
    "battery":   None,
    "system":    {"lock", "stats"},
    "version":   None,
}

HYPRCTL_QUERIES = {"monitors", "clients", "activewindow", "workspaces",
                   "binds", "devices", "version", "activeworkspace", "layers"}
HYPRCTL_DISPATCH = {"workspace", "killactive", "fullscreen", "togglefloating",
                    "focuswindow", "movetoworkspace", "movetoworkspacesilent",
                    "movefocus", "cyclenext", "togglesplit", "pin",
                    "centerwindow", "focusmonitor", "dpms"}
# The one eval the catalogue offers: screen zoom. Exactly that shape.
HYPRCTL_ZOOM = re.compile(
    r"^hl\.config\(\s*\{\s*cursor\s*=\s*\{\s*zoom_factor\s*=\s*\d+(\.\d+)?\s*\}\s*\}\s*\)$")

SYSTEMCTL_VERBS = {"start", "stop", "restart", "status", "is-active", "is-enabled"}
UNIT_NAME = re.compile(r"^[A-Za-z0-9@._-]+$")

NMCLI_READ = {("general",), ("device",), ("dev",), ("connection", "show"),
              ("con", "show"), ("radio",), ("networking",)}
PACTL_VERBS = {"set-sink-volume", "set-sink-mute", "set-source-volume",
               "set-source-mute", "set-default-sink", "set-default-source",
               "get-sink-volume", "get-sink-mute", "get-source-volume",
               "get-source-mute", "get-default-sink", "get-default-source",
               "list", "info", "move-sink-input", "move-source-output"}
WPCTL_VERBS = {"set-volume", "set-mute", "set-default", "status", "get-volume",
               "inspect", "set-profile"}
BLUETOOTHCTL_VERBS = {"power", "connect", "disconnect", "show", "devices",
                      "info", "scan", "discoverable"}
VOXTYPE_VERBS = {"status", "record"}
IP_MUTATING = {"add", "del", "delete", "change", "replace", "flush", "set",
               "append", "prepend", "monitor"}

# curl is here for one thing - the one-line weather - so it is vetted by the
# shape of a plain GET rather than by a list of dangerous flags, which kept
# losing: -sO bundles, -T is --upload-file, -F posts a file, -K reads any
# option at all out of a file.
CURL_SAFE_FLAGS = {"--silent", "--show-error", "--location", "--compressed"}
CURL_VALUE_FLAGS = {"-m", "--max-time", "--connect-timeout"}
CURL_SAFE_SHORT = set("sSL")


def _http(arg):
    return arg.startswith(("http://", "https://"))


def _curl(argv):
    expect_value = False
    target = False
    for arg in argv[1:]:
        if expect_value:
            expect_value = False
            continue
        if arg in CURL_VALUE_FLAGS:
            expect_value = True
            continue
        if arg in CURL_SAFE_FLAGS:
            continue
        if re.fullmatch(r"-[A-Za-z]+", arg):
            bad = [c for c in arg[1:] if c not in CURL_SAFE_SHORT]
            if bad:
                return f"curl option -{bad[0]} is not allowed"
            continue
        if arg.startswith("-"):
            return f"curl option {arg} is not allowed"
        if "://" in arg and not _http(arg):
            return f"curl may only fetch http(s), not {arg}"
        if arg.startswith(("/", ".", "~", "@")):
            return f"curl may only fetch a URL, not the path {arg}"
        target = True
    return None if target else "curl needs a URL"


def _omarchy(argv):
    if len(argv) < 2:
        return "omarchy needs a command"
    group, rest = argv[1], argv[2:]
    if group not in OMARCHY:
        return f"omarchy {group} is not available to voice"
    verbs = OMARCHY[group]
    if verbs is not None:
        if not rest:
            return f"omarchy {group} needs a verb"
        if rest[0] not in verbs:
            return f"omarchy {group} {rest[0]} is not available to voice"
    if group == "launch":
        # `launch terminal <command>`, `launch or focus <pattern> <command>` and
        # `launch floating terminal ... <command>` all run a command; none of
        # those shapes is offered. browser takes a URL, editor a path.
        if rest[0] == "terminal" and len(rest) > 1:
            return "the terminal may be opened, not given a command"
        if rest[0] == "browser" and len(rest) > 1 and not _http(rest[1]):
            return "the browser may only be given an http(s) URL"
        if rest[0] == "discord" and rest[1:] != ["community"]:
            return "omarchy launch discord takes only 'community'"
    if group == "hyprland" and rest[0] == "monitor" and rest[1:2] != ["scaling"]:
        return "only monitor scaling is available to voice"
    if group == "theme" and rest[0] == "bg" and rest[1:] not in ([], ["next"]):
        return "theme bg may only be asked for the next wallpaper"
    return None


def _hyprctl(argv):
    rest = argv[1:]
    if rest and rest[0] in {"-j", "--json"}:
        rest = rest[1:]
    if not rest:
        return "hyprctl needs a command"
    if rest[0] in HYPRCTL_QUERIES and len(rest) == 1:
        return None
    if rest[0] == "dispatch":
        if len(rest) < 2 or rest[1] not in HYPRCTL_DISPATCH:
            return f"hyprctl dispatch {rest[1] if len(rest) > 1 else ''} is not available to voice".replace("  ", " ")
        return None
    if rest[0] == "eval":
        if len(rest) == 2 and HYPRCTL_ZOOM.match(rest[1]):
            return None
        return "hyprctl eval may only set the screen zoom"
    return f"hyprctl {rest[0]} is not available to voice"


def _systemctl(argv):
    rest = [a for a in argv[1:] if a not in {"--no-pager", "-q", "--quiet"}]
    if "--user" not in rest:
        return "only user services may be controlled"
    rest.remove("--user")
    if any(a.startswith("-") for a in rest):
        return "systemctl options are not available to voice"
    if len(rest) != 2 or rest[0] not in SYSTEMCTL_VERBS:
        return "systemctl may only start, stop, restart or query one unit"
    if not UNIT_NAME.match(rest[1]):
        return f"{rest[1]} is not a unit name"
    return None


def _nmcli(argv):
    rest = argv[1:]
    if any(a in {"-s", "--show-secrets", "-a", "--ask"} for a in rest):
        return "network secrets are not available to voice"
    while rest and rest[0] in {"-t", "--terse", "-p", "--pretty", "-c", "--colors"}:
        rest = rest[1:]
    if rest and rest[0] in {"-f", "--fields"}:
        rest = rest[2:]
    for shape in NMCLI_READ:
        if tuple(rest[:len(shape)]) == shape:
            if shape[0] in {"device", "dev"} and rest[1:2] not in ([], ["status"], ["show"], ["wifi"]):
                return f"nmcli device {rest[1]} is not available to voice"
            if shape[0] in {"device", "dev"} and rest[1:2] == ["wifi"] and rest[2:3] not in ([], ["list"], ["rescan"]):
                return "nmcli may only list or rescan wifi"
            if shape[0] == "radio" and rest[1:2] not in ([], ["wifi"], ["wwan"], ["all"]):
                return f"nmcli radio {rest[1]} is not available to voice"
            return None
    return "nmcli may only read network state or switch a radio"


def vet(argv):
    """None if this argv may run, else why it may not."""
    if not argv or not isinstance(argv, (list, tuple)) or \
            not all(isinstance(a, str) for a in argv):
        return "malformed command"
    if any("\n" in a or "\0" in a for a in argv):
        return "arguments may not contain newlines"
    prog = argv[0]
    if prog not in ALLOWED:
        return f"{prog} is not on the allowlist"
    for arg in argv[1:]:
        if FORBIDDEN_WORDS.match(arg):
            return f"{arg} is not available to voice"

    if prog == "omarchy":
        return _omarchy(argv)
    if prog == "hyprctl":
        return _hyprctl(argv)
    if prog == "systemctl":
        return _systemctl(argv)
    if prog == "nmcli":
        return _nmcli(argv)
    if prog == "curl":
        return _curl(argv)
    if prog == "xdg-open":
        if len(argv) != 2 or not _http(argv[1]):
            return "xdg-open may only open one http(s) URL"
        return None
    if prog == "omarchy-voice-browser":
        for arg in argv[1:]:
            if not _http(arg):
                return "the voice browser may only be given http(s) URLs"
        return None
    if prog == "omarchy-window":
        if len(argv) < 2 or argv[1] not in {"close", "focus", "list"}:
            return "omarchy-window may only close, focus or list"
        if any(a.startswith("-") for a in argv[2:]):
            return "omarchy-window takes a window name, not options"
        return None
    if prog == "pactl":
        if len(argv) < 2 or argv[1] not in PACTL_VERBS:
            return "that pactl command is not available to voice"
        return None
    if prog == "wpctl":
        if len(argv) < 2 or argv[1] not in WPCTL_VERBS:
            return "that wpctl command is not available to voice"
        return None
    if prog == "bluetoothctl":
        if len(argv) < 2 or argv[1] not in BLUETOOTHCTL_VERBS:
            return "that bluetoothctl command is not available to voice"
        return None
    if prog == "voxtype":
        if len(argv) < 2 or argv[1] not in VOXTYPE_VERBS:
            return "voxtype may only be asked to record or for its status"
        if any(a.startswith("-") for a in argv[1:]):
            return "voxtype options are not available to voice"
        return None
    if prog == "ip":
        if any(a in IP_MUTATING for a in argv[1:]):
            return "ip may only show network state"
        return None
    if prog == "date" and any(a in {"-s", "--set"} or a.startswith("--set=") for a in argv[1:]):
        return "the clock may not be set by voice"
    return None
