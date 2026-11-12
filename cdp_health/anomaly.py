"""Metric anomaly detection: thresholds + robust z-score vs history + capacity forecast."""
import sqlite3
import statistics
import time
from .models import Finding


class Store:
    def __init__(self, path):
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS m(ts REAL, metric TEXT, entity TEXT, v REAL, "
                        "PRIMARY KEY(ts, metric, entity))")

    def add(self, metric, entity, points):
        self.db.executemany("INSERT OR IGNORE INTO m VALUES(?,?,?,?)",
                            [(p[0], metric, entity, p[1]) for p in points])
        self.db.commit()

    def history(self, metric, entity, days):
        cutoff = time.time() - days * 86400
        return self.db.execute("SELECT ts, v FROM m WHERE metric=? AND entity=? AND ts>=? ORDER BY ts",
                               (metric, entity, cutoff)).fetchall()


def robust_z(history, value):
    if len(history) < 30:
        return None  # not enough baseline
    med = statistics.median(history)
    mad = statistics.median(abs(x - med) for x in history) or 1e-9
    return 0.6745 * (value - med) / mad


def days_to_full(points, full_at=100.0):
    """Least-squares slope on (ts, pct). Returns days until `full_at`, or None if flat/falling."""
    n = len(points)
    if n < 10:
        return None
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den   # pct per second
    if slope <= 0:
        return None
    return (full_at - ys[-1]) / slope / 86400


def evaluate_metric(name, entity, points, thr, store, cfg):
    """points = [(epoch_s, value)] for the lookback window (already stored by caller)."""
    out = []
    if not points:
        return out
    latest = points[-1][1]
    t = thr.get(name)
    if t and "crit" in t and name != "days_to_full_hdfs":
        if latest >= t["crit"]:
            out.append(Finding("CRITICAL", "ts.threshold", entity, f"{name}={latest:.1f} >= {t['crit']}",
                               {"metric": name, "value": latest}))
        elif latest >= t["warn"]:
            out.append(Finding("WARNING", "ts.threshold", entity, f"{name}={latest:.1f} >= {t['warn']}",
                               {"metric": name, "value": latest}))
    hist = [v for _, v in store.history(name, entity, cfg["baseline_days"])]
    z = robust_z(hist[:-len(points)] or hist, latest)
    if z is not None and abs(z) >= cfg["zscore_threshold"]:
        out.append(Finding("WARNING", "ts.anomaly", entity,
                           f"{name} deviates from {cfg['baseline_days']}d baseline (robust z={z:.1f}, now={latest:.1f})",
                           {"metric": name, "z": round(z, 2), "value": latest}))
    if name == "hdfs_used_pct":
        d = days_to_full(store.history(name, entity, min(cfg["baseline_days"], 14)))
        ft = thr.get("days_to_full_hdfs")
        if d is not None and ft:
            sev = "CRITICAL" if d <= ft["crit"] else "WARNING" if d <= ft["warn"] else None
            if sev:
                out.append(Finding(sev, "ts.forecast", entity, f"HDFS projected full in ~{d:.0f} days at current growth",
                                   {"days_to_full": round(d, 1)}))
    return out
