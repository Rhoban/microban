# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

"""Local simulation entry point — never deployed to the robot: the robot's program on Rhoban's robot simulator
(microban_sim), the robot on the floor, or on the hackathon's climbing wall (climbing_sim). docs/simulation.md.

Usage:
    make sim                    # the classic robot on the floor (VARIANT=climber: the climbing one)
    make sim WALL=N2            # the climbing robot hanging on the hackathon's wall N2 (START=floor: in front of it)
"""

import argparse

from scheduler import Scheduler
from telemetry import Telemetry
from moves.move import CLASSIC, CLIMBER
from sim.mujoco_input import MuJoCoInputSource
from sim.sim_controller import SimController
from moves.rotate_head import RotateHeadMove
from moves.squat import SquatMove
from moves.walk import WalkMove
from moves.controller import ControllerMove
from moves.discover import with_discovered_moves


def main() -> None:
    parser = argparse.ArgumentParser(description="Run microban scheduler in MuJoCo simulation.")
    parser.add_argument("--hz", type=float, default=50.0, metavar="FREQ", help="Scheduler frequency in Hz (default: 50)")
    parser.add_argument("--variant", default=CLASSIC, choices=[CLASSIC, CLIMBER],
                        help="the robot's version on the floor: walking or climbing forearms and feet")
    parser.add_argument("--controller", default=None, help="a Controller file (moves/controller.py), started with [c]")
    parser.add_argument("--wall", default=None, metavar="WALL", help="on the hackathon's climbing wall (the simulator "
                        "cloned next to this folder): N1, N2, N3 or a wall JSON file; the climbing robot")
    parser.add_argument("--start", default="hang", choices=["hang", "floor"],
                        help="--wall: hanging on the start holds, or standing in front of the wall")
    args = parser.parse_args()

    if args.wall:
        try:
            from climbing_sim import ClimbingSim
        except ImportError:
            raise SystemExit("The hackathon's simulator is not found: clone it next to this folder (git clone "
                             "https://github.com/rock-climbing-robots/simulator ../simulator), see docs/simulation.md")
        sim = ClimbingSim(args.wall, cameras=[])
        start, variant = (sim.reset if args.start == "floor" else sim.reset_hanging), CLIMBER
    else:
        from microban_sim import MicrobanSim
        sim = MicrobanSim(args.variant)
        start, variant = sim.reset, args.variant

    input_source = MuJoCoInputSource(move_keys={"h": "head", "s": "squat", "v": "walk", "c": "controller"})
    controller = SimController(sim, start, key_callback=input_source.key_callback, reset_source=input_source)
    input_source.set_viewer_opt(controller.viewer_opt)

    scheduler = Scheduler(
        frequency_hz=args.hz,
        controller=controller,
        input_source=input_source,
        moves=with_discovered_moves(controller, {
            "head": RotateHeadMove(),
            "squat": SquatMove(),
            **({"controller": ControllerMove(args.controller, controller)} if args.controller else {}),
            "walk": WalkMove(controller=controller),
        }),
        telemetry=Telemetry(controller),            # the dashboard works on the simulation too (make dashboard HOST=127.0.0.1)
        variant=variant,                            # the moves made for this version (Move.variants)
    )
    scheduler.run()


if __name__ == "__main__":
    main()
