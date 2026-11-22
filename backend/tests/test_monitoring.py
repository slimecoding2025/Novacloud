from novacloud.core.logging import JsonFormatter, redact
from novacloud.core.ratelimit import RateLimiter
from novacloud.monitoring.metrics import Metric, MetricsRegistry


def test_unavailable_source_is_not_reported_as_zero():
    r = MetricsRegistry()
    r.register(Metric("nc_up", "ok", "static", "gauge", lambda: 1))
    def broken(): raise RuntimeError("db down")
    r.register(Metric("nc_jobs", "jobs", "postgres:jobs", "gauge", broken))
    out = r.render()
    assert "nc_up 1" in out
    assert "nc_jobs " not in out.replace("# ", "")  # no value line for the broken metric
    assert 'novacloud_metric_available{metric="nc_jobs",source="postgres:jobs"} 0' in out


def test_labels_and_counters():
    r = MetricsRegistry()
    r.counter_metric("nc_req_total", "requests", "api middleware", ("method", "status"))
    r.inc("nc_req_total", ("GET", "200")); r.inc("nc_req_total", ("GET", "200"))
    assert 'nc_req_total{method="GET",status="200"} 2.0' in r.render()


def test_redaction_and_json_logs():
    import json, logging
    assert redact({"Authorization": "x", "a": [{"session_token": "y"}]}) == {"Authorization": "[REDACTED]", "a": [{"session_token": "[REDACTED]"}]}
    rec = logging.LogRecord("n", logging.INFO, "f", 1, "msg", None, None)
    rec.fields = {"password": "p", "ok": 1}
    d = json.loads(JsonFormatter().format(rec))
    assert d["password"] == "[REDACTED]" and d["ok"] == 1


def test_rate_limiter_window():
    t = [0.0]
    rl = RateLimiter(2, 60, clock=lambda: t[0])
    assert rl.allow("k") and rl.allow("k") and not rl.allow("k") and rl.allow("other")
    t[0] = 61
    assert rl.allow("k")
