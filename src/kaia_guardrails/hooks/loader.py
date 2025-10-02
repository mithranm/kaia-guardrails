from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import pkgutil
from dataclasses import dataclass
from importlib.metadata import entry_points

from .base import HookBase


@dataclass
class DiscoveredHook:
    name: str
    hook: HookBase
    source: str


def _discover_builtin(package_name: str) -> list[DiscoveredHook]:
    """Discover modules under a package and look for Hook subclasses."""

    try:
        pkg = importlib.import_module(package_name)
    except Exception:
        return []

    discovered: list[DiscoveredHook] = []
    if not hasattr(pkg, "__path__"):
        return discovered

    for _finder, name, _ispkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, HookBase) and obj is not HookBase:
                try:
                    inst = obj()
                except TypeError:
                    # Skip classes that require constructor args
                    continue
                discovered.append(DiscoveredHook(inst.name, inst, "builtin"))

    return discovered


def _discover_entrypoints(group: str = "kaia_guardrails.hooks") -> list[DiscoveredHook]:
    eps = entry_points(group=group)
    discovered: list[DiscoveredHook] = []
    for ep in eps:
        try:
            obj = ep.load()
        except Exception:
            continue

        if inspect.isclass(obj) and issubclass(obj, HookBase):
            try:
                inst = obj()
            except TypeError:
                continue
            discovered.append(DiscoveredHook(inst.name, inst, f"entrypoint:{ep.name}"))
        else:
            # Allow callables/factory functions returning HookBase
            try:
                inst = obj()
            except Exception:
                continue
            if isinstance(inst, HookBase):
                discovered.append(DiscoveredHook(inst.name, inst, f"entrypoint:{ep.name}"))

    return discovered


def _discover_filesystem(hooks_dir: str) -> list[DiscoveredHook]:
    discovered: list[DiscoveredHook] = []
    if not os.path.isdir(hooks_dir):
        return discovered

    for fn in os.listdir(hooks_dir):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(hooks_dir, fn)
        name = f"filesystem_hooks.{os.path.splitext(fn)[0]}"
        spec = importlib.util.spec_from_file_location(name, path)
        if not spec or not spec.loader:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, HookBase) and obj is not HookBase:
                try:
                    inst = obj()
                except TypeError:
                    continue
                discovered.append(DiscoveredHook(inst.name, inst, f"filesystem:{fn}"))

    return discovered


def discover_hooks(
    builtin_package: str = "kaia_guardrails.hooks.implementation", hooks_dir: str | None = None
) -> list[DiscoveredHook]:
    """Discover hooks from builtin package, entry points, and an optional hooks_dir.

    Returns a list of DiscoveredHook sorted by priority.
    """

    hooks: list[DiscoveredHook] = []
    hooks.extend(_discover_builtin(builtin_package))
    hooks.extend(_discover_entrypoints())
    if hooks_dir:
        hooks.extend(_discover_filesystem(hooks_dir))

    # deduplicate by name, prefer filesystem > entrypoint > builtin
    by_name: dict[str, DiscoveredHook] = {}
    priority_of_source = {"filesystem": 3, "entrypoint": 2, "builtin": 1}
    for h in hooks:
        key = h.name
        existing = by_name.get(key)
        if not existing:
            by_name[key] = h
            continue

        # compare source priority
        def src_priority(src: str) -> int:
            s = src.split(":", 1)[0]
            return priority_of_source.get(s, 0)

        if src_priority(h.source) >= src_priority(existing.source):
            by_name[key] = h

    discovered_list = list(by_name.values())
    # sort by hook priority
    discovered_list.sort(key=lambda x: getattr(x.hook, "priority", 100))
    return discovered_list


def load_hook_by_name(
    name: str, builtin_package: str = "kaia_guardrails.hooks.implementation", hooks_dir: str | None = None
) -> DiscoveredHook | None:
    for h in discover_hooks(builtin_package=builtin_package, hooks_dir=hooks_dir):
        if h.name == name:
            return h
    return None
