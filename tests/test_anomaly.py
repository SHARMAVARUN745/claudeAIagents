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


def test_logs_learn_then_flag():
    from cdp_health import logs
    st = logs.LogStore(":memory:")
    base = [("f", "2026-01-01 00:00:00,1 ERROR x.Y: failed blk_123_1 from 10.0.0.1:99")]
    assert logs.scan({}, st, lines=base) == []                       # bootstrap = learn silently
    same = [("f", "2026-02-02 01:01:01,9 ERROR x.Y: failed blk_999_7 from 10.9.9.9:11")]
    assert logs.scan({}, st, lines=same) == []                        # same template
    bad = [("f", "ERROR z.Q: No space left on device /data/1")]
    r = logs.scan({}, st, lines=bad)
    assert r and r[0].severity == "CRITICAL"


def test_rag_keyword():
    from cdp_health import rag
    ch = rag.load_chunks("runbooks")
    assert "DataNode volume" in rag.retrieve("DATA_NODE_VOLUME_FAILURES datanode volume", ch)[0][1]
