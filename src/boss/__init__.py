"""`boss`: the old import name of `antstreet`, kept so existing imports and `python -m boss.X` work.

`import boss` gives the `antstreet` package itself, and `boss.X` the already-imported
`antstreet.X`: one module object under two names, so module state (registries, caches) is never
duplicated. Nothing in `antstreet` imports this.
"""

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from types import CodeType, ModuleType

import antstreet

_OLD, _NEW = "boss.", "antstreet."


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.InspectLoader):
    """Finds `boss.X` and loads it as `antstreet.X`. It must come before the path finder on
    `sys.meta_path`: `boss` is `antstreet` in `sys.modules`, so the path finder would otherwise
    find `antstreet/X.py` again and execute a second copy under the name `boss.X`."""

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(_OLD):
            return None
        real = importlib.util.find_spec(_NEW + fullname[len(_OLD) :])
        if real is None:
            return None
        # `origin` is the real file, so `python -m boss.cli` sets `__file__` and `sys.argv[0]`
        # as `python -m antstreet.cli` would.
        return importlib.util.spec_from_loader(
            fullname,
            self,
            origin=real.origin,
            is_package=real.submodule_search_locations is not None,
        )

    def exec_module(self, module: ModuleType) -> None:
        # The import system returns whatever sits in `sys.modules` after this, not `module`.
        sys.modules[module.__name__] = importlib.import_module(_NEW + module.__name__[len(_OLD) :])

    def get_code(self, fullname: str) -> CodeType | None:
        """For `python -m boss.X` (runpy runs the code as `__main__`, never via exec_module)."""
        real = importlib.util.find_spec(_NEW + fullname[len(_OLD) :])
        if real is None or not isinstance(real.loader, importlib.abc.InspectLoader):
            raise ImportError(f"no code for {fullname}: {_NEW}{fullname[len(_OLD) :]} has none")
        return real.loader.get_code(real.name)

    def get_source(self, fullname: str) -> str | None:
        return None


if not any(isinstance(finder, _Alias) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Alias())
sys.modules[__name__] = antstreet
