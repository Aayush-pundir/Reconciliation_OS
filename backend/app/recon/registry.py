"""Module registry (PRD F1). Adding recon type #8 to Recon OS means:
  1. write `app/recon/modules/my_new_module.py` implementing `ReconModule`
  2. call `register(MyNewModule())` at the bottom of that file
  3. add one import line to `_load_all()` below

Nothing in the engine, the API routes, or the frontend shell changes -
the frontend renders whatever `module.schema()` describes.
"""
from __future__ import annotations

from app.recon.base import ReconModule

_registry: dict[str, ReconModule] = {}


def register(module: ReconModule) -> None:
    _registry[module.key] = module


def get_module(key: str) -> ReconModule | None:
    return _registry.get(key)


def all_modules() -> list[ReconModule]:
    return list(_registry.values())


def _load_all() -> None:
    from app.recon.modules import (  # noqa: F401
        bank_addmoney,
        data_prep_6f,
        fastag,
        nfs,
        pg_recon,
        rupay,
        upi,
    )


_load_all()
