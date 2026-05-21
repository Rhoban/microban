from rustypot import Xl330PyController
import numpy as np
import time 

from constants import motor_id_dict

controller = Xl330PyController(serial_port='/dev/ttyAMA0', baudrate=1000000, timeout=0.1)

controller.sync_write_torque_enable(list(motor_id_dict.values()), [True] * len(list(motor_id_dict.values())))
controller.sync_write_status_return_level(list(motor_id_dict.values()), [1] * len(list(motor_id_dict.values())))

# Slowly move all motors to their initial positions (0 radians)
duration = 2
motor_init_pos = np.array([controller.read_present_position(id) for id in motor_id_dict.values()])
print("Initializing all motors to 0 radians...")

t = 0
start_time = time.perf_counter()
while t < duration:
    t = time.perf_counter() - start_time
    motor_pos = motor_init_pos + t * (0 - motor_init_pos) / duration
    controller.sync_write_goal_position(list(motor_id_dict.values()), list(motor_pos.flatten()))
controller.sync_write_goal_position(list(motor_id_dict.values()), [0] * len(list(motor_id_dict.values())))
print("All motors initialized to 0 radians.")

for id in motor_id_dict.values():
    print(f"Motor {id} position: {controller.read_present_position(id)}")