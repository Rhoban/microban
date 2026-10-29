# Robot model

The robot's model is the package [microban_model](https://github.com/Rhoban/microban_model) (a dependency: MuJoCo XML
and URDF of Microban v2, in two versions that differ only by the forearms and the feet: walking, the default, and
climbing). The simulation runs it (Rhoban's microban_sim: `make sim`, `VARIANT=climber`, [simulation.md](simulation.md)),
the squat's inverse kinematics reads its URDF, the dashboard shows it (`make dashboard`).
The CAD: the walking robot's [Onshape assembly](https://cad.onshape.com/documents/d424992a192a8ce34ffce163/v/7de3e6e40f0e1185d169e6d9/e/b34620a03cc3a684006c5867?renderMode=0&uiState=6a2fccab8e6d9214d2644ca7)
(its parts in `cad/`), the climbing robot's [Onshape document](https://cad.onshape.com/documents/a4bcc28f64d49d0ed7bca71b/w/caf376f744ab0aab1547c516/e/42a4642d1b4dccabe8f99c03).

Joint angles everywhere (model, code, motors) have the motors' zero as their zero (Dynamixel Wizard: 180 deg): the
shoulder pitch holds the arm forward at 0, along the body at +90 deg (`NEUTRAL_POSE`). The walking policy was trained
on Microban v1 (arm down at 0): `moves/walk.py` turns its default pose by a quarter turn on the shoulders, which leaves
its inputs and outputs unchanged.
