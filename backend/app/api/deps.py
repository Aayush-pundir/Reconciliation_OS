"""Shared FastAPI dependencies: DB session + current-user auth.

Auth is optional by default (Settings.auth_required=False) - this is an
internal tool with no login screen. When disabled, every request resolves
to a shared "local" system user so the audit trail (Run.triggered_by) still
has a stable value instead of silently going null. Set AUTH_REQUIRED=true
(and log in) to re-enable JWT enforcement + the login screen, e.g. if this
ever runs on shared/exposed infra.

Two credential types are accepted when auth IS required:
  - Bearer JWT (human login, via POST /api/auth/login)
  - X-API-Key header (service-to-service, via ApiKey records - see
    app/api/routes_api_keys.py)
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token, hash_api_key, hash_password
from app.models import ApiKey, User

_bearer = HTTPBearer(auto_error=False)
LOCAL_USER_EMAIL = "local@reconos.internal"


def get_or_create_local_user(db: Session) -> User:
    user = db.query(User).filter(User.email == LOCAL_USER_EMAIL).first()
    if user is None:
        user = User(email=LOCAL_USER_EMAIL, name="Local User", password_hash=hash_password(""), role="admin")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    if not settings.auth_required:
        return get_or_create_local_user(db)

    api_key_value = request.headers.get(settings.api_key_header)
    if api_key_value:
        key_hash = hash_api_key(api_key_value)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None)).first()
        if api_key is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")
        user = db.get(User, api_key.user_id)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key owner not found")
        return user

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
