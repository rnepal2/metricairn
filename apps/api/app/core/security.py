"""API-key auth. Write keys start with alw_, read keys with alr_.

Keys are stored as SHA-256 hashes; only the prefix is kept in clear for display.
"""

import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ApiKey


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_keypair() -> tuple[str, str]:
    """Return (write_key, read_key)."""
    return f"alw_{secrets.token_urlsafe(32)}", f"alr_{secrets.token_urlsafe(32)}"


def store_key(db: Session, *, project_id: str, key: str, name: str, scopes: str) -> ApiKey:
    record = ApiKey(
        project_id=project_id,
        key_hash=_hash(key),
        key_prefix=key[:8],
        name=name,
        scopes=scopes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _require(db: Session, key: str | None, scope: str) -> ApiKey:
    if not key:
        raise HTTPException(status_code=401, detail="Missing API key")
    record = (
        db.query(ApiKey).filter(ApiKey.key_hash == _hash(key), ApiKey.revoked.is_(False)).first()
    )
    if not record or scope not in record.scopes.split(","):
        raise HTTPException(status_code=403, detail="Invalid or unauthorized API key")
    return record


def require_write_key(
    x_write_key: str | None = Header(default=None, alias="X-Write-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    return _require(db, x_write_key, "write")


def require_management_key(
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Private credential. Browser-visible ingest keys can never administer data."""
    return _require(db, x_management_key, "manage")


def require_read_key(
    x_read_key: str | None = Header(default=None, alias="X-Read-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    return _require(db, x_read_key, "read")
