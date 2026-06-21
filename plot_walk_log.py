import matplotlib.pyplot as plt
import json

if __name__ == "__main__":
    with open("logs/walk_log.json", "r") as f:
        log = json.load(f)

    motor_positions = log["position"]
    motor_voltages = log["voltage"]

    time = [0.02 * i for i in range(len(motor_positions["head"]))]

    plt.figure(figsize=(12, 6))
    plt.subplot(2, 1, 1)
    for name in motor_positions.keys():
        plt.plot(time, motor_positions[name], label=f"Observed {name}")
    plt.xlabel("Time (s)")
    plt.ylabel("Motor Position (rad)")
    plt.title("Motor Positions vs Time")
    plt.legend()
    plt.grid()

    plt.subplot(2, 1, 2)
    for name in motor_voltages.keys():
        plt.plot(time, motor_voltages[name], label=f"Observed {name}")
    plt.xlabel("Time (s)")
    plt.ylabel("Motor Voltage (V)")
    plt.title("Motor Voltages vs Time")
    plt.legend()
    plt.grid()

    plt.tight_layout()
    plt.show()