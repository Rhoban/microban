.PHONY: sync setup deploy run stop robot-service-enable robot-service-disable robot-service-start robot-service-stop robot-service-logs shutdown voltage imu sim viewer dashboard gamepad-headless-enable gamepad-headless-disable

HOST ?= microban
ID ?=

sync:
	rsync -avz \
		--exclude='.git' \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='cad' \
		--exclude='docs' \
		--exclude='logs' \
		--exclude='src/debug' \
		--exclude='src/sim' \
		--exclude='src/humanoid_dashboard/web' \
		./ $(HOST):microban

setup: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv sync'"

# CONTROLLER=path/to/file.py: your Controller (src/moves/controller.py), started / stopped with [c] (gamepad: B)
CONTROLLER ?=
sim:
	PYTHONPATH=src uv run --group sim src/sim/sim_main.py --hz 50 $(if $(CONTROLLER),--controller $(CONTROLLER))

viewer:
	PYTHONPATH=src uv run src/sim/viewer_main.py --hz 25

run: sync
	$(if $(CONTROLLER),scp $(CONTROLLER) $(HOST):microban/user_controller.py)
	-ssh $(HOST) "systemctl is-active -q microban.service && sudo systemctl stop microban.service && echo 'robot service stopped for this session (make robot-service-start to restart it)'"
	ssh -tt $(HOST) "bash -l -c 'cd microban && $(if $(CONTROLLER),MICROBAN_CONTROLLER=user_controller.py) PYTHONPATH=src .venv/bin/python src/main.py'"

# The robot service: the control loop starts at boot (torque off until a move is launched), for the dashboard
robot-service-enable: setup
	ssh -tt $(HOST) "cd microban && sudo bash systemd/install-robot-service.sh"
robot-service-disable:
	ssh -tt $(HOST) "cd microban && sudo bash systemd/install-robot-service.sh --uninstall"
robot-service-start:
	ssh $(HOST) "sudo systemctl start microban.service"
robot-service-stop:
	ssh $(HOST) "sudo systemctl stop microban.service"
# Your code on the robot, in one command: sends it (as make sync) and restarts the robot's program (the service), which
# reads the moves at start. An open dashboard page then shows the new Moves list by itself (no reload). The torque goes
# off for the few seconds of the restart: hold the robot (or let it sit), never on the wall.
# New Python dependencies (pyproject.toml): make setup first.
deploy: sync
	ssh $(HOST) "sudo systemctl restart microban.service && echo 'robot program restarted with your code'"

robot-service-logs:
	ssh -tt $(HOST) "journalctl -u microban.service -f -n 50"

stop:
	ssh -tt $(HOST) "bash -l -c 'cd microban && PYTHONPATH=src .venv/bin/python src/stop.py'"

voltage: sync
	ssh $(HOST) "bash -l -c 'cd microban && PYTHONPATH=src .venv/bin/python src/voltage.py $(ID)'"

imu: sync
	ssh -tt $(HOST) "bash -l -c 'cd microban && PYTHONPATH=src .venv/bin/python src/imu.py'"

shutdown:
	ssh -tt $(HOST) "sudo shutdown -h now"

# Opt-in headless mode: a service launches the control loop when START is held 2s on
# the gamepad (no SSH needed); B stops it. See docs/usage.md.
gamepad-headless-enable: sync
	ssh -tt $(HOST) "bash -l -c 'cd microban && sudo bash systemd/install-gamepad-daemon.sh'"

gamepad-headless-disable:
	ssh -tt $(HOST) "bash -l -c 'cd microban && sudo bash systemd/install-gamepad-daemon.sh --uninstall'"

# Live dashboard on this PC (motors, IMU, 3D, reboot a motor): the robot streams while its program runs (service or
# `make run`). HOST: the robot to open with; another one can be chosen, and saved under a name, in the page.
# MODEL: the robot model shown (default: microban_model's robot.xml; CLIMB=1: robot_climb.xml)
CLIMB ?=
MODEL ?= $(shell uv run --group dashboard python -c "import microban_model; print(microban_model.mjcf($(if $(CLIMB),True,False)))")
# the page's Deploy button runs make deploy for the robot shown, as this user (the SD image's: radxa)
ROBOT_USER ?= radxa
dashboard:
	PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --robot $(HOST) --model $(MODEL) --title Microban \
		--deploy 'make deploy HOST=$(ROBOT_USER)@{host}'
