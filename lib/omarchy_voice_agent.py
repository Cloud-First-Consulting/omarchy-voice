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
to; gemini's deny-all policy rule, though documented to match every tool,
could not be checked on this machine; and opencode honours a catch-all deny
at the wire, but merges per-agent permission rules from the user's own
config over it, so a rule they already have can hand a tool back. None of
those is an engine here. claude is the one whose invocation ignores every
settings file and names its tool set outright.
An agent joins the table when its tool-free form has been checked, by
asking it to use a tool, or better, by reading the request it sends.
They still work for "ask the agent to ..." - a deliberate handoff through
`omarchy agent prompt`, started only on a sentence the user spoke - and
`claude` answers instead when it is installed, with a note saying so.

Every agent also runs from an empty runtime directory rather than $HOME, so
none of them picks up a CLAUDE.md, AGENTS.md or project config that happens
to be lying around.

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

from omarchy_voice_rundir import private_dir, run_dir

HERE = pathlib.Path(__file__).resolve().parent

ADAPTERS = {
    # --tools "" removes every built-in tool; --restricted removes the ones
    # that run code or fetch and ignores the user's settings files as well;
    # --strict-mcp-config with no --mcp-config removes every MCP server;
    # --setting-sources "" ignores the settings files that could add any of
    # it back; --permission-mode manual refuses anything that would still
    # ask. Asked to run `id` with Bash and to read a file with Read, it
    # answered "NO TOOLS" to both.
    "claude": {
        "argv": lambda p, m: ["claude", "-p", p, "--output-format", "json",
                              "--max-turns", "1", "--restricted", "--tools", "",
                              "--strict-mcp-config", "--setting-sources", "",
                              "--permission-mode", "manual",
                              "--no-session-persistence",
                              "--disable-slash-commands"]
                             + (["--model", m] if m else []),
        # The flags the invocation depends on. If the installed CLI does not
        # list every one of them, it is not asked at all - never asked in a
        # looser form.
        "required_flags": ("--restricted", "--tools", "--strict-mcp-config",
                           "--setting-sources", "--permission-mode"),
        "envelope": "json",
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
    "opencode": "merges per-agent tool permissions from the user's own config over any catch-all rule",
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
    """An empty directory of our own for the agent to run in, inside the
    private runtime directory (see omarchy_voice_rundir)."""
    return private_dir(run_dir() / "agent")


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


_flags_ok = {}


def supports_required_flags(agent):
    """True if the installed CLI's own --help lists every flag the tool-free
    invocation relies on. Checked once per process."""
    if agent not in _flags_ok:
        needed = ADAPTERS[agent].get("required_flags", ())
        try:
            out = subprocess.run([agent, "--help"], capture_output=True, text=True,
                                 timeout=20, stdin=subprocess.DEVNULL)
            text = (out.stdout or "") + (out.stderr or "")
        except (OSError, subprocess.TimeoutExpired):
            text = ""
        _flags_ok[agent] = all(flag in text for flag in needed)
    return _flags_ok[agent]


def ask(prompt, model=None, timeout=60):
    """Put one question to the agent. Returns (reply_text, error)."""
    agent, note = resolve()
    if agent is None:
        return None, note
    if not supports_required_flags(agent):
        return None, f"{agent} is installed but does not offer the flags needed to ask it without tools; not asking"

    cwd = workdir()
    argv = ADAPTERS[agent]["argv"](prompt, model if agent == "claude" else None)
    assert not any(a in PERMISSIVE for a in argv), "a permissive flag reached an agent"
    try:
        # stdin closed, never inherited. Several of these read stdin when it is
        # open and append it to the prompt, so an inherited terminal would have
        # them sitting there waiting for input that is never coming while the
        # user waits for an answer.
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd,
                              timeout=timeout, stdin=subprocess.DEVNULL)
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
