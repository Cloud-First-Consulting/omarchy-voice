"""Ask the machine's chosen coding agent exactly one question.

Both the planner and the Omarchy manual want the same narrow thing: one prompt
in, one reply out, no session, no terminal. Every agent spells that
differently, and several spell it in a way that is easy to get wrong - the
flag that launches an agent to work interactively is rarely the flag that
answers a single question and exits.

Omarchy already knows which agent the user picked, so that is where the choice
comes from rather than from a setting of our own. What Omarchy's own launcher
cannot give us is the invocation: `omarchy agent` deliberately starts each
agent in its interactive mode, attached to a terminal, which would hang here.

Two things vary per agent and both live in the table below:

  argv      how to ask one question and have the process exit
  envelope  whether the reply arrives as text, or wrapped in JSON

Only the envelope is unwrapped here. Finding the JSON object the caller asked
the model for is the caller's job, because it already has to do that anyway:
agents add banners, and models add prose around JSON no matter how firmly they
are told not to.

Each invocation below was run against the real CLI. Three returned the
answer outright; the rest parsed their flags and stopped at the machine's own
missing credentials, which is evidence the invocation is right and the account
is not set up, not evidence the invocation is wrong:

    claude      answered
    opencode    answered
    copilot     answered
    codex       reached the API, 401 - no OpenAI credentials here
    gemini      exit 41, no auth method configured
    crush       no providers configured
    cursor-agent  authentication required
    grok        not signed in

So a failure here is almost always "that agent is not logged in", and the
error says which agent, rather than silently handing the question to a
different one and returning an answer the user did not ask for.
"""

import json
import os
import shutil
import subprocess

# Agent -> how to ask it one question.
#
#   argv(prompt, model) -> the command to run
#   envelope            -> "json" if the reply is wrapped, "text" if it is bare
#
# `model` is passed only where an agent takes a model on the command line in a
# form we know. Everywhere else the agent's own configured default is used,
# which is the right behaviour anyway: the user chose that agent and its model.
ADAPTERS = {
    # VERIFIED. --max-turns 1 keeps it to a single answer with no tool use.
    "claude": {
        "argv": lambda p, m: ["claude", "-p", p, "--output-format", "json",
                              "--max-turns", "1"] + (["--model", m] if m else []),
        "envelope": "json",
    },
    # --skip-git-repo-check is not optional here. `codex exec` refuses to run
    # outside a directory it trusts, and the wake listener runs from $HOME, so
    # without it every single question fails with "Not inside a trusted
    # directory" - which reads like a bug in this and is not.
    "codex": {
        "argv": lambda p, m: ["codex", "exec", "--skip-git-repo-check", p],
        "envelope": "text",
    },
    "gemini": {
        "argv": lambda p, m: ["gemini", "-p", p],
        "envelope": "text",
    },
    "opencode": {
        "argv": lambda p, m: ["opencode", "run", p],
        "envelope": "text",
    },
    # Omarchy's own launcher notes that `crush run` never prompts, which is
    # exactly the property this path needs.
    "crush": {
        "argv": lambda p, m: ["crush", "run", p],
        "envelope": "text",
    },
    "cursor-agent": {
        "argv": lambda p, m: ["cursor-agent", "-p", p],
        "envelope": "text",
    },
    "copilot": {
        "argv": lambda p, m: ["copilot", "-p", p, "--allow-all"],
        "envelope": "text",
    },
    "grok": {
        "argv": lambda p, m: ["grok", "-p", p],
        "envelope": "text",
    },
}

# Agents Omarchy can launch but which have no one-shot mode we are confident
# enough to guess at. They still work for "ask the agent to ..." - that hands
# off through `omarchy agent prompt`, which Omarchy maps correctly for every
# agent it supports. They just cannot be the engine behind the phrase table's
# fallback or the Omarchy manual.
UNSUPPORTED = {"pi", "omp", "openclaw", "hermes", "muse"}


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
            return "claude", f"{chosen} has no one-shot mode; answered with claude"
        if chosen not in ADAPTERS:
            return "claude", f"{chosen} is not known here; answered with claude"
        return "claude", f"{chosen} is not installed; answered with claude"

    if chosen in UNSUPPORTED:
        return None, f"{chosen} cannot answer a single question, and claude is not installed"
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

    argv = ADAPTERS[agent]["argv"](prompt, model if agent == "claude" else None)
    try:
        # stdin closed, never inherited. Several of these read stdin when it is
        # open and append it to the prompt, so an inherited terminal would have
        # them sitting there waiting for input that is never coming while the
        # user waits for an answer.
        proc = subprocess.run(argv, capture_output=True, text=True,
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
