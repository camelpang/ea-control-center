from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AdminPrincipal:
    subject: str
    role: str


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(*, subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def require_ea_token(x_ea_token: str | None = Header(default=None)) -> None:
    if x_ea_token != settings.ea_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid EA token")


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def require_admin_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> AdminPrincipal:
    if x_admin_token is not None and x_admin_token == settings.admin_api_token:
        return AdminPrincipal(subject="legacy-token", role="admin")

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role = str(payload.get("role", "viewer"))
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this console",
        )

    sub = str(payload.get("sub", ""))
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    return AdminPrincipal(subject=sub, role=role)


def require_console_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> AdminPrincipal:
    if x_admin_token is not None and x_admin_token == settings.admin_api_token:
        return AdminPrincipal(subject="legacy-token", role="admin")

    return require_authenticated_user(credentials)


def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AdminPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = str(payload.get("sub", ""))
    role = str(payload.get("role", "viewer"))
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    return AdminPrincipal(subject=sub, role=role)
