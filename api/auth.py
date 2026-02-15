"""Auth module: per-candidate and platform-level Basic Auth."""

import logging
import os
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_db

log = logging.getLogger("uvicorn.error")

security = HTTPBasic(auto_error=False)


PLATFORM_ADMIN_USER = os.environ.get("PLATFORM_ADMIN_USER", "admin")
PLATFORM_ADMIN_PASS = os.environ.get("PLATFORM_ADMIN_PASS", "changeme")


def verify_admin(
    slug: str,
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify admin credentials against the candidate's stored credentials.

    Args:
        slug: The candidate slug from the URL path parameter
        request: The FastAPI request object
        credentials: HTTP Basic Auth credentials

    Returns:
        The authenticated username
    """
    # Debug logging for troubleshooting
    log.debug(f"verify_admin called for path: {request.url.path}")
    log.debug(f"credentials present: {credentials is not None}")
    
    if not credentials:
        log.warning(f"No credentials provided for admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Zugangsdaten erforderlich",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not slug:
        log.error(f"Empty slug provided for path: {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein Kandidat angegeben",
        )

    log.debug(f"Verifying admin credentials for candidate")
    
    db = get_db()
    try:
        row = db.execute(
            "SELECT admin_user, admin_pass FROM candidates WHERE slug=?", (slug,)
        ).fetchone()
    finally:
        db.close()

    if not row:
        log.warning(f"Candidate not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kandidat nicht gefunden",
        )

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"), row["admin_user"].encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"), row["admin_pass"].encode("utf-8")
    )
    if not (user_ok and pass_ok):
        log.warning(f"Invalid credentials provided for admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    log.info(f"Admin authentication successful")
    return credentials.username


def verify_platform_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify platform-level admin credentials from environment variables."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Zugangsdaten erforderlich",
            headers={"WWW-Authenticate": "Basic"},
        )

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
