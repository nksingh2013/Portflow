from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.config import settings

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2, type=Type.ID)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    role: str,
    *,
    scope: str = "access",
    lifetime: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expiry = now + (lifetime or timedelta(minutes=settings.access_token_minutes))
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "membership": str(membership_id),
        "role": role,
        "scope": scope,
        "iss": settings.token_issuer,
        "iat": now,
        "exp": expiry,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_token(token: str, expected_scope: str = "access") -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[ALGORITHM],
        issuer=settings.token_issuer,
        options={"require_sub": True, "require_exp": True, "require_iat": True, "require_iss": True},
    )
    if payload.get("scope") != expected_scope:
        raise JWTError("Invalid token scope")
    # Parse IDs here so malformed signed claims fail before reaching data access.
    UUID(payload["sub"])
    UUID(payload["org"])
    UUID(payload["membership"])
    return payload
