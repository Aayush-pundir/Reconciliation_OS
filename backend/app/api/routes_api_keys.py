"""Service-to-service API keys - separate credential path from human login
(which is optional). Lets other internal systems trigger runs
programmatically even when the UI itself requires no login."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.core.security import generate_api_key
from app.models import ApiKey, User
from app.schemas.schemas import ApiKeyCreateRequest, ApiKeyCreatedOut, ApiKeyOut

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
def create_api_key(
    payload: ApiKeyCreateRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)
) -> ApiKeyCreatedOut:
    raw, prefix, key_hash = generate_api_key()
    record = ApiKey(name=payload.name, key_prefix=prefix, key_hash=key_hash, user_id=user.id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return ApiKeyCreatedOut(
        id=record.id, name=record.name, key_prefix=record.key_prefix, created_at=record.created_at, api_key=raw
    )


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), user: User = Depends(require_admin)) -> list[ApiKeyOut]:
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.delete("/{key_id}", status_code=204)
def revoke_api_key(key_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> None:
    from datetime import datetime, timezone

    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(404, "API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    db.add(key)
    db.commit()
