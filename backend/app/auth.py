from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Callable
from uuid import UUID

import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, set_identity_context, set_tenant_context
from app.models import Membership, User
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@dataclass(frozen=True)
class Principal:
    user: User
    membership: Membership

    @property
    def organization_id(self) -> UUID:
        return self.membership.organization_id

    @property
    def role(self) -> str:
        return self.membership.role


def get_current_principal(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired sign-in. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = UUID(payload["sub"])
        organization_id = UUID(payload["org"])
        membership_id = UUID(payload["membership"])
    except (JWTError, ValueError, KeyError):
        raise unauthorized from None

    # Both values are derived from a server-signed token issued only after the
    # password and membership were checked. The membership query below still
    # verifies that access is current and has not been revoked.
    set_identity_context(db, user_id)
    set_tenant_context(db, organization_id)
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.is_active.is_(True),
        )
    )
    if not user or not membership:
        raise unauthorized
    if payload.get("role") != membership.role:
        raise unauthorized
    if membership.role == "organization_admin" and not user.mfa_enabled:
        raise HTTPException(status_code=403, detail="Administrator MFA enrollment is required")
    return Principal(user=user, membership=membership)


def require_roles(*roles: str) -> Callable:
    def dependency(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
        if principal.role not in roles and not principal.user.is_platform_super_admin:
            raise HTTPException(status_code=403, detail="Your role cannot perform this action")
        return principal

    return dependency


def verify_totp(user: User, code: str | None) -> bool:
    if not user.mfa_enabled:
        return False
    if not code or not user.mfa_secret:
        return False
    return pyotp.TOTP(user.mfa_secret).verify(code.strip(), valid_window=1)
