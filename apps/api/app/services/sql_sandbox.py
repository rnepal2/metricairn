"""Read-only SQL sandbox.

Two layers:
1. ``validate_shape`` — purely syntactic: single SELECT/WITH statement, no
   forbidden keywords (checked after stripping string literals and comments,
   so ``WHERE name = 'drop table'`` doesn't false-positive).
2. ``execute`` — runs the validated statement in a worker thread with a
   timeout, fetches at most ``row_cap`` rows. Semantic checks (project_id
   scoping, table allowlist, question/SQL alignment) live in sql_validate.py.
"""

from __future__ import annotations

import re
import threading

from sqlalchemy import text

from app.core.config import get_settings

_FORBIDDEN = frozenset({
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "exec", "execute", "call", "copy", "vacuum",
    "pragma", "attach", "detach", "replace", "merge", "handler", "load",
})


def _strip_literals(sql: str) -> str:
    """Remove string literals, quoted identifiers, and comments so keyword
    scans can't be fooled by (or trip on) literal contents."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c in ("'", '"', "`"):
            quote = c
            i += 1
            while i < n:
                if sql[i] == quote:
                    if sql[i + 1:i + 2] == quote:  # escaped quote ''
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
        elif c == "-" and nxt == "-":
            while i < n and sql[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            i += 2
            while i < n and not (sql[i] == "*" and sql[i + 1:i + 2] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def validate_shape(sql: str | None) -> tuple[bool, str]:
    """Syntactic safety only. Returns (ok, reason)."""
    if not sql or not sql.strip():
        return False, "empty SQL"
    stripped = _strip_literals(sql).strip()
    body = stripped[:-1].strip() if stripped.endswith(";") else stripped
    if ";" in body:
        return False, "multiple statements not allowed"
    if not re.match(r"(?i)^(SELECT|WITH)\b", body):
        return False, "only SELECT/WITH queries allowed"
    words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", body.lower()))
    bad = words & _FORBIDDEN
    if bad:
        return False, f"forbidden keyword: {sorted(bad)[0]}"
    return True, ""


def _run_with_timeout(fn, timeout_s: float):
    """Run fn() in a daemon thread; abandon it on timeout. Returns
    (value, error, timed_out)."""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except Exception as e:  # noqa: BLE001 — surfaced as validation failure
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, None, True
    if "error" in box:
        return None, box["error"], False
    return box.get("value"), None, False


def execute(db, sql: str, timeout_s: float | None = None,
            row_cap: int | None = None) -> dict:
    """Validate then execute a read-only query. Never raises: failures come
    back as {"ok": False, "reason": ...} so the router can fall back honestly."""
    ok, reason = validate_shape(sql)
    if not ok:
        return {"ok": False, "reason": reason}

    settings = get_settings()
    timeout_s = timeout_s if timeout_s is not None else settings.agentic_sql_timeout_s
    row_cap = row_cap if row_cap is not None else settings.agentic_sql_row_cap

    holder: dict = {}

    def run():
        bind = db.get_bind()
        conn = bind.connect()
        holder["conn"] = conn
        try:
            if bind.dialect.name == "postgresql":
                conn.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_s * 1000)}'"))
            cursor = conn.execute(text(sql))
            columns = list(cursor.keys())
            rows = cursor.fetchmany(row_cap)
            truncated = cursor.fetchone() is not None
            return {"columns": columns, "rows": [tuple(r) for r in rows],
                    "truncated": truncated}
        finally:
            conn.close()

    value, error, timed_out = _run_with_timeout(run, timeout_s)
    if timed_out:
        conn = holder.get("conn")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return {"ok": False, "reason": f"query timed out after {timeout_s}s"}
    if error is not None:
        return {"ok": False, "reason": f"execution failed: {error}"}
    return {"ok": True, **value}
