from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.recon.registry import all_modules
from app.schemas.schemas import ModuleSchemaOut

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleSchemaOut])
def list_modules(_user=Depends(get_current_user)) -> list[ModuleSchemaOut]:
    """Drives the frontend's dynamic run wizard (PRD F1) - one entry per
    registered ReconModule, with its input slots and options JSON schema."""
    return [ModuleSchemaOut(**m.schema()) for m in all_modules()]
