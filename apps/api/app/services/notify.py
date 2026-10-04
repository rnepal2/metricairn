"""Outbound notifications: Slack webhooks and email via Resend.

All sending is best-effort and synchronous (the scheduler runs in the
background anyway). Every attempt returns (ok, detail) so the caller can log
the outcome in alert_deliveries regardless of provider configuration.
"""

from __future__ import annotations

import html as _html

import httpx

from app.core.config import get_settings


def format_anomaly_message(
    project_name: str, anomalies: list[dict], *, test: bool = False
) -> tuple[str, str]:
    """Return (subject, body_text) for one or more anomalies.

    Keeps the message short enough for a phone notification: headline numbers
    first, one line of interpretation, no dashboard links to chase.
    """
    if test:
        return (
            f"AgentLens test alert — {project_name}",
            f"Hello from AgentLens! Alerts for project '{project_name}' are wired up correctly. "
            "You'll get a message like this when a real anomaly is detected.",
        )
    lines = []
    for a in anomalies:
        date = a["date"] + (f" → {a['date_end']}" if a.get("date_end") else "")
        if a["metric"] == "revenue":
            obs, exp = f"${a['value']:,.0f}", f"${a['expected']:,.0f}"
        else:
            obs, exp = f"{a['value']:,.0f}", f"{a['expected']:,.0f}"
        lines.append(
            f"• {a['metric']} {a['direction']} {date}: {obs} vs ~{exp} expected "
            f"(z={a['z_score']})"
        )
    n = len(anomalies)
    subject = f"AgentLens alert — {project_name}: {n} anomal{'y' if n == 1 else 'ies'}"
    body = (
        f"AgentLens detected {n} anomal{'y' if n == 1 else 'ies'} for '{project_name}':\n\n"
        + "\n".join(lines)
        + "\n\nAsk your AI agent \"why did this happen?\" for a grounded explanation."
    )
    return subject, body


def _as_html(subject: str, body: str) -> str:
    paras = "".join(f"<p>{_html.escape(p)}</p>" for p in body.split("\n\n"))
    return (
        "<!doctype html><html><body style='font-family:sans-serif;color:#0f172a'>"
        f"<h2 style='font-size:16px'>{_html.escape(subject)}</h2>{paras}"
        "<p style='color:#94a3b8;font-size:12px'>Sent by AgentLens anomaly alerts.</p>"
        "</body></html>"
    )


def send_slack(webhook_url: str, subject: str, body: str) -> tuple[bool, str]:
    try:
        r = httpx.post(
            webhook_url,
            json={"text": f"*{subject}*\n{body}"},
            timeout=15,
        )
        if r.status_code in (200, 201, 204):
            return True, f"slack http {r.status_code}"
        return False, f"slack http {r.status_code}: {r.text[:200]}"
    except Exception as e:  # noqa: BLE001 — delivery must never raise
        return False, f"slack error: {e}"


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    settings = get_settings()
    if not settings.resend_api_key:
        return False, "skipped: RESEND_API_KEY not configured"
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.alerts_from_email,
                "to": [to],
                "subject": subject,
                "html": _as_html(subject, body),
            },
            timeout=15,
        )
        if r.status_code in (200, 201, 202):
            return True, f"resend http {r.status_code}"
        return False, f"resend http {r.status_code}: {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, f"email error: {e}"


def deliver(channel_kind: str, target: str, subject: str, body: str) -> tuple[bool, str]:
    if channel_kind == "slack":
        return send_slack(target, subject, body)
    if channel_kind == "email":
        return send_email(target, subject, body)
    return False, f"unknown channel kind: {channel_kind}"
