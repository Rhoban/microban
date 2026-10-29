# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

"""Kinematic viewer entry point — never deployed to the robot.

Usage:
    uv run src/sim/viewer_main.py --hz 25
    make viewer
"""

import argparse

import microban_model

from scheduler import Scheduler
from moves.move import CLASSIC
from input.keyboard_input import KeyboardInputSource
from sim.placo_controller import PlacoViewerController
from constants import MOVE_KEYS
from moves.discover import discover_moves


def main() -> None:
    parser = argparse.ArgumentParser(description="Run microban scheduler in MeshCat kinematic viewer.")
    parser.add_argument("--hz", type=float, default=50.0, metavar="FREQ", help="Scheduler frequency in Hz (default: 50)")
    args = parser.parse_args()

    controller = PlacoViewerController(model_path=str(microban_model.MJCF_DIR), dt=1.0 / args.hz)
    moves = {n: m for n, m in discover_moves().items() if n in ("head", "squat")}   # kinematics only: no walk
    input_source = KeyboardInputSource(move_keys={k: n for k, n in MOVE_KEYS.items() if n in moves})

    scheduler = Scheduler(
        frequency_hz=args.hz,
        controller=controller,
        input_source=input_source,
        moves=moves,
        variant=CLASSIC,
    )
    scheduler.run()


if __name__ == "__main__":
    main()