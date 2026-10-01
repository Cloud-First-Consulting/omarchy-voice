"""Every agent is asked tool-free, and stays that way.

The flags in lib/omarchy_voice_agent.py were each chosen against the real
CLI's documentation and, where an account was available, confirmed by asking
the agent to run a command and watching it say it could not. These cases keep
a later edit from quietly handing the tools back.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "lib"))
import omarchy_voice_agent as agent  # noqa: E402

# What each adapter must say to its CLI to withhold tools.
REQUIRED = {
    "claude": [("--tools", ""), ("--strict-mcp-config",), ("--setting-sources", ""),
               ("--max-turns", "1")],
    "gemini": [("--policy", str(agent.GEMINI_POLICY))],
    "opencode": [("--dir",)],
}


def has(argv, seq):
    n = len(seq)
    return any(tuple(argv[i:i + n]) == seq for i in range(len(argv) - n + 1))


class ToolFree(unittest.TestCase):
    def test_every_adapter_is_covered_here(self):
        self.assertEqual(set(agent.ADAPTERS), set(REQUIRED))

    def test_required_flags_present(self):
        for name, seqs in REQUIRED.items():
            argv = agent.ADAPTERS[name]["argv"]("hello", None)
            for seq in seqs:
                with self.subTest(agent=name, flag=seq):
                    self.assertTrue(has(argv, seq), f"{name} is missing {seq}: {argv}")

    def test_no_permissive_flag_anywhere(self):
        for name, spec in agent.ADAPTERS.items():
            argv = spec["argv"]("hello", "some-model")
            with self.subTest(agent=name):
                self.assertFalse(set(argv) & agent.PERMISSIVE, f"{name}: {argv}")

    def test_prompt_is_one_argument_never_shell(self):
        prompt = 'say "hi"; $(id) `id` && rm -rf /'
        for name, spec in agent.ADAPTERS.items():
            argv = spec["argv"](prompt, None)
            with self.subTest(agent=name):
                self.assertIn(prompt, argv)
                self.assertNotIn("sh", argv[:2])

    def test_each_adapter_states_its_access(self):
        for name, spec in agent.ADAPTERS.items():
            with self.subTest(agent=name):
                self.assertTrue(spec["access"])
                self.assertIn("verified", spec)

    def test_gemini_policy_denies_everything(self):
        text = agent.GEMINI_POLICY.read_text()
        self.assertIn('toolName = "*"', text)
        self.assertIn('decision = "deny"', text)

    def test_opencode_config_turns_every_tool_off(self):
        self.assertTrue(agent.OPENCODE_NO_TOOLS["tools"])
        self.assertFalse(any(agent.OPENCODE_NO_TOOLS["tools"].values()))

    def test_read_only_is_not_tool_free(self):
        for name in ("crush", "codex", "cursor-agent", "grok", "copilot"):
            with self.subTest(agent=name):
                self.assertIn(name, agent.UNSUPPORTED)
                self.assertNotIn(name, agent.ADAPTERS)


if __name__ == "__main__":
    unittest.main()
