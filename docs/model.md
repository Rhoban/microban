# Robot model

The robot's model is the package [microban_model](https://github.com/Rhoban/microban_model) (a dependency: MuJoCo XML
and URDF of Microban v2, in two versions that differ only by the forearms and the feet: walking, the default, and
climbing). The simulation runs it (Rhoban's microban_sim: `make sim`, `VARIANT=climber`, [simulation.md](simulation.md)),
the squat's inverse kinematics reads its URDF, the dashboard shows it (`make dashboard`).

Joint angles everywhere (model, code, motors) have the motors' zero as their zero (Dynamixel Wizard: 180 deg): the
shoulder pitch holds the arm forward at 0, along the body at +90 deg (`NEUTRAL_POSE`). The walking policy was trained
on Microban v1 (arm down at 0): `moves/walk.py` turns its default pose by a quarter turn on the shoulders, which leaves
its inputs and outputs unchanged.
