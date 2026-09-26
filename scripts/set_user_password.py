"""Provision a password for an existing user; never creates accounts or roles."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, update

from app.db.database import SessionLocal
from app.db.models import User, UserSession
from app.services.auth_service import hash_password, normalize_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Set an existing user's password")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user-id", type=int)
    target.add_argument("--email")
    args = parser.parse_args()

    password = getpass("New password: ")
    confirmation = getpass("Confirm password: ")
    if not password or password != confirmation:
        print("Password provisioning failed.")
        return 1

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        query = select(User)
        if args.user_id is not None:
            query = query.where(User.id == args.user_id)
        else:
            query = query.where(User.email == normalize_email(args.email))
        user = db.scalar(query)
        if user is None:
            print("Password provisioning failed.")
            return 1
        user.password_hash = hash_password(password)
        user.password_changed_at = now
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    print("Password updated and existing sessions revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
