# SPDX-License-Identifier: GPL-3.0-or-later
"""What the moves print(): to the terminal as before (make run, make robot-service-logs), and to the live dashboard's
events, "move: line", so that a print shows in the page.

The scheduler runs each call of a move (start, step, stopping, on_key, on_option) inside ``capture(name)``. At most
MAX_LINES_PER_S lines a second per move go to the dashboard (a print in step() would be 50 a second): the others are
counted, and said at most once a second. Nothing is sent while no dashboard listens.
"""
import contextlib
import io
import sys
import time

MAX_LINES_PER_S = 10
MAX_CHARS = 300             # a longer line is cut in the dashboard (the terminal gets it whole)


class MoveOutput:
    def __init__(self, telemetry=None):
        self.telemetry = telemetry
        self._budget: dict[str, list[float]] = {}     # move -> [lines it may send now, last refill time]
        self._skipped: dict[str, int] = {}
        self._said: dict[str, float] = {}             # move -> when the lines not shown were last said

    @contextlib.contextmanager
    def capture(self, name: str):
        """Run the block with print() going to this move's output."""
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                yield
        finally:
            text = buf.getvalue()
            if text:
                self._emit(name, text)

    def _emit(self, name: str, text: str) -> None:
        # the robot's terminal is in raw mode (keyboard input): a line ends with \r\n there
        sys.stdout.write(text.replace("\r\n", "\n").replace("\n", "\r\n"))
        sys.stdout.flush()
        if self.telemetry is None:
            return
        now = time.monotonic()
        tokens, last = self._budget.get(name, [MAX_LINES_PER_S, now])
        tokens = min(MAX_LINES_PER_S, tokens + (now - last) * MAX_LINES_PER_S)
        for line in text.splitlines():
            if not line.strip():
                continue
            if tokens < 1:
                self._skipped[name] = self._skipped.get(name, 0) + 1
                continue
            if self._skipped.get(name) and now - self._said.get(name, 0.0) >= 1.0:
                self.telemetry.event(f"{name}: ({self._skipped.pop(name)} printed lines not shown here: "
                                     f"too many a second; all in the robot's log, make robot-service-logs, or the terminal of make run / make sim)")
                self._said[name] = now
                tokens -= 1
                if tokens < 1:
                    self._skipped[name] = 1                # this line: said with the next note
                    continue
            self.telemetry.event(f"{name}: {line[:MAX_CHARS]}")
            tokens -= 1
        self._budget[name] = [tokens, now]
