import os
from datetime import datetime
from .models import SEV_ORDER


def render(findings, narrative=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    counts = {s: sum(f.severity == s for f in findings) for s in ("CRITICAL", "WARNING", "INFO")}
    lines = [f"# Cloudera Health Report - {ts}", "",
             f"**CRITICAL: {counts['CRITICAL']} | WARNING: {counts['WARNING']} | INFO: {counts['INFO']}**", ""]
    if narrative:
        lines += ["## AI triage", narrative, ""]
    lines += ["## Raw findings", "", "| Sev | Source | Subject | Message |", "|---|---|---|---|"]
    for f in sorted(findings, key=lambda f: -SEV_ORDER[f.severity]):
        lines.append(f"| {f.severity} | {f.source} | {f.subject} | {f.message.replace('|', '/')} |")
    if not findings:
        lines.append("| - | - | - | No abnormalities detected |")
    return "\n".join(lines)


def save(md, report_dir):
    os.makedirs(report_dir, exist_ok=True)
    p = os.path.join(report_dir, f"health_{datetime.now():%Y%m%d_%H%M%S}.md")
    open(p, "w").write(md)
    return p
