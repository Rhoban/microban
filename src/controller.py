from typing import Protocol


class ControllerProtocol(Protocol):
    """Structural interface shared by RobotController, FakeController, and MuJoCoController.

    All positions are expressed in radians. Implementations are
    responsible for any hardware-level sign or unit conversion internally.
    """

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None: ...

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None: ...

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None: ...

    def sync_read_present_position(self, ids: list[int]) -> list[float]: ...

    def read_present_position(self, motor_id: int) -> float: ...

    def read_present_input_voltage(self, motor_id: int) -> float: ...
