"""Validation framework for agentic SQL.

Pipeline: static semantic checks → sandbox execution → result assessment →
confidence score. Anything below threshold becomes an honest fallback, never
an answer. Rules-based v1; an LLM second-opinion critic can plug into
``assess`` via ``critic_fn`` later.
"""

from __future__ import annotations

import re

from app.services.sql_sandbox import _strip_literals

_ALLOWED_TABLES = {"events"}
_CONFIDENCE_THRESHOLD = 0.6


def semantic_checks(sql: str, project_id: str) -> tuple[bool, str]:
    """Validate the AST. Tenant isolation is enforced again at execution."""
    from sqlglot import exp

    from app.services.sql_sandbox import _parse, physical_tables

    try:
        tree = _parse(sql)
        physical_tables(tree)
    except Exception as exc:
        return False, str(exc)
    for eq in tree.find_all(exp.EQ):
        for col, value in ((eq.left, eq.right), (eq.right, eq.left)):
            if isinstance(col, exp.Column) and col.name.lower() == "project_id":
                if isinstance(value, exp.Literal) and value.is_string and value.this == project_id:
                    return True, ""
    return False, "query does not filter project_id to this project's id"


def sanity_issues(question: str, sql: str) -> list[str]:
    """Soft question/SQL alignment checks. Each issue costs confidence."""
    issues: list[str] = []
    q = question.lower()
    s = _strip_literals(sql).lower()
    if "revenue" in q and "revenue_amount" not in s and not ("name" in s and "revenue" in s):
        issues.append("question is about revenue but the query doesn't touch revenue data")
    if (
        re.search(r"\b(last|past|this|yesterday|today|week|month|year|days?)\b", q)
        and "created_at" not in s
    ):
        issues.append("question implies a time window but the query doesn't filter created_at")
    return issues


def assess(question: str, sql: str, project_id: str) -> dict:
    """Pre-execution assessment. {"ok", "confidence", "issues"}."""
    ok, reason = semantic_checks(sql, project_id)
    if not ok:
        return {"ok": False, "confidence": 0.0, "issues": [reason]}
    issues = sanity_issues(question, sql)
    return {"ok": True, "confidence": max(0.0, 1.0 - 0.3 * len(issues)), "issues": issues}


def assess_result(assessment: dict, exec_result: dict) -> dict:
    """Post-execution assessment: fold result properties into confidence."""
    issues = list(assessment["issues"])
    conf = assessment["confidence"]
    if not exec_result.get("rows"):
        issues.append("query returned no rows")
        conf -= 0.2
    if exec_result.get("truncated"):
        issues.append("results were truncated at the row cap")
        conf -= 0.1
    return {"confidence": max(0.0, conf), "issues": issues}


def confidence_threshold() -> float:
    return _CONFIDENCE_THRESHOLD
