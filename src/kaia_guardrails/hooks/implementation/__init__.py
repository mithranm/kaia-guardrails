"""Built-in hook implementations for kaia_guardrails.

Implementations live under this subpackage (keeps engine and impl separated).
Utilities are provided to migrate existing `.claude/hooks` scripts into this package.
"""

from collections.abc import Iterable
from importlib import import_module


def iter_impl_names() -> Iterable[str]:
    # Discover statically-exported implementations in this package.
    # Add names here as implementations are added.
    return [
        "agents_compliance_judge",
    ]


def load_impl(name: str):
    return import_module(f"{__name__}.{name}")
