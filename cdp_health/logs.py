"""Log anomaly detection: templatise ERROR/WARN lines, learn what is 'normal', flag novel patterns.
Deterministic keyword rules always run; BERT embeddings/zero-shot refine novelty and severity if enabled."""
import glob
import json
import re
import sqlite3
from .models import Finding
from .ml import cosine

LEVEL_RE = re.compile(r"\b(ERROR|WARN(?:ING)?|FATAL|SEVERE)\b|Exception|Traceback")
CRITICAL_RE = re.compile(r"OutOfMemoryError|No space left on device|Corrupt|BlockMissing|"
                         r"Could not obtain block|Too many open files|Unable to connect to ZooKeeper|"
                         r"SafeMode|Split brain|GSS initiate failed|Checksum error", re.I)
LABELS = ["data loss or corruption", "service outage", "performance degradation", "routine noise"]
_MASKS = [(re.compile(r"\b\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d[,.\d]*Z?\b"), ""),
          (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<IP>"),
          (re.compile(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{8}-[0-9a-f-]{27}\b", re.I), "<HEX>"),
          (re.compile(r"blk_-?\d+(_\d+)?"), "<BLK>"),
          (re.compile(r"(?:/[\w.\-]+){2,}"), "<PATH>"),
          (re.compile(r"application_\d+_\d+|container_\w+|attempt_\w+"), "<YARNID>"),
          (re.compile(r"\b\d+\b"), "<N>")]


def templatize(line: str) -> str:
    for rx, rep in _MASKS:
        line = rx.sub(rep, line)
    return re.sub(r"\s+", " ", line).strip()[:300]


class LogStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS tpl(t TEXT PRIMARY KEY, n INT, emb TEXT)")

    def known(self):
        return {t: (n, json.loads(e) if e else None) for t, n, e in self.db.execute("SELECT t,n,emb FROM tpl")}

    def upsert(self, t, n, emb):
        self.db.execute("INSERT INTO tpl VALUES(?,?,?) ON CONFLICT(t) DO UPDATE SET n=n+excluded.n",
                        (t, n, json.dumps(emb) if emb else None))
        self.db.commit()


def read_lines(cfg):
    for pat in cfg.get("paths", []):
        for fp in glob.glob(pat):
            with open(fp, errors="replace") as f:
                lines = f.readlines()[-cfg.get("tail_lines", 20000):]
            for ln in lines:
                yield fp, ln.rstrip()


def scan(cfg, store, embedder=None, zeroshot=None, lines=None):
    """lines: optional iterable of (source, line) - used by tests/demo."""
    src = lines if lines is not None else read_lines(cfg)
    counts, example = {}, {}
    for fp, ln in src:
        if LEVEL_RE.search(ln):
            t = templatize(ln)
            counts[t] = counts.get(t, 0) + 1
            example.setdefault(t, (fp, ln[:400]))
    known = store.known()
    bootstrapping = not known
    thr = cfg.get("novelty_similarity", 0.85)
    new = [t for t in counts if t not in known]
    embs = dict(zip(new, embedder.encode(new))) if embedder and new else {}
    known_vecs = [e for _, e in known.values() if e]
    out = []
    for t in new:
        fp, ex = example[t]
        near = max((cosine(embs[t], k) for k in known_vecs), default=0.0) if t in embs else 0.0
        variant = near >= thr           # semantically close to something already seen -> not novel
        crit = bool(CRITICAL_RE.search(ex))
        sev = "CRITICAL" if crit else "WARNING"
        label = None
        if zeroshot and not crit and not variant:
            label, score = zeroshot.classify(ex, LABELS)
            if label in LABELS[:2] and score > 0.6:
                sev = "CRITICAL"
            elif label == "routine noise" and score > 0.7:
                sev = "INFO"
        if (variant or bootstrapping) and not crit:
            continue                    # learn silently; deterministic critical keywords always alert
        out.append(Finding(sev, "log.novel", fp, f"New log pattern x{counts[t]}: {ex[:200]}",
                           {"template": t, "count": counts[t], "nearest_similarity": round(near, 2),
                            "zero_shot": label}))
    for t, n in counts.items():
        store.upsert(t, n, embs.get(t))
    return out
