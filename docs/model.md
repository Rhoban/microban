# Robot model (Microban v2, Radxa)

`src/model/` holds the robot (Onshape export converted by onshape-to-robot 1.8.3, masses from the CAD) in two versions
that are the same robot except for the forearms and the feet:

| | MuJoCo | URDF (kinematics, PlaCo) |
|---|---|---|
| default: walking forearms and feet | `mjcf/robot.xml`, `mjcf/scene.xml` | `urdf/robot.urdf` |
| climbing mode: ball hands, climbing feet | `mjcf/robot_climb.xml`, `mjcf/scene_climb.xml` | `urdf/robot_climb.urdf` |

Both have the same joints, actuators (XL330 torque motors for the BAM model, class `xl330`) and IMU sensors (site
`imu`). Collisions: boxes for the servos that stick out, the trunk as four hulls, the other parts as convex pieces;
the walking forearms and feet as primitives; the climbing hands and feet with their 25 mm balls (sites `*_ball`).

Joint angles follow the code's convention (the neutral pose, the walk): shoulder pitch 0 is the arm down. The real
shoulder horns are a quarter turn from it, which `MOTOR_OFFSET` (`src/constants.py`) applies on the robot only.
