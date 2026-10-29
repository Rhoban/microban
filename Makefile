.PHONY: discover-robots sync backup restore setup deploy run stop robot-service-enable robot-service-disable robot-service-start robot-service-stop robot-service-logs shutdown voltage imu sim viewer dashboard gamepad-headless-enable gamepad-headless-disable

HOST ?= microban
ID ?=

# Sends this folder to the robot's ~/microban; the PC's own files stay here: the dashboard's recordings, the options
# saved from a simulation (move_options.json), the MOVES copy (make run puts it there itself). A file deleted here is
# deleted on the robot too (--delete; the files excluded below stay there)
sync:
	rsync -avz --delete \
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
		--exclude='user_moves.py' \
		./ $(HOST):microban

setup: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv sync'"

# MOVES=path/to/file.py: the moves of a file kept outside src/moves/, for this session (make run, make sim)
MOVES ?=
# The robot's program on Rhoban's robot simulator (microban_sim): VARIANT=climber for the climbing robot on the
# floor; WALL=N1|N2|N3|wall.json on the hackathon's climbing wall, its simulator cloned next to this folder (SIMULATOR,
# used from there: a change made in it applies at once); START=floor: standing in front of the wall
VARIANT ?= classic
WALL ?=
START ?= hang
SIMULATOR ?= ../simulator
# MICROBAN_SIM=path/to/microban_sim: a clone of Rhoban's robot simulator instead of its release (to change it)
MICROBAN_SIM ?=
# PYTHON=mjpython on macOS (MuJoCo's viewer needs it)
PYTHON ?= python
sim:
	@$(if $(WALL),test -f $(SIMULATOR)/pyproject.toml || { echo "The climbing simulator is not in $(SIMULATOR): \
	git clone https://github.com/rock-climbing-robots/simulator $(SIMULATOR)  (or SIMULATOR=its/folder)"; exit 1; })
	PYTHONPATH=src uv run --group sim $(if $(MICROBAN_SIM),--with-editable $(MICROBAN_SIM)) $(if $(WALL),--with-editable $(SIMULATOR)) \
		$(PYTHON) src/sim/sim_main.py --hz 50 $(if $(WALL),,--variant $(VARIANT)) $(if $(MOVES),--moves $(MOVES)) \
		$(if $(WALL),--wall $(WALL) --start $(START))

viewer:
	PYTHONPATH=src uv run src/sim/viewer_main.py --hz 25

run: sync
	$(if $(MOVES),scp $(MOVES) $(HOST):microban/user_moves.py)
	-ssh $(HOST) "systemctl is-active -q microban.service && sudo systemctl stop microban.service && echo 'robot service stopped for this session (make robot-service-start to restart it)'"
	ssh -tt $(HOST) "bash -l -c 'cd microban && $(if $(MOVES),MICROBAN_MOVES=user_moves.py) PYTHONPATH=src .venv/bin/python src/main.py'"

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
# Before every deploy, the robot's code as it was goes to ~/microban_backups/ (its last 5 kept; not .venv, recordings,
# logs). make restore HOST=...: back to the latest one (BACKUP=microban_YYYYmmdd_HHMMSS.tgz: that one), and restart.
BACKUPS = 5
BACKUP ?=
backup:
	ssh $(HOST) "set -e; [ -d microban ] || exit 0; mkdir -p microban_backups; \
		f=microban_backups/microban_\$$(date +%Y%m%d_%H%M%S).tgz; \
		tar czf \$$f --exclude=microban/.venv --exclude=microban/recordings --exclude=microban/logs \
			--exclude='__pycache__' microban; \
		ls -1t microban_backups/microban_*.tgz | tail -n +$$(($(BACKUPS) + 1)) | xargs -r rm -f; \
		echo \"backup of the robot's code: ~/\$$f (the last $(BACKUPS) kept: make restore)\""

restore:
	ssh $(HOST) "set -e; f=\$$(ls -1t microban_backups/microban_*.tgz | head -1); $(if $(BACKUP),f=microban_backups/$(BACKUP);) \
		[ -f \"\$$f\" ] || { echo 'no backup on the robot'; exit 1; }; \
		t=\$$(mktemp -d); tar xzf \$$f -C \$$t; \
		rsync -a --delete --exclude=.venv --exclude=recordings --exclude=logs \$$t/microban/ microban/; rm -rf \$$t; \
		sudo systemctl restart microban.service; echo \"robot's code back to ~/\$$f, its program restarted\""

deploy: backup sync
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

# The robots on this network: name, address, whether their program runs, their version (tools/discover_robots.py)
discover-robots:
	@uv run -q --group dashboard python tools/discover_robots.py

# Live dashboard on this PC (motors, IMU, 3D, reboot a motor): the robot streams while its program runs (service or
# `make run`). HOST: the robot to open with; another one can be chosen, and saved under a name, in the page.
# The robot says its version, Classic or Climber: the page shows its model (and changes it, in its header menu).
MODELS ?=
MODELS_CMD = uv run -q --group dashboard python -c "import microban_model as m; print(f'--model Classic={m.mjcf()} --model Climber={m.mjcf(True)}')"
# the page's Deploy button runs make deploy for the robot shown, as this user (the SD image's: radxa)
ROBOT_USER ?= radxa
# only a HOST given (command line or environment), not the default one: else the page opens on its robot picker;
# with or without its user (radxa@microban-XXXX.local as for make deploy: the page needs the host only)
DASH_ROBOT = $(if $(filter command line environment,$(origin HOST)),--robot $(lastword $(subst @, ,$(HOST))))
dashboard:
	@echo "Starting the dashboard (the first time, uv installs its packages: about a minute)..."
	PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app $(DASH_ROBOT) $(if $(MODELS),$(MODELS),$$($(MODELS_CMD))) \
		--title Microban \
		--deploy 'make deploy HOST=$(ROBOT_USER)@{host}'
