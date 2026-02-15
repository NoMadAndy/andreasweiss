"""Auth module: per-candidate and platform-level Basic Auth."""

import logging
import os
import re
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_db

log = logging.getLogger("uvicorn.error")

security = HTTPBasic(auto_error=False)


PLATFORM_ADMIN_USER = os.environ.get("PLATFORM_ADMIN_USER", "admin")
PLATFORM_ADMIN_PASS = os.environ.get("PLATFORM_ADMIN_PASS", "changeme")


def verify_admin(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify admin credentials against the candidate's stored credentials.

    Reads the candidate slug from the URL path parameters or extracts it from the URL path.
    """
    # Debug logging for troubleshooting
    log.debug(f"verify_admin called for path: {request.url.path}")
    log.debug(f"path_params: {request.path_params}")
    log.debug(f"credentials present: {credentials is not None}")
    
    if not credentials:
        log.warning(f"No credentials provided for path: {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Zugangsdaten erforderlich",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Try to get slug from path_params first
    slug = request.path_params.get("slug", "")
    
    # Fallback: extract slug from URL path if path_params is empty
    if not slug:
        log.debug("Slug not in path_params, attempting to extract from URL path")
        # Pattern: /api/{slug}/admin/...
        match = re.search(r'/api/([^/]+)/admin/', request.url.path)
        if match:
            slug = match.group(1)
            log.debug(f"Extracted slug from URL: {slug}")
    
    if not slug:
        log.error(f"Could not determine slug for path: {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kein Kandidat angegeben",
        )

    log.debug(f"Verifying admin credentials for slug: {slug}")
    
    db = get_db()
    try:
        row = db.execute(
            "SELECT admin_user, admin_pass FROM candidates WHERE slug=?", (slug,)
        ).fetchone()
    finally:
        db.close()

    if not row:
        log.warning(f"Candidate not found: {slug}")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidat nicht gefunden")

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"), row["admin_user"].encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"), row["admin_pass"].encode("utf-8")
    )
    if not (user_ok and pass_ok):
        log.warning(f"Invalid credentials for slug: {slug}, user: {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    log.info(f"Admin authentication successful for slug: {slug}, user: {credentials.username}")
    return credentials.username


def verify_platform_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Verify platform-level admin credentials from environment variables."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Zugangsdaten erforderlich")

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
        )
    return credentials.username
