"""Shared on-screen feedback for the voice tools.

Kept out of bin/ because it is a module, not a command. Both omarchy-voice-help
and omarchy-voice-diagnose import it by resolving their own path first, which
follows the symlink from ~/.local/bin back into the repo.
"""

import subprocess
import threading


class Progress:
    """A single notification that animates in place while work is happening.

    Answering takes several seconds and diagnosing the better part of a minute -
    two model calls with half a dozen probes between them - and a silent minute
    is indistinguishable from having crashed. The notification server hands back
    an id, so each frame replaces the previous one rather than stacking a dozen
    copies of itself down the side of the screen.

    The stage text matters more than the spinner. "reading the journal" says it
    is doing something specific and roughly how far through it is; a bare
    spinner only says it has not died yet.
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    INTERVAL = 0.4

    def __init__(self, title, enabled=True, glyph="󰋗"):
        self.title = title
        self.glyph = glyph
        self.enabled = enabled
        self.label = "starting"
        self.id = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if not self.enabled:
            return self
        try:
            out = subprocess.run(
                ["omarchy-notification-send", "-p", "-g", self.glyph,
                 self.title, self.label, "-t", "120000"],
                capture_output=True, text=True, timeout=10)
            self.id = out.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            self.enabled = False
            return self
        if not self.id:
            # No id means no way to replace it, and a spinner that stacks is
            # worse than no spinner at all.
            self.enabled = False
            return self
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stage(self, label):
        self.label = label

    def _send(self, glyph, title, body, timeout="120000"):
        if not (self.enabled and self.id):
            return
        try:
            subprocess.run(
                ["omarchy-notification-send", "-r", self.id, "-g", glyph,
                 title, body, "-t", timeout],
                check=False, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _spin(self):
        frame = 0
        while not self._stop.wait(self.INTERVAL):
            self._send(self.glyph, self.title,
                       f"{self.FRAMES[frame % len(self.FRAMES)]}  {self.label}")
            frame += 1

    def finish(self, glyph, title, body):
        """Land the result in the notification the spinner was already using.

        So the thing being watched turns into the answer, rather than the answer
        arriving as a second notification beside a spinner still going round.
        Returns False if there was nothing to replace, so the caller can send an
        ordinary notification instead.
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if not (self.enabled and self.id):
            return False
        self._send(glyph, title, body, timeout="12000")
        return True
