.PHONY: sync setup deploy run stop robot-service-enable robot-service-disable robot-service-start robot-service-stop robot-service-logs shutdown voltage imu sim viewer dashboard gamepad-headless-enable gamepad-headless-disable

HOST ?= microban
ID ?=

# Sends this folder to the robot's ~/microban; the PC's own files stay here: the dashboard's recordings, the options
# saved from a simulation (move_options.json), the CONTROLLER copy (make run puts it there itself)
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
		--exclude='recordings' \
		--exclude='move_options.json' \
		--exclude='robot_variant.txt' \
		--exclude='user_controller.py' \
		./ $(HOST):microban

setup: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv sync'"

# CONTROLLER=path/to/file.py: your Controller (src/moves/controller.py), started / stopped with [c] (gamepad: Y)
CONTROLLER ?=
# WALL=N1|N2|N3|wall.json: on the climbing wall of the hackathon's simulator, cloned next to this folder (SIMULATOR;
# used from there: a change made in it applies at once); START=floor: standing in front of the wall
WALL ?=
START ?= hang
SIMULATOR ?= ../simulator
sim:
	@$(if $(WALL),test -f $(SIMULATOR)/pyproject.toml || { echo "The climbing simulator is not in $(SIMULATOR): \
	git clone https://github.com/rock-climbing-robots/simulator $(SIMULATOR)  (or SIMULATOR=its/folder)"; exit 1; })
	PYTHONPATH=src uv run --group sim $(if $(WALL),--with-editable $(SIMULATOR)) src/sim/sim_main.py --hz 50 \
		$(if $(CONTROLLER),--controller $(CONTROLLER)) $(if $(WALL),--wall $(WALL) --start $(START))

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
# the gamepad (no SSH needed); B stops it. See docs/gamepad.md.
gamepad-headless-enable: sync
	ssh -tt $(HOST) "bash -l -c 'cd microban && sudo bash systemd/install-gamepad-daemon.sh'"

gamepad-headless-disable:
	ssh -tt $(HOST) "bash -l -c 'cd microban && sudo bash systemd/install-gamepad-daemon.sh --uninstall'"

# Live dashboard on this PC (motors, IMU, 3D, reboot a motor): the robot streams while its program runs (service or
# `make run`). HOST: the robot to open with; another one can be chosen, and saved under a name, in the page.
# The page asks for each robot its version, Classic or Climber (the 3D model; saved with the robot). CLIMB=1: Climber
# first.
CLIMB ?=
MODELS ?= $(shell uv run --group dashboard python -c "import microban_model as m; print(f'--model Classic={m.mjcf()} --model Climber={m.mjcf(True)}')")
# the page's Deploy button runs make deploy for the robot shown, as this user (the SD image's: radxa)
ROBOT_USER ?= radxa
# only a HOST given (command line or environment), not the default one: else the page opens on its robot picker
DASH_ROBOT = $(if $(filter command line environment,$(origin HOST)),--robot $(HOST))
dashboard:
	PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app $(DASH_ROBOT) $(MODELS) \
		$(if $(CLIMB),--model-name Climber) --title Microban \
		--deploy 'make deploy HOST=$(ROBOT_USER)@{host}'
