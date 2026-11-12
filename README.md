# AI-assisted Cloudera Health Check (on-prem)

Collects health from **Cloudera Manager (CM)**, detects abnormalities with deterministic rules and
statistics, then uses an **LLM only to triage** (group root causes, prioritise, suggest read-only
diagnostics). Detection never depends on the LLM, so it stays auditable and works if the LLM is down.

```
 CM REST API ──► collectors ──► rules + stats ──► findings ──► LLM triage ──► report ──► Slack/Email
 (read-only)    (health,hosts,   (thresholds,      (JSON)      (on-prem or     (.md)      + exit code
                 roles,events,    MAD z-score,                   Claude API)              for cron/Airflow
                 tsquery)         capacity forecast)
                                       ▲
                                  SQLite baseline
```

## 1. Quick start (no cluster needed)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m cdp_health --demo --no-llm --no-notify     # synthetic cluster with injected faults
pytest -q
```
Exit code: `0` ok/info, `1` warning, `2` critical (wire it to Nagios/Airflow/cron alerts).

## 2. Connect to your cluster
1. **Create a CM user** with the *Read-Only* (or Auditor) role. The client only issues GET requests.
2. Find your API version: `curl -u user $CM_URL/api/version` → set `api_version`.
3. `cp config.example.yaml config.yaml`, set URL/CA path; `export CM_PASSWORD=...`
4. Validate metric names in **CM → Charts → Chart Builder** (tsquery names vary by version/service)
   and edit `checks.metrics` accordingly. A failing query becomes an INFO finding, not a crash.
5. `python -m cdp_health --no-llm --no-notify` and review the report in `./reports`.
6. Let it run for a few days: statistical baselines need ≥30 samples/metric (stored in SQLite).

## 3. What gets checked
| Layer | Check | Method |
|---|---|---|
| Services | state != STARTED, BAD/CONCERNING health checks | CM `/clusters/*/services` |
| Roles | stopped roles, failed health checks (DN volumes, NN GC, ZK quorum...) | CM `/roles` |
| Hosts | stale agent heartbeat, host health checks | CM `/hosts` |
| Alerts | CM alert events in last N h | CM `/events?query=alert==true` |
| Metrics | CPU, memory, swap, HDFS %, YARN pending apps | tsquery + thresholds |
| Anomalies | deviation from 14-day baseline | robust z-score (median/MAD) |
| Capacity | days until HDFS full | linear trend forecast |

### Extending (recommended next checks)
- **HDFS**: `hdfs dfsadmin -report`, `hdfs fsck / -blocks | tail`, small-files count, NN safemode, NN JMX `:9870/jmx`.
- **YARN**: ResourceManager `:8088/ws/v1/cluster/metrics` (unhealthy/lost NMs, pending containers).
- **Hive/Impala**: HMS DB connectivity, HS2 `beeline -e 'select 1'` canary, Impala `/queries` JSON failures.
- **Kafka/ZK/HBase**: under-replicated partitions, consumer lag, `echo ruok | nc zk 2181`, HBase regions in transition.
- **Security/ops**: Kerberos ticket/keytab expiry, TLS cert expiry, KDC reachability, NTP drift, disk SMART, parcel versions.
- **Synthetic canaries**: scheduled tiny HDFS write/read and Hive query; latency regression = anomaly.
Add each as a function returning `list[Finding]` in `cdp_health/checks.py` and call it from `main.run`.

## 4. LLM layer choices (on-prem data governance)
| Option | Config | Notes |
|---|---|---|
| Local OpenAI-compatible server (**recommended on-prem**) | `provider: openai_compat`, `base_url` | vLLM / Ollama / TGI / LiteLLM; 70B-class model for good triage; data stays inside network |
| Claude API | `provider: anthropic` | Needs outbound HTTPS to Anthropic from a bastion/proxy; keep `redact_hostnames: true`; get security sign-off |
| None | `llm.enabled: false` or `--no-llm` | Pure rule/stat report |

Guardrails built in: hostname/IP redaction with reversible tokens, temperature 0.1, prompt forbids
inventing data, state-changing steps must be flagged `REQUIRES CHANGE APPROVAL`, LLM failure falls back to raw findings.
**Do not give the LLM write access to the cluster** until you have run read-only for weeks; if you later add
remediation (restart role, etc.), put it behind a human approval step.

### 4a. Open-source models: Llama, BERT and friends
Generative (Llama etc.) and encoder (BERT) models do different jobs. Use both:

| Job | Model | Why | Where in code |
|---|---|---|---|
| Triage narrative, root-cause grouping, next steps | **Llama 3.x Instruct** (8B light / 70B best), also Qwen2.5, Mistral | Generates text; BERT cannot | `llm.py` via any OpenAI-compatible server |
| Log anomaly: "is this error pattern new/similar?" | **BERT-family embedder**: `bge-small-en-v1.5`, `all-MiniLM-L6-v2` | Fast on CPU, semantic similarity | `logs.py`, `ml.Embedder` |
| Severity/category of a new log line | **Zero-shot NLI**: `deberta-v3-base-zeroshot-v2.0` (or `bart-large-mnli`) | No labelled data needed | `ml.ZeroShot` |
| Runbook retrieval (RAG) for Llama | same embedder | Grounds answers in your SOPs | `rag.py` |
| Optional later: fine-tuned classifier | DistilBERT/RoBERTa on your labelled incidents | Beats zero-shot once you have ~1-2k labels | add alongside `ZeroShot` |

**Serve Llama on-prem** (pick one):
```bash
# Ollama: simplest, small/medium setups (8B fits a 16 GB GPU or runs slowly on CPU)
ollama pull llama3.1:8b && ollama serve            # base_url: http://host:11434/v1, model: llama3.1:8b
# vLLM: production throughput (70B needs ~2x80GB GPUs, or use a 4-bit AWQ build on 1-2 GPUs)
vllm serve meta-llama/Llama-3.3-70B-Instruct --tensor-parallel-size 2 --port 8000
```
Check the Llama licence terms for your use. **Air-gapped hosts:** download models on a connected machine
(`huggingface-cli download BAAI/bge-small-en-v1.5 --local-dir ...`), copy them in, point `ml.*_model` at the
local directory, and set `HF_HUB_OFFLINE=1`. Install `pip install sentence-transformers transformers torch`
(CPU build is enough for the BERT models).

**How the log detector works:** ERROR/WARN/FATAL lines are masked into templates (IPs, block IDs, paths, numbers
removed). The first run only learns the baseline. Later, a template never seen before is flagged unless its BERT
embedding is >= 0.85 similar to a known one (a variant). Deterministic keywords (OOM, no space left, checksum
error, safe mode...) are always CRITICAL, and zero-shot can upgrade or downgrade the rest. Without the ML
libraries it falls back to exact template novelty.

Expect a smaller Llama (8B) to follow the "don't invent" rule less reliably than 70B; keep the raw findings table authoritative.

## 5. Tool inventory
| Need | Tool |
|---|---|
| Source of truth | Cloudera Manager REST API (+ Cloudera Observability / Workload XM if licensed) |
| Service endpoints | NameNode/RM/HS2/Impala JMX & REST, `hdfs`, `yarn`, `beeline` CLIs |
| Runtime | Python 3.9+ on an edge node/bastion (`requests`, `PyYAML`) |
| Baseline store | SQLite (this repo) → upgrade to Postgres/Prometheus/VictoriaMetrics for scale |
| Stat detection | MAD z-score (here); upgrade: `ruptures`, `statsmodels`, Prophet, Isolation Forest |
| LLM | vLLM/Ollama (on-prem) or Claude API; optional RAG over your runbooks (pgvector/Chroma) |
| Orchestration | systemd timer / cron / Airflow / Oozie (files in `deploy/`) |
| Alerting | Slack/Teams webhook, SMTP, PagerDuty/ServiceNow (add in `notify.py`) |
| Secrets | env file `chmod 600`, or HashiCorp Vault / CyberArk |
| Dashboards (optional) | Grafana over Prometheus; Cloudera's own CM charts |
| Logs (optional) | Feed role logs (ELK/Splunk/Solr) in and let the LLM summarise error clusters |

## 6. Deploy
```bash
sudo useradd -r cdp-monitor; sudo mkdir /opt/cdp-health && sudo cp -r . /opt/cdp-health
cd /opt/cdp-health && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo install -m 600 /dev/null /etc/cdp-health.env   # then add CM_PASSWORD=..., LLM_API_KEY=...
sudo cp deploy/cdp-health.* /etc/systemd/system/ && sudo systemctl enable --now cdp-health.timer
```
(or use `deploy/airflow_dag.py`.) Run every 15 min; send a weekly digest by lowering `min_severity` to INFO.

## 7. Rollout plan
1. **Week 1 - shadow**: read-only, reports only to you; tune thresholds, fix noisy checks.
2. **Week 2-3 - alert**: enable Slack/email at CRITICAL; compare against CM's own alerts, add missing checks.
3. **Month 2 - enrich**: add runbook RAG, log summarisation, synthetic canaries, ticket creation.
4. **Later - gated remediation**: human-approved actions only, with audit log.

## 8. Known limits / verify before trusting
- tsquery metric names and CM API version differ per CDP/CDH release; verify in Chart Builder.
- Robust z-scores ignore seasonality (nightly batch peaks); for strongly cyclical metrics compare to same hour-of-week or use Prophet.
- Forecast is linear; step changes (big ingests) will skew it.
- The LLM can be wrong: treat its output as a triage aid; the raw findings table is the source of truth.
