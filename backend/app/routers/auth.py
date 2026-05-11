from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginIn, TokenOut, UserPublicOut
from app.security import AdminPrincipal, create_access_token, require_authenticated_user, verify_password

router = APIRouter()


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token(subject=user.username, role=user.role.value)
    return TokenOut(
        access_token=token,
        user=UserPublicOut(username=user.username, role=user.role.value),
    )


@router.get("/me")
def me(principal: AdminPrincipal = Depends(require_authenticated_user)) -> dict[str, str]:
    return {"username": principal.subject, "role": principal.role}
