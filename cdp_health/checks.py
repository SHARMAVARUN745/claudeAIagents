"""Deterministic checks over Cloudera Manager health/inventory data."""
import time
from datetime import datetime, timezone
from .models import Finding

_SEV = {"BAD": "CRITICAL", "CONCERNING": "WARNING"}


def _health_findings(kind, subject, obj):
    out = []
    summary = obj.get("healthSummary")
    for hc in obj.get("healthChecks", []) or []:
        if hc.get("suppressed") or hc.get("summary") in ("GOOD", "DISABLED", "NOT_AVAILABLE", None):
            continue
        sev = _SEV.get(hc["summary"], "INFO")
        out.append(Finding(sev, f"cm.{kind}", subject,
                           f"Health check {hc['name']} is {hc['summary']}",
                           {"explanation": hc.get("explanation"), "rollup": summary}))
    if not out and summary in _SEV:
        out.append(Finding(_SEV[summary], f"cm.{kind}", subject, f"{kind} health is {summary}"))
    return out


def check_services_and_roles(cm, cluster):
    out = []
    for svc in cm.services(cluster):
        name = svc["name"]
        if svc.get("serviceState") not in (None, "STARTED"):
            out.append(Finding("CRITICAL", "cm.service", f"{cluster}/{name}",
                               f"Service state is {svc.get('serviceState')} (expected STARTED)"))
        out += _health_findings("service", f"{cluster}/{name}", svc)
        for role in cm.roles(cluster, name):
            subj = f"{name}/{role['type']}@{role.get('hostRef', {}).get('hostname', '?')}"
            if role.get("roleState") not in (None, "STARTED"):
                out.append(Finding("CRITICAL", "cm.role", subj, f"Role state is {role['roleState']}"))
            out += _health_findings("role", subj, role)
    return out


def check_hosts(cm, max_age_s):
    out, now = [], datetime.now(timezone.utc)
    for h in cm.hosts():
        name = h.get("hostname", h.get("hostId"))
        hb = h.get("lastHeartbeat")
        if hb:
            age = (now - datetime.fromisoformat(hb.replace("Z", "+00:00"))).total_seconds()
            if age > max_age_s:
                out.append(Finding("CRITICAL", "cm.host", name, f"Agent heartbeat stale ({int(age)}s)",
                                   {"threshold_s": max_age_s}))
        out += _health_findings("host", name, h)
    return out


def check_alert_events(cm, hours):
    out = []
    for e in cm.events(hours):
        attrs = {a["name"]: a.get("values") for a in e.get("attributes", [])}
        out.append(Finding("WARNING", "cm.event", ",".join(attrs.get("SERVICE", ["cluster"])),
                           (e.get("content") or "")[:300],
                           {"category": e.get("category"), "time": e.get("timeOccurred")}))
    return out
