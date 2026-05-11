"""Create or update an admin user (bcrypt password). Run from repo: python backend/scripts/create_admin_user.py"""

from __future__ import annotations

import argparse
import os
import sys

# Allow `python backend/scripts/create_admin_user.py` from repo root
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import User, UserRole  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create admin user for EA Control Center")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--viewer", action="store_true", help="Create with viewer role (read-only API phase)")
    args = parser.parse_args()

    role = UserRole.viewer if args.viewer else UserRole.admin
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == args.username))
        if user:
            user.password_hash = hash_password(args.password)
            user.role = role
            user.is_active = True
            db.commit()
            print(f"Updated user {args.username!r} (role={role.value}).")
            return
        user = User(username=args.username, password_hash=hash_password(args.password), role=role)
        db.add(user)
        db.commit()
        print(f"Created user {args.username!r} (role={role.value}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
