# SPDX-License-Identifier: GPL-3.0-or-later
"""Input for the robot service (no terminal): a gamepad when one is connected, at any time; nothing otherwise (the
dashboard starts and stops the moves then)."""
import os
import time

from input.gamepad_input import GamepadInputSource, find_gamepad_path
from input.input_source import InputSource, UserInput

LOOK_EVERY_S = 2.0


class HotplugGamepadInputSource(InputSource):
    def __init__(self, button_moves: dict[str, str]) -> None:
        self._button_moves = button_moves
        self._pad: GamepadInputSource | None = None
        self._path: str | None = None
        self._last_look = 0.0

    def start(self) -> None:
        self._look()

    def stop(self) -> None:
        if self._pad is not None:
            self._pad.stop()
            self._pad = None

    def _look(self) -> None:
        self._last_look = time.monotonic()
        path = find_gamepad_path()
        if path is None:
            return
        try:
            pad = GamepadInputSource(button_moves=self._button_moves)
            pad.start()
        except OSError:
            return
        self._pad, self._path = pad, path
        print(f"Gamepad connected ({path})", end="\r\n", flush=True)

    def read(self) -> UserInput:
        if self._pad is not None and not os.path.exists(self._path):          # disconnected
            self.stop()
            print("Gamepad disconnected", end="\r\n", flush=True)
        if self._pad is None:
            if time.monotonic() - self._last_look > LOOK_EVERY_S:
                self._look()
            if self._pad is None:
                return UserInput()
        return self._pad.read()
