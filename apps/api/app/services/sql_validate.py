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


def _from_targets(sql: str) -> set[str]:
    """Table names referenced by FROM/JOIN, minus CTE names."""
    stripped = _strip_literals(sql)
    ctes = set(re.findall(r"(?i)(?:WITH|,)\s*([a-zA-Z_]\w*)\s+AS\s*\(", stripped))
    targets = set(re.findall(r"(?i)\b(?:FROM|JOIN)\s+([a-zA-Z_]\w*)", stripped))
    return {t.lower() for t in targets} - {c.lower() for c in ctes}


def semantic_checks(sql: str, project_id: str) -> tuple[bool, str]:
    """Hard gates. Returns (ok, reason); failure means confidence 0."""
    unknown = _from_targets(sql) - _ALLOWED_TABLES
    if unknown:
        return False, f"query references unknown tables: {sorted(unknown)} (only 'events' is queryable)"
    stripped = _strip_literals(sql)
    if not re.search(r"(?i)\bproject_id\s*=", stripped):
        return False, "query does not filter on project_id (tenant scope is mandatory)"
    if project_id not in sql:
        return False, "query filters project_id but not to this project's id"
    return True, ""


def sanity_issues(question: str, sql: str) -> list[str]:
    """Soft question/SQL alignment checks. Each issue costs confidence."""
    issues: list[str] = []
    q = question.lower()
    s = _strip_literals(sql).lower()
    if "revenue" in q and "revenue_amount" not in s and not ("name" in s and "revenue" in s):
        issues.append("question is about revenue but the query doesn't touch revenue data")
    if re.search(r"\b(last|past|this|yesterday|today|week|month|year|days?)\b", q) and "created_at" not in s:
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
