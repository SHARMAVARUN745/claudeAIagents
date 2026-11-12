"""Thin read-only Cloudera Manager REST client (GET only, by design)."""
import os
import time
import requests


class CMClient:
    def __init__(self, cfg: dict):
        self.base = f"{cfg['url'].rstrip('/')}/api/{cfg.get('api_version', 'v54')}"
        self.s = requests.Session()
        self.s.auth = (cfg["username"], os.environ[cfg.get("password_env", "CM_PASSWORD")])
        self.s.verify = cfg.get("verify_tls", True)
        self.timeout = cfg.get("timeout_s", 30)

    def get(self, path: str, **params):
        r = self.s.get(f"{self.base}{path}", params=params or None, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # --- inventory / health ---
    def clusters(self):
        return self.get("/clusters").get("items", [])

    def services(self, cluster: str):
        return self.get(f"/clusters/{cluster}/services", view="full").get("items", [])

    def roles(self, cluster: str, service: str):
        return self.get(f"/clusters/{cluster}/services/{service}/roles").get("items", [])

    def hosts(self):
        return self.get("/hosts", view="full").get("items", [])

    def events(self, hours: int = 24, query: str = "alert==true"):
        frm = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
        return self.get("/events", query=query, **{"from": frm}).get("items", [])

    def timeseries(self, tsquery: str, hours: int):
        now = time.time()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
        out = self.get("/timeseries", query=tsquery, **{"from": iso(now - hours * 3600), "to": iso(now)})
        series = []
        for item in out.get("items", []):
            for ts in item.get("timeSeries", []):
                md = ts["metadata"]
                pts = [(d["timestamp"], d["value"]) for d in ts.get("data", []) if d.get("value") is not None]
                series.append({"entity": md.get("entityName") or md.get("attributes", {}).get("hostname", "?"),
                               "metric": md.get("metricName"), "points": pts})
        return series
