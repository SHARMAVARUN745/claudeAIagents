"""Synthetic CM so you can test the whole pipeline without a cluster (--demo)."""
import math, random, time


class DemoCM:
    def clusters(self): return [{"name": "prod-cluster"}]

    def services(self, c):
        return [
            {"name": "hdfs", "serviceState": "STARTED", "healthSummary": "CONCERNING",
             "healthChecks": [{"name": "HDFS_UNDER_REPLICATED_BLOCKS", "summary": "CONCERNING",
                               "explanation": "4,213 under-replicated blocks (5.2% of total)"}]},
            {"name": "hive", "serviceState": "STARTED", "healthSummary": "GOOD", "healthChecks": []},
            {"name": "impala", "serviceState": "STOPPED", "healthSummary": "BAD", "healthChecks": []},
        ]

    def roles(self, c, s):
        if s == "hdfs":
            return [{"type": "DATANODE", "roleState": "STARTED", "healthSummary": "BAD",
                     "hostRef": {"hostname": "dn07.corp.local"},
                     "healthChecks": [{"name": "DATA_NODE_VOLUME_FAILURES", "summary": "BAD",
                                       "explanation": "1 volume failed on /data/5"}]}]
        return []

    def hosts(self):
        old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900))
        return [{"hostname": "dn07.corp.local", "lastHeartbeat": old, "healthChecks": [], "healthSummary": "GOOD"}]

    def events(self, hours=24, query=""):
        return [{"content": "Alert: NameNode GC pause 14s", "category": "HEALTH_CHECK",
                 "timeOccurred": "now", "attributes": [{"name": "SERVICE", "values": ["hdfs"]}]}]

    def timeseries(self, q, hours):
        n, now = hours * 12, time.time()
        pts = lambda f: [(now - (n - i) * 300, f(i)) for i in range(n)]
        rnd = random.Random(1)
        if "dfs_capacity" in q:
            return [{"entity": "hdfs", "metric": "m", "points": pts(lambda i: 70 + i * 0.05 + rnd.random())}]
        if "cpu" in q:
            return [{"entity": "dn07", "metric": "m", "points": pts(lambda i: 35 + 8 * math.sin(i / 9) + (55 if i > n - 6 else 0))}]
        return [{"entity": "dn07", "metric": "m", "points": pts(lambda i: 40 + rnd.random() * 5)}]


DEMO_LOG = [
    "2026-11-12 10:00:01,100 WARN  org.apache.hadoop.hdfs.server.datanode.DataNode: Slow BlockReceiver write 812ms blk_1073741825_1001",
    "2026-11-12 10:00:02,100 ERROR org.apache.hadoop.ipc.Server: IPC Server handler 5 on 8020 failed from 10.1.2.3:51234",
    "2026-11-12 10:00:03,100 WARN  org.apache.hadoop.hdfs.server.datanode.DataNode: Slow BlockReceiver write 903ms blk_1073741999_1002",
    "2026-11-12 11:30:00,000 FATAL org.apache.hadoop.hdfs.server.datanode.DataNode: Volume /data/5 failed: java.io.IOException: Checksum error on blk_1073749999_5555",
    "2026-11-12 11:31:00,000 ERROR org.apache.hadoop.hdfs.server.namenode.FSNamesystem: Unexpected rollover of edit log segment 4421",
]
