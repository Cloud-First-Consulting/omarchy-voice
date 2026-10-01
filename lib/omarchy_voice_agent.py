"""Ask the machine's chosen coding agent exactly one question, with no tools.

Both the planner and the Omarchy manual want the same narrow thing: one prompt
in, one reply out, no session, no terminal - and no hands. The prompt the
agent is given contains text that came from somewhere untrusted: the titles
of open windows (a web page sets its own), the elements on a page, lines out
of the journal. A model can be talked into things by text it is shown, and a
coding agent with its tools available would then be talked into *doing* them
- reading a file, running a command, fetching a URL - inside the agent, before
anything here gets to vet the reply. So every agent below is invoked in a
form that withholds its tools, and the reply is the only thing it can produce.

Each agent spells that differently, and the flag that launches an agent to
work interactively is rarely the flag that answers one question and exits.
Both live in the table below:

  argv      how to ask one question, tool-free, and have the process exit
  envelope  whether the reply arrives as text, or wrapped in JSON
  access    what the flags leave the agent able to do, in one phrase
  verified  whether that was confirmed by asking it to use a tool and
            watching it fail, on a logged-in install of that CLI

"Read-only" is not enough. A sandbox that still lets the agent read files
lets injected text pull a private file into the model's context, and the
model's reply is spoken aloud and written to a cache. So an agent is in the
table only when its CLI has a documented way to leave it with *no* tools,
reads included. codex's read-only sandbox, cursor-agent's plan mode and
grok's plan mode all keep file reads; grok's --tools "" is not documented
as "none"; crush has no such flag at all; copilot, with every tool it
lists excluded and url access denied, still fetched a web page when asked
to; and gemini's deny-all policy rule, though documented to match every
tool, could not be checked on this machine. None of those is an engine here.
An agent joins the table when its tool-free form has been checked, by
asking it to use a tool, or better, by reading the request it sends.
They still work for "ask the agent to ..." - a deliberate handoff through
`omarchy agent prompt`, started only on a sentence the user spoke - and
`claude` answers instead when it is installed, with a note saying so.

Every agent also runs from an empty runtime directory rather than $HOME, so
none of them picks up a CLAUDE.md, AGENTS.md or project config that happens
to be lying around. For opencode that directory is also where its tool-free
project configuration is written.

Only the envelope is unwrapped here. Finding the JSON object the caller asked
the model for is the caller's job, because it already has to do that anyway:
agents add banners, and models add prose around JSON no matter how firmly they
are told not to.
"""

import json
import os
import pathlib
import shutil
import subprocess

HERE = pathlib.Path(__file__).resolve().parent

# opencode's catch-all permission rule, which it applies to every tool by
# name - built-in, MCP server tools (registered under the server's name as a
# prefix) and plugin tools alike - before the model is sent a single tool
# definition. The deprecated `tools` map says the same thing a second way.
# Delivered twice: as the project config of the directory the agent runs in,
# and inline through OPENCODE_CONFIG_CONTENT, which opencode merges above the
# project, custom and global configs - so nothing in the user's own config
# can put a tool back.
OPENCODE_NO_TOOLS = {
    "$schema": "https://opencode.ai/config.json",
    "permission": {"*": "deny"},
    "tools": {"*": False},
}

ADAPTERS = {
    # --tools "" removes every built-in tool; --strict-mcp-config with no
    # --mcp-config removes every MCP server; --setting-sources "" ignores the
    # settings files that could add either back. Asked to run `id` with Bash
    # and to read a file with Read, it answered "NO TOOLS" to both.
    "claude": {
        "argv": lambda p, m: ["claude", "-p", p, "--output-format", "json",
                              "--max-turns", "1", "--tools", "",
                              "--strict-mcp-config", "--setting-sources", "",
                              "--no-session-persistence",
                              "--disable-slash-commands"]
                             + (["--model", m] if m else []),
        "envelope": "json",
        "access": "no tools",
        "verified": True,
    },
    # Checked by pointing opencode at a local stand-in for a model endpoint
    # and reading the tool definitions it sent. Unrestricted: bash, edit,
    # glob, grep, read, skill, task, todowrite, webfetch, write, and - with
    # an MCP server configured outside the project - that server's tool too.
    # With the rule above: an empty list, in every request, MCP included.
    "opencode": {
        "argv": lambda p, m: ["opencode", "run", "--dir", str(workdir()), p],
        "envelope": "text",
        "access": "no tools",
        "verified": True,
    },
}

# Agents Omarchy can launch but which cannot answer here, and why.
UNSUPPORTED = {
    "pi": "has no one-shot mode",
    "omp": "has no one-shot mode",
    "openclaw": "has no one-shot mode",
    "hermes": "has no one-shot mode",
    "muse": "has no one-shot mode",
    "crush": "has no way to be asked without its tools",
    "gemini": "has a deny-all policy file, but it could not be checked here",
    "copilot": "still reaches the network with every tool excluded and url denied",
    "codex": "keeps file reads and a shell even in its read-only sandbox",
    "cursor-agent": "keeps file reads in plan mode, and has no tool-free mode",
    "grok": "keeps file reads in plan mode, and --tools \"\" is not documented as none",
}

# Flags that would hand an agent its tools back. Nothing in ADAPTERS may
# contain one; tests/test_agent.py checks.
PERMISSIVE = {
    "--allow-all", "--allow-all-tools", "--allow-all-paths", "--allow-all-urls",
    "--yolo", "--full-auto", "--force", "--always-approve", "--auto",
    "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox", "--approve-for-me",
    "--approve-mcps", "--autopilot", "bypassPermissions", "danger-full-access",
}


def workdir():
    """An empty directory of our own for the agent to run in."""
    base = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/omarchy-voice-{os.getuid()}")
    path = base / "omarchy-voice" / "agent"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def configured():
    """The agent Omarchy is set to use, or "" when the user has not picked one."""
    try:
        out = subprocess.run(["omarchy-default-agent"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def resolve():
    """Which agent will answer, and why it is not the configured one if it is not.

    Returns (agent, note). `agent` is None when nothing here can answer, in
    which case `note` is what to tell the user.
    """
    override = os.environ.get("OMARCHY_VOICE_AGENT", "").strip()
    chosen = override or configured()

    if chosen and chosen in ADAPTERS and shutil.which(ADAPTERS[chosen]["argv"]("", None)[0]):
        return chosen, ""

    # Fall back rather than fail: an agent that cannot answer one question can
    # still be the user's agent for everything else, and the manual working is
    # worth more than being pedantic about which model wrote the sentence.
    if shutil.which("claude"):
        if not chosen:
            return "claude", ""
        if chosen in UNSUPPORTED:
            return "claude", f"{chosen} {UNSUPPORTED[chosen]}; answered with claude"
        if chosen not in ADAPTERS:
            return "claude", f"{chosen} is not known here; answered with claude"
        return "claude", f"{chosen} is not installed; answered with claude"

    if chosen in UNSUPPORTED:
        return None, f"{chosen} {UNSUPPORTED[chosen]}, and claude is not installed"
    if chosen and chosen not in ADAPTERS:
        return None, f"{chosen} is not one of the agents this can ask"
    if not chosen:
        return None, "no coding agent is set: omarchy default agent <name>"
    return None, f"{chosen} is not installed"


def ask(prompt, model=None, timeout=60):
    """Put one question to the agent. Returns (reply_text, error)."""
    agent, note = resolve()
    if agent is None:
        return None, note

    cwd = workdir()
    if agent == "opencode":
        try:
            (cwd / "opencode.json").write_text(json.dumps(OPENCODE_NO_TOOLS))
        except OSError:
            return None, "could not write opencode's tool-free configuration"

    argv = ADAPTERS[agent]["argv"](prompt, model if agent == "claude" else None)
    assert not any(a in PERMISSIVE for a in argv), "a permissive flag reached an agent"
    env = dict(os.environ)
    if agent == "opencode":
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(OPENCODE_NO_TOOLS)
    try:
        # stdin closed, never inherited. Several of these read stdin when it is
        # open and append it to the prompt, so an inherited terminal would have
        # them sitting there waiting for input that is never coming while the
        # user waits for an answer.
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd,
                              env=env, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"{agent} took too long"
    except OSError:
        return None, f"{agent} could not be run"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return None, f"{agent} failed: {detail[-1][:120] if detail else 'no output'}"

    out = proc.stdout
    if ADAPTERS[agent]["envelope"] == "json":
        try:
            out = json.loads(out).get("result", "")
        except (json.JSONDecodeError, AttributeError):
            return None, f"could not read {agent}'s reply"
    return out, None
