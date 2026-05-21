import rustypot

from constants import motor_id_dict

controller = rustypot.Xl330PyController(serial_port='/dev/ttyAMA0', baudrate=1000000, timeout=0.1)
controller.sync_write_torque_enable(list(motor_id_dict.values()), [False] * len(list(motor_id_dict.values())))

print("All motors stopped.")