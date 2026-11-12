import argparse, os, sys, yaml
from . import checks, anomaly, report, notify, ml, logs, rag
from .models import at_least, SEV_ORDER


def run(cfg, demo=False, use_llm=True, notify_on=True):
    if demo:
        from .demo import DemoCM
        cm = DemoCM()
    else:
        from .cm_client import CMClient
        cm = CMClient(cfg["cloudera_manager"])
    c = cfg["checks"]
    findings = []
    for cl in cm.clusters():
        findings += checks.check_services_and_roles(cm, cl["name"])
    findings += checks.check_hosts(cm, c["host_heartbeat_max_age_s"])
    findings += checks.check_alert_events(cm, c["events_lookback_hours"])

    store = anomaly.Store(":memory:" if demo else cfg["state_db"])
    for name, q in c["metrics"].items():
        try:
            for s in cm.timeseries(q, c["lookback_hours"]):
                store.add(name, s["entity"], s["points"])
                findings += anomaly.evaluate_metric(name, s["entity"], s["points"], c["thresholds"], store, c)
        except Exception as e:  # one broken metric query must not kill the run
            from .models import Finding
            findings.append(Finding("INFO", "collector", name, f"metric query failed: {e}"))

    emb, zs = ml.build(cfg.get("ml", {})) if not demo else (None, None)
    lc = cfg.get("logs", {})
    if lc.get("enabled") or demo:
        from .demo import DEMO_LOG
        ls = logs.LogStore(":memory:" if demo else cfg["state_db"])
        if demo:  # learn a baseline first, then scan a window containing a new fault
            logs.scan(lc, ls, lines=[("nn.log", l) for l in DEMO_LOG[:3]])
        findings += logs.scan(lc, ls, emb, zs, lines=[("nn.log", l) for l in DEMO_LOG] if demo else None)
    context = None
    rb = cfg.get("rag", {}).get("runbook_dir")
    if rb and findings:
        q = " ".join(f.message for f in findings if f.severity != "INFO")[:2000]
        context = [c for _, c in rag.retrieve(q, rag.load_chunks(rb), emb, cfg["rag"].get("top_k", 3))]
    narrative = None
    if use_llm and cfg["llm"].get("enabled") and findings:
        from . import llm
        try:
            narrative = llm.summarize(findings, cfg["llm"], context)
        except Exception as e:
            narrative = f"_LLM triage unavailable ({e}); raw findings below are still authoritative._"
    md = report.render(findings, narrative)
    path = report.save(md, cfg.get("report_dir", "./reports"))
    worst = max((f.severity for f in findings), key=lambda s: SEV_ORDER[s], default="OK")
    if notify_on and findings and at_least(worst, cfg["notify"].get("min_severity", "WARNING")):
        notify.send(md, worst, cfg["notify"])
    return md, path, worst


def cli():
    ap = argparse.ArgumentParser("cdp_health")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--demo", action="store_true", help="synthetic data, no cluster needed")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config if os.path.exists(a.config) else "config.example.yaml"))
    md, path, worst = run(cfg, a.demo, not a.no_llm, not a.no_notify)
    print(md); print(f"\nSaved: {path}")
    sys.exit({"OK": 0, "INFO": 0, "WARNING": 1, "CRITICAL": 2}[worst])  # usable by cron/Airflow/Nagios


if __name__ == "__main__":
    cli()
