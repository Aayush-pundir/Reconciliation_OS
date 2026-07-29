"""Merges a run's own options on top of the admin-configured org-level
defaults for that module (app/api/routes_admin.py)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ModuleConfig


def get_effective_options(db: Session, module_key: str, override: dict[str, Any]) -> dict[str, Any]:
    cfg = db.query(ModuleConfig).filter(ModuleConfig.module_key == module_key).first()
    merged: dict[str, Any] = dict(cfg.default_options) if cfg else {}
    merged.update(override or {})
    return merged
