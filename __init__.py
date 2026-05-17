from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


def _export_from(module: Any) -> None:
    names = getattr(module, "__all__", None)
    if names is None:
        names = [name for name in dir(module) if not name.startswith("_")]
    globals().update({name: getattr(module, name) for name in names})
    globals()["__all__"] = list(names)


def _load_synthetic_runtime() -> Any:
    _pkg_name = "_turn_closure_audit_runtime"
    _plugin_dir = Path(__file__).resolve().parent
    if _pkg_name not in sys.modules:
        _pkg = types.ModuleType(_pkg_name)
        _pkg.__path__ = [str(_plugin_dir)]  # type: ignore[attr-defined]
        _pkg.__package__ = _pkg_name
        sys.modules[_pkg_name] = _pkg
    return importlib.import_module(f"{_pkg_name}.runtime")


try:
    if not __package__:
        raise ImportError("top-level import needs synthetic package")
    from . import events, paths  # noqa: F401
    from . import runtime as _runtime
except ImportError:
    _runtime = _load_synthetic_runtime()
    paths = importlib.import_module("_turn_closure_audit_runtime.paths")
    events = importlib.import_module("_turn_closure_audit_runtime.events")

_export_from(_runtime)
