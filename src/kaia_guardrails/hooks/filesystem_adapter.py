"""Adapter to wrap existing .claude hook scripts on disk as HookBase implementations.

This module provides a convenience factory `wrap_script_as_hook` that will
import a python file by path and create a HookBase-compatible wrapper around
an exported `run(context)` function or `main` callable.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Any

from .base import HookBase, HookError


def wrap_script_as_hook(path: str, name: str | None = None, priority: int = 100) -> HookBase | None:
    if not os.path.exists(path):
        return None

    module_name = f"_external_hook_{os.path.splitext(os.path.basename(path))[0]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise HookError(f"failed to import hook script {path}: {e}") from e

    # find a run function
    runner = None
    if hasattr(mod, "run") and callable(mod.run):
        runner = mod.run
    elif hasattr(mod, "main") and callable(mod.main):
        runner = mod.main

    if not runner:
        return None

    @dataclass
    class ScriptHook(HookBase):
        def __init__(self):
            super().__init__(name or os.path.splitext(os.path.basename(path))[0], priority=priority)

        def run(self, context: dict[str, Any]):
            try:
                return runner(context)
            except Exception as e:
                raise HookError(str(e)) from e

    return ScriptHook()
