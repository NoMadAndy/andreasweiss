"""Auth module: per-candidate and platform-level Basic Auth."""

import os
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_db

security = HTTPBasic()

PLATFORM_ADMIN_USER = os.environ.get("PLATFORM_ADMIN_USER", "admin")
PLATFORM_ADMIN_PASS = os.environ.get("PLATFORM_ADMIN_PASS", "changeme")


def verify_admin(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify admin credentials against the candidate's stored credentials.

    Reads the candidate slug from the URL path parameters.
    """
    slug = request.path_params.get("slug", "")
    if not slug:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kein Kandidat angegeben")

    db = get_db()
    try:
        row = db.execute(
            "SELECT admin_user, admin_pass FROM candidates WHERE slug=?", (slug,)
        ).fetchone()
    finally:
        db.close()

    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat nicht gefunden")

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"), row["admin_user"].encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"), row["admin_pass"].encode("utf-8")
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def verify_platform_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify platform-level admin credentials from environment variables."""
    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        PLATFORM_ADMIN_USER.encode("utf-8"),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        PLATFORM_ADMIN_PASS.encode("utf-8"),
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Plattform-Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
