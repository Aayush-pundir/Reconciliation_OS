"""Admin: org-level default options per module. A run's own options are
layered on top of these defaults at creation time (see routes_runs.create_run)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models import ModuleConfig, User
from app.recon.registry import get_module
from app.schemas.schemas import ModuleConfigOut, ModuleConfigUpdateRequest

router = APIRouter(prefix="/api/admin/module-configs", tags=["admin"])


@router.get("", response_model=list[ModuleConfigOut])
def list_module_configs(db: Session = Depends(get_db), _user: User = Depends(require_admin)) -> list[ModuleConfigOut]:
    existing = {c.module_key: c for c in db.query(ModuleConfig).all()}
    from app.recon.registry import all_modules

    out = []
    for module in all_modules():
        cfg = existing.get(module.key)
        out.append(
            ModuleConfigOut(
                module_key=module.key,
                default_options=cfg.default_options if cfg else {},
                updated_at=cfg.updated_at if cfg else None,
            )
        )
    return out


@router.put("/{module_key}", response_model=ModuleConfigOut)
def update_module_config(
    module_key: str,
    payload: ModuleConfigUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> ModuleConfigOut:
    if get_module(module_key) is None:
        raise HTTPException(404, f"Unknown module '{module_key}'")

    cfg = db.query(ModuleConfig).filter(ModuleConfig.module_key == module_key).first()
    if cfg is None:
        cfg = ModuleConfig(module_key=module_key, default_options=payload.default_options)
    else:
        cfg.default_options = payload.default_options
    cfg.updated_by = user.id
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return ModuleConfigOut(module_key=cfg.module_key, default_options=cfg.default_options, updated_at=cfg.updated_at)
