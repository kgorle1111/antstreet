"""The firm's specialist roles. Each module in this package defines `SPECS`, a tuple of
`RoleSpec`; `registry()` collects them, so adding a role is adding a module."""

from __future__ import annotations

import importlib
import pkgutil

from antstreet.roles.base import RoleSpec

_NOT_ROLES = frozenset({"base", "stories"})


def registry() -> dict[str, RoleSpec]:
    """Every role by name, in a stable order. Two roles with one name is an error."""
    found: dict[str, RoleSpec] = {}
    for module in sorted(m.name for m in pkgutil.iter_modules(__path__)):
        if module in _NOT_ROLES:
            continue
        for spec in getattr(importlib.import_module(f"{__name__}.{module}"), "SPECS", ()):
            if spec.name in found:
                raise ValueError(f"role {spec.name!r} is defined twice")
            found[spec.name] = spec
    return found
