.PHONY: sync setup run stop shutdown voltage imu sim viewer gamepad-headless-enable gamepad-headless-disable

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
		--exclude='src/model/mjcf' \
		./ $(HOST):microban

setup: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv sync --frozen'"

sim:
	PYTHONPATH=src uv run --group sim src/sim/sim_main.py --hz 50

viewer:
	PYTHONPATH=src uv run src/sim/viewer_main.py --hz 25

run: sync
	ssh -tt $(HOST) "bash -l -c 'cd microban && PYTHONPATH=src .venv/bin/python src/main.py'"

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
