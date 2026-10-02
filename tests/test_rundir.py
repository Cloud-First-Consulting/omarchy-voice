"""The runtime directory is ours or it is not used - in Python and in shell."""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from omarchy_voice_rundir import run_dir  # noqa: E402

SHELL = HERE.parent / "lib" / "omarchy-voice-rundir.sh"


def shell_run_dir(env):
    return subprocess.run(
        ["bash", "-c", f'source "{SHELL}" && omarchy_voice_run_dir'],
        env=env, capture_output=True, text=True)


class RuntimeDirectory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.base))
        os.environ["XDG_RUNTIME_DIR"] = str(self.base)

    def tearDown(self):
        os.environ.pop("XDG_RUNTIME_DIR", None)
        self.tmp.cleanup()

    def test_created_private(self):
        path = run_dir()
        self.assertEqual(path, self.base / "omarchy-voice")
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o700")
        out = shell_run_dir(self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), str(path))

    def test_existing_loose_mode_is_tightened(self):
        (self.base / "omarchy-voice").mkdir(mode=0o755)
        self.assertEqual(oct(run_dir().stat().st_mode & 0o777), "0o700")
        (self.base / "omarchy-voice").chmod(0o755)
        self.assertEqual(shell_run_dir(self.env).returncode, 0)
        self.assertEqual(oct((self.base / "omarchy-voice").stat().st_mode & 0o777), "0o700")

    def test_symlink_is_refused(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (self.base / "omarchy-voice").symlink_to(elsewhere)
        with self.assertRaises(OSError):
            run_dir()
        out = shell_run_dir(self.env)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("not a private directory", out.stderr)

    def test_file_in_the_way_is_refused(self):
        (self.base / "omarchy-voice").write_text("")
        with self.assertRaises(OSError):
            run_dir()
        self.assertNotEqual(shell_run_dir(self.env).returncode, 0)

    def test_fallback_is_per_user_and_private(self):
        env = {k: v for k, v in os.environ.items() if k != "XDG_RUNTIME_DIR"}
        os.environ.pop("XDG_RUNTIME_DIR", None)
        fallback = pathlib.Path(f"/tmp/omarchy-voice-{os.getuid()}")
        path = run_dir()
        try:
            self.assertEqual(path, fallback / "omarchy-voice")
            self.assertEqual(oct(fallback.stat().st_mode & 0o777), "0o700")
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o700")
            out = shell_run_dir(env)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout.strip(), str(path))
        finally:
            import shutil
            shutil.rmtree(fallback, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
