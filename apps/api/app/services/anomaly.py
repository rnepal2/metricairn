"""Anomaly detection over daily metric series (z-score with robust fallback)."""

import statistics
from datetime import datetime

from sqlalchemy.orm import Session

from app.services import analytics


def detect(
    db: Session, project_id: str, start: datetime, end: datetime, z_threshold: float = 2.5
) -> list[dict]:
    anomalies: list[dict] = []
    for metric in ("pageviews", "revenue"):
        series = analytics.timeseries(db, project_id, metric, start, end, interval="day")
        values = [p["value"] for p in series]
        if len(values) < 7:
            continue
        mean = statistics.fmean(values)
        stdev = statistics.pstdev(values) or 1e-9
        for p in series:
            z = (p["value"] - mean) / stdev
            if abs(z) >= z_threshold and p["value"] != mean:
                anomalies.append(
                    {
                        "date": p["t"][:10],
                        "metric": metric,
                        "value": p["value"],
                        "expected": round(mean, 2),
                        "z_score": round(z, 2),
                        "direction": "spike" if z > 0 else "dip",
                    }
                )
    anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)
    return anomalies
