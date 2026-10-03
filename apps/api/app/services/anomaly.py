"""Anomaly detection over daily metric series.

Rolling robust z-score with a same-weekday baseline: each day is compared
against the median/MAD of the same weekday over the previous 4 weeks
(modified z-score, Iglewicz & Hoaglin). Same-weekday comparison means regular
weekly seasonality (quiet weekends) never fires; a launch spike can't poison
the baseline for other weekdays; and the detector works on any query window
because it always fetches 28 days of baseline history behind the window.

The incomplete current day is excluded — a partial bucket always looks like
a dip.

On top of per-day flags, sustained runs are detected: 3+ consecutive days
that each deviate in the same direction (|z| >= 1.5). A multi-day total outage
is an overwhelming signal jointly even when a single day sits under the
per-day bar. Merged run anomalies replace their individual days to avoid
double-reporting.
"""

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services import analytics

_BASELINE_WEEKS = 4
_MIN_BASELINE_POINTS = 3
_SUSTAINED_DAYS = 3  # consecutive days that make a sustained anomaly
_SUSTAINED_Z = 1.5  # per-day bar inside a sustained run


def _baseline(values: list[float], i: int) -> list[float]:
    """Same-weekday baseline over the prior 4 weeks; falls back to the trailing
    14 days when same-weekday history is thin (young projects / short windows)."""
    same_weekday = [values[i - 7 * w] for w in range(1, _BASELINE_WEEKS + 1) if i - 7 * w >= 0]
    if sum(1 for v in same_weekday if v != 0) >= _MIN_BASELINE_POINTS:
        return same_weekday
    trailing = values[max(0, i - 14) : i]
    if len(trailing) >= 7:
        return trailing
    return []


def _robust_z(value: float, baseline: list[float]) -> tuple[float, float]:
    med = statistics.median(baseline)
    mad = statistics.median([abs(v - med) for v in baseline])
    scale = max(mad, 0.12 * abs(med), 1e-9)  # floor: don't explode on flat baselines
    return 0.6745 * (value - med) / scale, med


def _sustained_runs(scores: list[tuple[float, float]], blocked: set[int]) -> list[list[int]]:
    """Maximal runs of 3+ consecutive days, each |z| >= _SUSTAINED_Z, same sign.
    Positions in `blocked` (strong single-day flags) break runs and never join."""
    runs: list[list[int]] = []
    cur: list[int] = []
    for i, (z, _med) in enumerate(scores):
        if i in blocked or abs(z) < _SUSTAINED_Z:
            if len(cur) >= _SUSTAINED_DAYS:
                runs.append(cur)
            cur = []
        elif cur and i == cur[-1] + 1 and (z > 0) == (scores[cur[-1]][0] > 0):
            cur.append(i)
        else:
            if len(cur) >= _SUSTAINED_DAYS:
                runs.append(cur)
            cur = [i]
    if len(cur) >= _SUSTAINED_DAYS:
        runs.append(cur)
    return runs


def detect(
    db: Session, project_id: str, start: datetime, end: datetime, z_threshold: float = 2.5
) -> list[dict]:
    # Fetch 28 extra days behind the window so every scored day has a
    # same-weekday baseline even on short query windows.
    ext_start = start - timedelta(weeks=_BASELINE_WEEKS)
    anomalies: list[dict] = []
    for metric in ("pageviews", "revenue"):
        series = analytics.timeseries(db, project_id, metric, ext_start, end, interval="day")
        dates = [p["t"][:10] for p in series]
        values = [p["value"] for p in series]

        # The current day may be partial; same-day dips are clamped to zero in
        # scoring below (a partial day can only understate its total).
        today = datetime.now(timezone.utc).date().isoformat()

        start_day = start.date().isoformat()
        scored = [i for i, d in enumerate(dates) if d >= start_day]
        if not scored:
            continue

        scores: dict[int, tuple[float, float]] = {}
        for i in scored:
            baseline = _baseline(values, i)
            # No baseline, or a zero baseline (ramp-up / pre-launch): nothing to
            # compare against, so skip rather than manufacture a z-score.
            if not baseline or statistics.median(baseline) == 0:
                continue
            z, med = _robust_z(values[i], baseline)
            # The current day is partial: it can only understate its total, so a
            # same-day dip is meaningless — but a same-day spike already cleared
            # the bar with hours to spare, so spikes still count.
            if dates[i] == today and z < 0:
                z = 0.0
            scores[i] = (z, med)

        ordered = [scores[i] for i in sorted(scores)]
        # Strong single-day flags are reported as-is and never absorbed into runs.
        blocked = {pos for pos, (z, _med) in enumerate(ordered) if abs(z) >= z_threshold}
        runs = _sustained_runs(ordered, blocked)
        run_pos = {p for r in runs for p in r}  # positions within `ordered`
        series_by_pos = sorted(scores)  # ordered position -> series index

        for pos, i in enumerate(series_by_pos):
            if pos in run_pos:
                continue
            z, med = scores[i]
            if pos in blocked and values[i] != med:
                anomalies.append(
                    {
                        "date": dates[i],
                        "metric": metric,
                        "value": values[i],
                        "expected": round(med, 2),
                        "z_score": round(z, 2),
                        "direction": "spike" if z > 0 else "dip",
                    }
                )

        for r in runs:
            idx = [series_by_pos[p] for p in r]
            zs = [scores[i][0] for i in idx]
            meds = [scores[i][1] for i in idx]
            direction = "spike" if zs[0] > 0 else "dip"
            anomalies.append(
                {
                    "date": dates[idx[0]],
                    "date_end": dates[idx[-1]],
                    "days": len(idx),
                    "metric": metric,
                    "value": round(sum(values[i] for i in idx), 2),
                    "expected": round(sum(meds), 2),
                    "z_score": round(min(zs, key=abs), 2),
                    "direction": direction,
                    "sustained": True,
                }
            )
    anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)
    return anomalies
