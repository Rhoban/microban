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
from moves.rotate_head import RotateHeadMove
from moves.squat import SquatMove


def main() -> None:
    parser = argparse.ArgumentParser(description="Run microban scheduler in MeshCat kinematic viewer.")
    parser.add_argument("--hz", type=float, default=50.0, metavar="FREQ", help="Scheduler frequency in Hz (default: 50)")
    args = parser.parse_args()

    controller = PlacoViewerController(model_path=str(microban_model.MJCF_DIR), dt=1.0 / args.hz)
    input_source = KeyboardInputSource(move_keys={"h": "head", "s": "squat"})

    scheduler = Scheduler(
        frequency_hz=args.hz,
        controller=controller,
        input_source=input_source,
        moves={
            "head": RotateHeadMove(),
            "squat": SquatMove(),
        },
        variant=CLASSIC,
    )
    scheduler.run()


if __name__ == "__main__":
    main()