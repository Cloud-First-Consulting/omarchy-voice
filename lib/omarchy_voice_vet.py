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

# Every argument has a shape, and a command is matched whole: the right
# number of arguments, each of the right kind, and nothing after them. A
# trailing argument is never ignored, because a launcher that forwards its
# argument list turns a trailing argument into a flag for the program it
# starts - `omarchy launch browser <url> --renderer-cmd-prefix=...` would have
# handed Chromium a native executable to run. Flags are accepted only where a
# shape names them.
def _url(a):   return a.startswith(("http://", "https://"))
def _num(a):   return re.fullmatch(r"\d+(\.\d+)?", a) is not None
def _mac(a):   return re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", a) is not None
def _word(a):  return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", a) is not None
def _name(a):  return bool(a) and not a.startswith(("-", "+")) and "/" not in a
def _text(a):  return bool(a) and not a.startswith(("-", "+"))
def _path(a):  return bool(a) and not a.startswith(("-", "+"))
def _vol(a):   return a in {"raise", "lower", "mute-toggle"} or re.fullmatch(r"[+-]?\d+%?", a) is not None
def _lit(*xs): return lambda a: a in xs
OPT = object()  # marks the matcher before it as optional

def _shape(args, spec):
    """None if args fit spec - matchers in order, OPT after one that may be
    absent - with nothing left over, else a reason."""
    matchers = []
    for item in spec:
        if item is OPT:
            matchers[-1] = (matchers[-1][0], True)
        else:
            matchers.append((item, False))
    required = sum(1 for _, optional in matchers if not optional)
    if len(args) < required:
        return "too few arguments"
    if len(args) > len(matchers):
        return f"unexpected argument {args[len(matchers)]!r}"
    for arg, (match, _) in zip(args, matchers):
        if not match(arg):
            return f"unexpected argument {arg!r}"
    return None

# `omarchy <words...>`: the exact shapes offered, longest prefix first. A
# prefix that is not here is refused, which covers pkg, plugin, update,
# install, webapp, dev, default, config, menu and whatever is added next.
# `agent` is refused on purpose: starting a coding agent on a model-composed
# task is the one thing the phrase table does only on a sentence the user
# actually spoke. launch terminal <command>, launch or focus, launch editor
# --inline, capture screenshot --editor=<name>, theme bg set <path>, theme
# bg install, bluetooth device pair|forget and reminder -i are all real
# subcommands that are deliberately not here.
OMARCHY_SHAPES = [
    (("launch", "browser"),            [_url, OPT]),
    (("launch", "terminal"),           []),
    (("launch", "nautilus"),           [_lit("cwd"), OPT]),
    (("launch", "editor"),             [_path]),
    (("launch", "spotify"),            []),
    (("launch", "signal"),             []),
    (("launch", "1password"),          []),
    (("launch", "about"),              []),
    (("launch", "screensaver"),        []),
    (("launch", "discord"),            [_lit("community")]),
    (("theme", "set"),                 [_name]),
    (("theme", "bg"),                  [_lit("next", "current"), OPT]),
    (("theme", "current"),             []),
    (("theme", "list"),                []),
    (("toggle",),                      [_word]),
    (("audio", "output", "volume"),    [_vol]),
    (("audio", "output", "switch"),    []),
    (("audio", "output", "sink"),      [_name, OPT]),
    (("audio", "output", "set", "default"), [_word, _name]),
    (("audio", "input", "set", "default"),  [_word, _name]),
    (("audio", "input", "mute"),       []),
    (("bluetooth", "power"),           [_lit("on", "off", "toggle", "is-on")]),
    (("bluetooth", "device"),          [_lit("connect", "disconnect"), _mac]),
    (("capture", "screenshot"),        [_lit("smart", "region", "windows", "fullscreen"), OPT,
                                        _lit("slurp", "copy", "save"), OPT]),
    (("capture", "screenrecording"),   "RECORDING"),
    (("capture", "text"),              []),
    (("capture", "qr"),                []),
    (("reminder", "show"),             []),
    (("reminder", "clear"),            []),
    (("reminder",),                    [_num, _text, OPT]),
    (("display", "text", "size"),      [lambda a: _num(a) or a == "reset", OPT]),
    (("hyprland", "monitor", "scaling"), [lambda a: a in {"up", "down"} or _num(a), OPT]),
    (("hyprland", "focus", "app"),     [_name]),
    (("hyprland", "workspace", "layout", "toggle"), []),
    (("hyprland", "window", "close", "all"), []),
    (("hyprland", "window", "gaps", "toggle"), []),
    (("hyprland", "window", "transparency", "toggle"), []),
    (("hyprland", "window", "tiled", "fullscreen", "toggle"), []),
    (("hyprland", "window", "single", "square", "aspect", "toggle"), []),
    (("hyprland", "window", "width"),  [_lit("save", "restore")]),
    (("hyprland", "window", "pop"),    [_num, OPT, _num, OPT, _num, OPT, _num, OPT]),
    (("window", "close", "all"),       []),
    (("window", "gaps", "toggle"),     []),
    (("window", "transparency", "toggle"), []),
    (("window", "tiled", "fullscreen", "toggle"), []),
    (("window", "single", "square", "aspect", "toggle"), []),
    (("window", "width"),              [_lit("save", "restore")]),
    (("window", "pop"),                [_num, OPT, _num, OPT, _num, OPT, _num, OPT]),
    (("battery", "status"),            []),
    (("battery", "present"),           []),
    (("system", "lock"),               []),
    (("system", "stats"),              []),
    (("version",),                     []),
]
RECORDING_FLAGS = {"--fullscreen", "--stop-recording", "--with-desktop-audio",
                   "--with-microphone-audio"}


def _omarchy(argv):
    words = argv[1:]
    if not words:
        return "omarchy needs a command"
    for prefix, spec in sorted(OMARCHY_SHAPES, key=lambda x: -len(x[0])):
        if tuple(words[:len(prefix)]) == prefix:
            rest = words[len(prefix):]
            if spec == "RECORDING":
                bad = [a for a in rest if a not in RECORDING_FLAGS]
                return f"unexpected argument {bad[0]!r}" if bad else None
            reason = _shape(rest, spec)
            return f"omarchy {' '.join(prefix)}: {reason}" if reason else None
    return f"omarchy {' '.join(words[:2])} is not available to voice"


HYPRCTL_QUERIES = {"monitors", "clients", "activewindow", "workspaces",
                   "binds", "devices", "version", "activeworkspace", "layers"}
HYPRCTL_DISPATCH = {
    "workspace": [_word], "killactive": [], "fullscreen": [_lit("0", "1", "2"), OPT],
    "togglefloating": [], "focuswindow": [_name], "movetoworkspace": [_name],
    "movetoworkspacesilent": [_name], "movefocus": [_lit("l", "r", "u", "d")],
    "cyclenext": [_lit("prev"), OPT], "togglesplit": [], "pin": [],
    "centerwindow": [], "focusmonitor": [_name],
    "dpms": [_lit("on", "off", "toggle"), _name, OPT],
}
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
PLAYERCTL_VERBS = {"play", "pause", "play-pause", "stop", "next", "previous",
                   "status", "metadata", "volume", "position", "shuffle", "loop"}
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
        reason = _shape(rest[2:], HYPRCTL_DISPATCH[rest[1]])
        return f"hyprctl dispatch {rest[1]}: {reason}" if reason else None
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
        return _shape(argv[1:], [_url, OPT]) and "the voice browser may only be given one http(s) URL"
    if prog == "omarchy-window":
        if len(argv) < 2 or argv[1] not in {"close", "focus", "list"}:
            return "omarchy-window may only close, focus or list"
        if _shape(argv[2:], [] if argv[1] == "list" else [_text]):
            return "omarchy-window takes one window name, not options"
        return None
    if prog in {"pactl", "wpctl", "bluetoothctl"}:
        verbs = {"pactl": PACTL_VERBS, "wpctl": WPCTL_VERBS, "bluetoothctl": BLUETOOTHCTL_VERBS}[prog]
        if len(argv) < 2 or argv[1] not in verbs:
            return f"that {prog} command is not available to voice"
        if len(argv) > 5 or any(a.startswith("-") for a in argv[2:]):
            return f"{prog} {argv[1]} takes names and values, not options"
        return None
    if prog == "playerctl":
        rest = argv[1:]
        while rest and rest[0] in {"-a", "--all-players"} or (rest and rest[0] in {"-p", "--player"} and len(rest) > 1 and _name(rest[1])):
            rest = rest[2:] if rest[0] in {"-p", "--player"} else rest[1:]
        if not rest or rest[0] not in PLAYERCTL_VERBS:
            return "that playerctl command is not available to voice"
        value = lambda a: re.fullmatch(r"[+-]?\d+(\.\d+)?[+-]?|[A-Za-z]+", a) is not None
        return _shape(rest[1:], [value, OPT]) and "playerctl takes one value after the command"
    if prog == "brightnessctl":
        rest = argv[1:]
        while rest and rest[0] in {"-d", "--device", "-c", "--class"} and len(rest) > 1 and _name(rest[1]):
            rest = rest[2:]
        if not rest or rest[0] not in {"set", "get", "max", "info", "list"}:
            return "that brightnessctl command is not available to voice"
        spec = [lambda a: re.fullmatch(r"\d+%?[+-]?|[+-]\d+%?", a) is not None] if rest[0] == "set" else []
        return _shape(rest[1:], spec) and "brightnessctl set takes one level"
    if prog == "voxtype":
        if len(argv) < 2 or argv[1] not in VOXTYPE_VERBS:
            return "voxtype may only be asked to record or for its status"
        return _shape(argv[2:], [_lit("start", "stop", "toggle", "cancel"), OPT]) and "voxtype takes one word after the command"
    if prog == "notify-send":
        rest, texts = argv[1:], 0
        while rest:
            if rest[0] in {"-t", "-u", "-a", "-i", "--expire-time", "--urgency", "--app-name", "--icon"} and len(rest) > 1 and _text(rest[1]):
                rest = rest[2:]
            elif rest[0] in {"-e", "--transient"}:
                rest = rest[1:]
            elif _text(rest[0]) and texts < 2:
                rest, texts = rest[1:], texts + 1
            else:
                return f"notify-send: unexpected argument {rest[0]!r}"
        return None if texts else "notify-send needs a message"
    if prog == "ip":
        rest = argv[1:]
        while rest and rest[0] in {"-br", "-brief", "-4", "-6", "-j", "-json", "-c", "-color"}:
            rest = rest[1:]
        if not rest or rest[0] not in {"addr", "address", "a", "link", "l", "route", "r", "neigh", "neighbour", "n", "rule"}:
            return "ip may only show addresses, links, routes, neighbours or rules"
        if len(rest) > 5 or any(a.startswith("-") or a in IP_MUTATING for a in rest[1:]):
            return "ip may only show network state"
        return None
    if prog == "date":
        bad = [a for a in argv[1:] if not (a.startswith("+") or a in {"-u", "--utc", "-R", "--rfc-email", "-I", "--iso-8601"})]
        return f"date: unexpected argument {bad[0]!r}" if bad else None
    if prog == "cal":
        bad = [a for a in argv[1:] if not (a in {"-m", "-y", "-3", "-1"} or _num(a))]
        return f"cal: unexpected argument {bad[0]!r}" if bad or len(argv) > 4 else None
    if prog == "uptime":
        bad = [a for a in argv[1:] if a not in {"-p", "--pretty", "-s", "--since"}]
        return f"uptime: unexpected argument {bad[0]!r}" if bad else None
    if prog == "free":
        bad = [a for a in argv[1:] if a not in {"-h", "--human", "-m", "-g", "--mega", "--giga"}]
        return f"free: unexpected argument {bad[0]!r}" if bad else None
    if prog in {"df", "du"}:
        letters = set("hHTi") if prog == "df" else set("hsca")
        longs = {"--human-readable"} | ({"--summarize"} if prog == "du" else set())
        rest = argv[1:]
        while rest and (rest[0] in longs or (re.fullmatch(r"-[A-Za-z]+", rest[0]) and set(rest[0][1:]) <= letters)):
            rest = rest[1:]
        if prog == "du" and rest[:1] == ["-d"] and len(rest) > 1 and _num(rest[1]):
            rest = rest[2:]
        if len(rest) > 3 or any(not _path(a) for a in rest):
            return f"{prog} takes a few paths, not options"
        return None
    return None
