.PHONY: sync setup run

sync:
	rsync -avz \
		--exclude='.git' \
		--exclude='.venv' \
		--exclude='__pycache__' \
		--exclude='cad' \
		--exclude='docs' \
		./ microban:microban

setup: sync
	ssh microban "bash -l -c 'cd microban && uv sync'"

run: sync
	ssh microban "bash -l -c 'cd microban && uv run src/main.py'"

stop:
	ssh microban "bash -l -c 'cd microban && uv run src/stop.py'"