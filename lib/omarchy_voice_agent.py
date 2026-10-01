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

An agent whose CLI offers no documented way to withhold its tools is not in
the table. It still works for "ask the agent to ..." - that is a deliberate
handoff through `omarchy agent prompt`, started only on a sentence the user
spoke - but it cannot be the engine behind the planner or the manual, and
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
GEMINI_POLICY = HERE.parent / "config" / "gemini-no-tools.toml"

# Every tool opencode knows, switched off. Written as the project config of
# the directory the agent runs in, which opencode merges over the user's own
# config - so their provider and model stay, and only the tools go.
OPENCODE_NO_TOOLS = {
    "$schema": "https://opencode.ai/config.json",
    "tools": {name: False for name in (
        "bash", "read", "write", "edit", "patch", "glob", "grep", "list",
        "webfetch", "websearch", "todowrite", "todoread", "task", "skill")},
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
    # Denial rules take precedence over everything in copilot, including
    # --allow-all-tools; shell(), write() and url() without an argument match
    # every shell command, every file write and every URL. Built-in MCP
    # servers are off. The same two probes answered "NO TOOLS".
    "copilot": {
        "argv": lambda p, m: ["copilot", "-p", p, "-s",
                              "--deny-tool", "shell", "--deny-tool", "write",
                              "--deny-tool", "url", "--disable-builtin-mcps"],
        "envelope": "text",
        "access": "no shell, no writes, no network, no MCP",
        "verified": True,
    },
    # opencode merges the project config in its working directory over the
    # user's; OPENCODE_NO_TOOLS is written there before every call. The
    # `tools` map is documented in opencode's config schema. Not probed: the
    # only opencode account here is its free tier, and that provider refuses
    # a request once the tools are gone ("can only be used from within
    # OpenCode"), so the probe never reached a model.
    "opencode": {
        "argv": lambda p, m: ["opencode", "run", "--dir", str(workdir()), p],
        "envelope": "text",
        "access": "no tools (project config)",
        "verified": False,
    },
    # A user-tier policy rule that denies every tool. --approval-mode plan
    # alone is not enough: gemini overrides it in a folder it does not trust,
    # which the runtime directory is not. Flags verified to parse; the deny
    # itself could not be exercised here (no Gemini account).
    "gemini": {
        "argv": lambda p, m: ["gemini", "-p", p, "--policy", str(GEMINI_POLICY),
                              "--approval-mode", "plan"],
        "envelope": "text",
        "access": "no tools (policy)",
        "verified": False,
    },
    # Read-only sandbox: the shell tool exists but may not write or reach the
    # network. --skip-git-repo-check because exec refuses to run outside a
    # directory it trusts. Flags verified to parse; no OpenAI account here.
    "codex": {
        "argv": lambda p, m: ["codex", "exec", "--skip-git-repo-check",
                              "--sandbox", "read-only", p],
        "envelope": "text",
        "access": "read-only sandbox",
        "verified": False,
    },
    # plan mode is documented as read-only; the sandbox is turned on as well.
    # Flags verified to parse; no Cursor account here.
    "cursor-agent": {
        "argv": lambda p, m: ["cursor-agent", "-p", "--mode", "plan",
                              "--sandbox", "enabled", p],
        "envelope": "text",
        "access": "read-only (plan mode)",
        "verified": False,
    },
    # --tools takes the built-in tools to allow, and is given none; plan mode
    # is read-only on top; no web search, no subagents, one turn. Flags
    # verified to parse; no xAI account here.
    "grok": {
        "argv": lambda p, m: ["grok", "-p", p, "--tools", "",
                              "--permission-mode", "plan",
                              "--disable-web-search", "--no-subagents",
                              "--max-turns", "1"],
        "envelope": "text",
        "access": "no tools (plan mode)",
        "verified": False,
    },
}

# Agents Omarchy can launch but which cannot answer here. pi, omp, openclaw,
# hermes and muse have no one-shot mode. crush has one, but no documented way
# to withhold its tools from it, and Omarchy's own launcher notes that
# `crush run` never prompts - which is the opposite of what this path needs.
UNSUPPORTED = {"pi", "omp", "openclaw", "hermes", "muse", "crush"}

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
            return "claude", f"{chosen} cannot be asked without its tools; answered with claude"
        if chosen not in ADAPTERS:
            return "claude", f"{chosen} is not known here; answered with claude"
        return "claude", f"{chosen} is not installed; answered with claude"

    if chosen in UNSUPPORTED:
        return None, f"{chosen} cannot be asked a single question without its tools, and claude is not installed"
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
