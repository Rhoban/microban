# SPDX-License-Identifier: GPL-3.0-or-later
"""Every move written in src/moves/ is found by itself: no need to register it anywhere.

Each class of a file of this folder with a step(self, obs) is a move (moves/move.py; its class name ends with Move by
convention). Its name in the dashboard and for the scheduler is the class's `name` if it sets one, otherwise the class
name without "Move" in snake_case (WaveMove -> "wave", RaiseArmMove -> "raise_arm"). A file kept elsewhere is loaded
the same way with load_file (make run MOVES=...). A file that fails to load or a move that cannot be built is skipped
with a message: the robot starts anyway.
"""
import importlib
import importlib.util
import inspect
import pathlib
import re
import sys
import traceback

from moves.move import ALL, Runner, is_move

HERE = pathlib.Path(__file__).parent
SKIP = {"__init__", "move", "discover"}          # the moves' runner, this file
PROBLEMS: list[str] = []          # why a move was skipped: printed, and shown in the dashboard's events (telemetry)


def move_name(cls) -> str:
    name = getattr(cls, "name", None)
    if isinstance(name, str) and name:
        return name
    base = cls.__name__[:-4] if cls.__name__.endswith("Move") and cls.__name__ != "Move" else cls.__name__
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", base).lower()   # IKSquatMove -> ik_squat


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


def _moves_of(module, path: pathlib.Path, found: dict) -> None:
    """The moves of a loaded file, added to found (name -> Runner), in the order they are written."""
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if c.__module__ == module.__name__]
    for cls in sorted(classes, key=lambda c: inspect.getsourcelines(c)[1]):
        if not is_move(cls):
            continue
        name = move_name(cls)
        if name in found:
            _skip(f"Move {cls.__name__} ({path.name}) skipped: another move is named {name} (set name = \"...\")")
            continue
        variants = getattr(cls, "variants", ALL)
        if not isinstance(variants, (tuple, list)) or not variants or not set(variants) <= set(ALL):
            _skip(f"Move {cls.__name__} ({path.name}) skipped: variants must be (\"classic\",), (\"climber\",) or "
                  f"both, not {variants!r}")
            continue
        try:
            found[name] = Runner(cls())
            only = "" if set(found[name].variants) == set(ALL) else f", {' / '.join(found[name].variants)} only"
            print(f"Move {name} ({path.name}{only}) found", end="\r\n", flush=True)
        except Exception:
            _skip(f"Move {cls.__name__} ({path.name}) skipped (it cannot be built):\n{traceback.format_exc()}", path)


def discover_moves() -> dict:
    """The moves of src/moves/, as {name: Runner}."""
    if str(HERE) not in sys.path:                  # a move imports its own files by name (import helper), as in the sim
        sys.path.append(str(HERE))
    found = {}
    for path in sorted(HERE.glob("*.py")):
        if path.stem in SKIP or path.stem.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"moves.{path.stem}")
        except Exception:
            _skip(f"Move file {path.name} skipped (it does not load):\n{traceback.format_exc()}", path)
            continue
        _moves_of(module, path, found)
    return found


def load_file(path) -> dict:
    """The moves of a file kept elsewhere (make run MOVES=...), as {name: Runner}."""
    path = pathlib.Path(path).expanduser().resolve()
    if str(path.parent) not in sys.path:
        sys.path.append(str(path.parent))
    spec = importlib.util.spec_from_file_location(f"user_moves_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    found = {}
    try:
        spec.loader.exec_module(module)
    except Exception:
        _skip(f"Move file {path} skipped (it does not load):\n{traceback.format_exc()}", path)
        return found
    _moves_of(module, path, found)
    return found


def all_moves(extra_file=None) -> dict:
    """The moves of src/moves/ and those of extra_file (make run / make sim MOVES=...): a move of that file named as
    one of src/moves/ replaces it, said in the events."""
    found = discover_moves()
    if extra_file:
        extra = load_file(extra_file)
        for name in sorted(set(extra) & set(found)):
            _skip(f"Move {name} of {pathlib.Path(extra_file).name} replaces the move {name} of src/moves/")
        found.update(extra)
    return found
