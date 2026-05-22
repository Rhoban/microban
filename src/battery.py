"""Read and print the battery voltage from any motor on the bus."""

from rustypot import Xl330PyController

# 2S LiPo voltage thresholds
BATTERY_WARN_V: float = 7.2              # print warning below this value
BATTERY_CRITICAL_V: float = 7.0          # stop the robot below this value
BATTERY_PROBE_IDS: list[int] = [11, 21]  # one per bus
BATTERY_VOLTAGE_OFFSET: float = 0.3      # calibration offset (measured: actual - reported)

def main() -> None:
    controller = Xl330PyController(
        serial_port="/dev/ttyAMA0", baudrate=1_000_000, timeout=0.1
    )
    controller.sync_write_status_return_level(BATTERY_PROBE_IDS, [1] * len(BATTERY_PROBE_IDS))

    readings = []
    for probe_id in BATTERY_PROBE_IDS:
        raw = controller.read_present_input_voltage(probe_id)
        voltage_raw = raw[0] if isinstance(raw, (list, tuple)) else raw
        readings.append(voltage_raw * 0.1)
        print(f"  Motor {probe_id}: {voltage_raw * 0.1:.2f} V")

    voltage_v = sum(readings) / len(readings) + BATTERY_VOLTAGE_OFFSET
    print(f"Battery voltage (avg, corrected): {voltage_v:.2f} V")


if __name__ == "__main__":
    main()
