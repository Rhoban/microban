.PHONY: sync setup run stop battery sim

HOST ?= microban
MJCF ?= model/scene.xml

sync:
	rsync -avz \
		--exclude='.git' \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='cad' \
		--exclude='docs' \
		--exclude='src/sim' \
		./ $(HOST):microban

setup: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv sync'"

run: sync
	ssh -tt $(HOST) "bash -l -c 'cd microban && uv run src/main.py'"

stop:
	ssh -tt $(HOST) "bash -l -c 'cd microban && uv run src/stop.py'"

battery: sync
	ssh $(HOST) "bash -l -c 'cd microban && uv run src/battery.py'"

sim:
	uv run --group sim src/sim/sim_main.py --mjcf $(MJCF)