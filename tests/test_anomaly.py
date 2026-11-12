import time
from cdp_health import anomaly


def test_robust_z_flags_spike():
    hist = [50 + (i % 5) for i in range(100)]
    assert anomaly.robust_z(hist, 95) > 4
    assert abs(anomaly.robust_z(hist, 52)) < 4


def test_days_to_full():
    now = time.time()
    pts = [(now - (20 - i) * 86400, 60 + i) for i in range(20)]   # +1%/day, at 79%
    assert 19 < anomaly.days_to_full(pts) < 22
    assert anomaly.days_to_full([(now - i, 50) for i in range(20)]) is None


def test_demo_pipeline():
    import yaml
    from cdp_health.main import run
    cfg = yaml.safe_load(open("config.example.yaml"))
    md, _, worst = run(cfg, demo=True, use_llm=False, notify_on=False)
    assert worst == "CRITICAL" and "DATA_NODE_VOLUME_FAILURES" in md
