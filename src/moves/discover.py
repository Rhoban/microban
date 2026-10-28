# SPDX-License-Identifier: GPL-3.0-or-later
"""Every move written in src/moves/ is found by itself: no need to register it in src/main.py.

Each class of a file of this folder that derives from Move becomes a move of the robot (and of the simulation), unless
it is registered already. Its name in the dashboard and for the scheduler is the class's `name` if it sets one,
otherwise the class name in snake_case without "Move" (WaveMove -> "wave"). Its constructor gets `controller=` when it
takes one, nothing otherwise. A file that fails to load or a class that cannot be built is skipped with a message:
the robot starts anyway.
"""
import importlib
import inspect
import pathlib
import re
import sys
import traceback

from moves.move import Move

HERE = pathlib.Path(__file__).parent
SKIP = {"__init__", "move", "discover", "controller"}       # the base class, this file, the Controller (CONTROLLER=)
PROBLEMS: list[str] = []          # why a move was skipped: printed, and shown in the dashboard's events (telemetry)


def move_name(cls) -> str:
    name = getattr(cls, "name", None)
    if isinstance(name, str) and name:
        return name
    base = cls.__name__[:-4] if cls.__name__.endswith("Move") and cls.__name__ != "Move" else cls.__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()


def _skip(text: str, path=None) -> None:
    """A skipped move: the full message (and traceback) in the robot's log; for the dashboard one line, with the line
    of the student's file where the error is."""
    lines = text.strip().splitlines()
    short = lines[0] if len(lines) == 1 else f"{lines[0]} {lines[-1]}"
    if path is not None and len(lines) > 1:
        frames = [f for f in traceback.extract_tb(sys.exc_info()[2]) if pathlib.Path(f.filename) == path]
        if frames:
            short = f"{lines[0][:-1]} line {frames[-1].lineno}: {lines[-1]}"
    PROBLEMS.append(short)
    print(text, end="\r\n", flush=True)


def discover_moves(controller, known: dict) -> dict:
    """The moves of src/moves/ not in `known` (name -> Move), as {name: instance}."""
    known_classes = {type(m) for m in known.values()}
    found = {}
    for path in sorted(HERE.glob("*.py")):
        if path.stem in SKIP or path.stem.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"moves.{path.stem}")
        except Exception:
            _skip(f"Move file {path.name} skipped (it does not load):\n{traceback.format_exc()}", path)
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, Move) or cls is Move or cls.__module__ != module.__name__ or cls in known_classes:
                continue
            if inspect.isabstract(cls):
                _skip(f"Move {cls.__name__} ({path.name}) skipped: it lacks {', '.join(sorted(cls.__abstractmethods__))}")
                continue
            name = move_name(cls)
            if name in known or name in found:
                continue
            try:
                params = inspect.signature(cls).parameters
                found[name] = cls(controller=controller) if "controller" in params else cls()
                print(f"Move {name} ({path.name}) found", end="\r\n", flush=True)
            except Exception:
                _skip(f"Move {cls.__name__} ({path.name}) skipped (it cannot be built):\n{traceback.format_exc()}", path)
    return found


def with_discovered_moves(controller, moves: dict) -> dict:
    """These moves and every other move written in src/moves/: a new file there is enough."""
    return {**moves, **discover_moves(controller, moves)}
