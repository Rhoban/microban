# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

"""Local simulation entry point — never deployed to the robot.

Usage:
    uv run --group sim src/sim/sim_main.py --hz 50
    make sim 
"""

import argparse

from scheduler import Scheduler
from telemetry import Telemetry
from moves.move import CLASSIC, CLIMBER
from sim.mujoco_input import MuJoCoInputSource
from sim.mujoco_controller import MuJoCoController
from moves.rotate_head import RotateHeadMove
from moves.squat import SquatMove
from moves.walk import WalkMove
from moves.controller import ControllerMove
from moves.discover import with_discovered_moves


def main() -> None:
    parser = argparse.ArgumentParser(description="Run microban scheduler in MuJoCo simulation.")
    parser.add_argument("--hz", type=float, default=50.0, metavar="FREQ", help="Scheduler frequency in Hz (default: 50)")
    parser.add_argument("--delay-act", type=int, default=2, metavar="STEPS", help="Actuation delay in simulator steps (1 step = 0.005 s)")
    parser.add_argument("--delay-pos", type=int, default=0, metavar="TICKS", help="Motor position read delay in scheduler ticks (1 tick = 20 ms at 50 Hz)")
    parser.add_argument("--delay-vel", type=int, default=1, metavar="TICKS", help="Motor velocity read delay in ticks")
    parser.add_argument("--delay-gyro", type=int, default=3, metavar="TICKS", help="Gyro read delay in ticks")
    parser.add_argument("--delay-quat", type=int, default=4, metavar="TICKS", help="Quaternion (projected gravity) read delay in ticks")
    parser.add_argument("--trunk-com-offset", type=float, nargs=3, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"), help="CoM offset on trunk body in meters (body frame)")
    parser.add_argument("--climb", action="store_true", help="the climbing forearms and feet (microban_model)")
    parser.add_argument("--controller", default=None, help="a Controller file (moves/controller.py), started with [c]")
    parser.add_argument("--wall", default=None, metavar="WALL", help="on the climbing wall of the hackathon's simulator "
                        "(../simulator): N1, N2, N3 or a wall JSON file; the climbing robot")
    parser.add_argument("--start", default="hang", choices=["hang", "floor"],
                        help="--wall: hanging on the start holds, or standing in front of the wall")
    args = parser.parse_args()

    input_source = MuJoCoInputSource(move_keys={"h": "head", "s": "squat", "v": "walk", "c": "controller"})
    if args.wall:
        from sim.wall_controller import WallController
        controller = WallController(args.wall, args.start, key_callback=input_source.key_callback,
                                    reset_source=input_source, delay_pos_ticks=args.delay_pos,
                                    delay_vel_ticks=args.delay_vel, delay_gyro_ticks=args.delay_gyro,
                                    delay_quat_ticks=args.delay_quat)
    else:
        controller = MuJoCoController(
            climb=args.climb,
            key_callback=input_source.key_callback,
            reset_source=input_source,
            delay_act_steps=args.delay_act,
            delay_pos_ticks=args.delay_pos,
            delay_vel_ticks=args.delay_vel,
            delay_gyro_ticks=args.delay_gyro,
            delay_quat_ticks=args.delay_quat,
            trunk_com_offset=tuple(args.trunk_com_offset),
        )
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
        variant=CLIMBER if args.climb or args.wall else CLASSIC,   # the moves made for this version (Move.variants)
    )
    scheduler.run()


if __name__ == "__main__":
    main()