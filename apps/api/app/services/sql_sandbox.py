"""Read-only SQL execution with database cancellation and enforced tenant scoping.

Generated SQL is untrusted. Every physical events reference is replaced with a
parameterized tenant subquery, including references in CTEs, joins and UNIONs.
SQLite uses a progress handler and authorizer; Postgres uses a read-only
transaction and statement_timeout. No abandoned query threads or shared sessions.
"""

from __future__ import annotations

import re
import sqlite3
import time

import sqlglot
from sqlalchemy import text
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from app.core.config import get_settings

_FORBIDDEN = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "exec",
        "execute",
        "call",
        "copy",
        "vacuum",
        "pragma",
        "attach",
        "detach",
        "replace",
        "merge",
        "handler",
        "load",
    }
)
# Functions that access files, external resources or server state are not analytics.
_ALLOWED_FUNCTIONS = frozenset(
    {
        "AND",
        "OR",
        "CASE",
        "EXISTS",
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "COALESCE",
        "NULLIF",
        "IF",
        "IIF",
        "ABS",
        "ROUND",
        "FLOOR",
        "CEIL",
        "CEILING",
        "POWER",
        "SQRT",
        "MOD",
        "CAST",
        "TRY_CAST",
        "EXTRACT",
        "DATE",
        "DATETIME",
        "TIME",
        "STRFTIME",
        "JULIANDAY",
        "UNIXEPOCH",
        "DATE_TRUNC",
        "TIMESTAMP_TRUNC",
        "TIMESTAMP",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP",
        "CURRENT_TIME",
        "NOW",
        "DATE_ADD",
        "DATE_SUB",
        "DATE_DIFF",
        "TIME_TO_STR",
        "TS_OR_DS_TO_TIMESTAMP",
        "TS_OR_DS_TO_DATE",
        "STR_TO_TIME",
        "TIME_TO_UNIX",
        "UNIX_TO_TIME",
        "LOWER",
        "UPPER",
        "LENGTH",
        "CHAR_LENGTH",
        "SUBSTRING",
        "TRIM",
        "CONCAT",
        "JSON_EXTRACT",
        "JSON_EXTRACT_SCALAR",
        "JSON_ARRAY_LENGTH",
        "JSON_TYPE",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "PERCENT_RANK",
        "NTILE",
        "GREATEST",
        "LEAST",
        "FILTER",
        "TO_CHAR",
    }
)


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`|--[^\n]*|/\*[\s\S]*?\*/", " ", sql)


def _parse(sql: str, dialect: str = "sqlite"):
    statements = sqlglot.parse(sql, read="postgres" if dialect == "postgresql" else "sqlite")
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("multiple statements not allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Query) or not tree.find(exp.Select):
        raise ValueError("only SELECT/WITH queries allowed")
    for node in tree.walk():
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Drop,
                exp.Command,
                exp.Into,
                exp.Lock,
            ),
        ):
            raise ValueError("only read-only SELECT queries allowed")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name()
            if name not in _ALLOWED_FUNCTIONS:
                raise ValueError(f"function {name} is not allowed in analytics queries")
    return tree


def validate_shape(sql: str | None) -> tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "empty SQL"
    stripped = _strip_literals(sql).strip().rstrip(";")
    if ";" in stripped:
        return False, "multiple statements not allowed"
    if not re.match(r"(?i)^(SELECT|WITH)\b", stripped):
        return False, "only SELECT/WITH queries allowed"
    bad = set(re.findall(r"\b\w+\b", stripped.lower())) & _FORBIDDEN
    if bad:
        return False, f"forbidden keyword: {sorted(bad)[0]}"
    try:
        _parse(sql)
    except (ValueError, sqlglot.errors.SqlglotError) as exc:
        return False, str(exc)
    return True, ""


def physical_tables(tree) -> list[exp.Table]:
    tables = []
    for scope in traverse_scope(tree):
        for _node, source in scope.selected_sources.values():
            if isinstance(source, exp.Table):
                if source.name.lower() != "events" or source.db or source.catalog:
                    raise ValueError(
                        f"query references unknown tables: {source.sql()} (only 'events' is queryable)"
                    )
                tables.append(source)
    return tables


def scoped_sql(sql: str, project_id: str, dialect: str, start=None, end=None) -> tuple[str, dict]:
    tree = _parse(sql, dialect)
    for table in physical_tables(tree):
        alias = table.alias_or_name
        # Construct the filter ourselves; a generated OR/UNION cannot widen it.
        scoped = (
            exp.select("*")
            .from_("events")
            .where(exp.column("project_id").eq(exp.Var(this=":metricairn_project")))
            .where(exp.column("name").isin("ask", "mcp_tool_call").not_())
        )
        if start is not None and end is not None:
            scoped = scoped.where(
                exp.GTE(this=exp.column("created_at"), expression=exp.Var(this=":metricairn_start"))
            ).where(
                exp.LT(this=exp.column("created_at"), expression=exp.Var(this=":metricairn_end"))
            )
        table.replace(scoped.subquery(alias))
    params = {"metricairn_project": project_id}
    if start is not None and end is not None:
        from app.services.analytics import _naive_utc

        params.update(
            {
                "metricairn_start": _naive_utc(start).isoformat(sep=" ", timespec="microseconds")
                if dialect == "sqlite"
                else start,
                "metricairn_end": _naive_utc(end).isoformat(sep=" ", timespec="microseconds")
                if dialect == "sqlite"
                else end,
            }
        )
    return tree.sql(dialect="postgres" if dialect == "postgresql" else "sqlite"), params


def execute(
    db,
    sql: str,
    timeout_s: float | None = None,
    row_cap: int | None = None,
    project_id: str | None = None,
    start=None,
    end=None,
) -> dict:
    ok, reason = validate_shape(sql)
    if not ok:
        return {"ok": False, "reason": reason}
    settings = get_settings()
    timeout_s = timeout_s if timeout_s is not None else settings.agentic_sql_timeout_s
    row_cap = row_cap if row_cap is not None else settings.agentic_sql_row_cap
    if timeout_s <= 0 or row_cap < 1:
        return {"ok": False, "reason": "invalid query resource limits"}
    bind = db.get_bind()
    deadline = time.monotonic() + timeout_s
    raw = None
    try:
        params = {}
        allowed_reads = {"events"} | {
            cte.alias for cte in _parse(sql, bind.dialect.name).find_all(exp.CTE)
        }
        if project_id is not None:
            sql, params = scoped_sql(sql, project_id, bind.dialect.name, start, end)
        with bind.connect() as conn:
            try:
                if bind.dialect.name == "sqlite":
                    raw = conn.connection.driver_connection
                    raw.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)

                    def authorize(action, arg1, arg2, _db, _trigger):
                        if action == sqlite3.SQLITE_READ and arg1 not in allowed_reads:
                            return sqlite3.SQLITE_DENY
                        if action not in (
                            sqlite3.SQLITE_SELECT,
                            sqlite3.SQLITE_READ,
                            sqlite3.SQLITE_FUNCTION,
                            sqlite3.SQLITE_RECURSIVE,
                        ):
                            return sqlite3.SQLITE_DENY
                        return sqlite3.SQLITE_OK

                    raw.set_authorizer(authorize)
                elif bind.dialect.name == "postgresql":
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                    conn.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_s * 1000)}'"))
                else:
                    return {"ok": False, "reason": "unsupported SQL sandbox dialect"}
                cursor = conn.execute(text(sql), params)
                columns = list(cursor.keys())
                rows = cursor.fetchmany(row_cap)
                truncated = cursor.fetchone() is not None
                return {
                    "ok": True,
                    "columns": columns,
                    "rows": [tuple(r) for r in rows],
                    "truncated": truncated,
                }
            finally:
                if raw is not None:
                    raw.set_authorizer(None)
                    raw.set_progress_handler(None, 0)
    except Exception as exc:
        if time.monotonic() >= deadline or "statement timeout" in str(exc):
            return {"ok": False, "reason": f"query timed out after {timeout_s}s"}
        # No connection strings or SQLAlchemy parameter dumps in API responses.
        return {"ok": False, "reason": f"execution failed: {type(exc).__name__}"}
