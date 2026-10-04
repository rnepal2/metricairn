"""Issue a management credential for an existing local project (operator migration).

Run from the repo root: uv run python scripts/issue_management_key.py PROJECT_ID
Requires direct local database access; never run as a public API endpoint.
"""

import secrets
import sys

from app.core.database import SessionLocal, init_db
from app.core.security import store_key
from app.models import Project


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: uv run python scripts/issue_management_key.py PROJECT_ID")
    init_db()
    with SessionLocal() as db:
        project = db.get(Project, sys.argv[1])
        if project is None:
            raise SystemExit("Project not found in the configured local database")
        raw = f"alm_{secrets.token_urlsafe(32)}"
        store_key(db, project_id=project.id, key=raw, name="operator-migration", scopes="manage")
        print(f"Management key for {project.name} (save privately; shown once): {raw}")


if __name__ == "__main__":
    main()
