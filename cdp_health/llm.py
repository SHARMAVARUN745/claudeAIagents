"""LLM triage layer. The LLM never detects anything: it only explains, groups and prioritises
findings that deterministic checks already produced."""
import json
import os
import re
import requests

SYSTEM = """You are a senior Cloudera (CDP/CDH) platform SRE. You receive JSON findings produced by
deterministic health checks on an on-prem cluster. Tasks:
1. Group findings that share a probable root cause (e.g. one failed disk -> DataNode role + volume check + under-replicated blocks).
2. Rank groups by business impact: data loss risk > outage > degradation > capacity trend > noise.
3. For each group give: Likely cause (state confidence), Impact, and Next diagnostic steps as read-only
   commands or CM UI paths. Mark any step that changes state as 'REQUIRES CHANGE APPROVAL'.
4. Never invent metrics or hosts that are not in the input. If evidence is insufficient, say so.
Output concise Markdown: '## Executive summary' (3 lines max), then '## Issues' ordered by priority."""

_HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b|\b\d{1,3}(?:\.\d{1,3}){3}\b", re.I)


class Redactor:
    """Stable token mapping so the LLM can correlate hosts without seeing real names."""
    def __init__(self): self.m = {}
    def __call__(self, text):
        def sub(mo):
            return self.m.setdefault(mo.group(0), f"HOST_{len(self.m) + 1:03d}")
        return _HOST_RE.sub(sub, text)
    def restore(self, text):
        for real, tok in self.m.items():
            text = text.replace(tok, real)
        return text


def summarize(findings, cfg) -> str:
    items = [f.to_dict() for f in findings][: cfg.get("max_findings_in_prompt", 60)]
    payload = json.dumps(items, indent=1, default=str)
    red = Redactor() if cfg.get("redact_hostnames") else None
    if red:
        payload = red(payload)
    key = os.environ.get(cfg.get("api_key_env", ""), "")
    if cfg["provider"] == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=cfg["model"], max_tokens=2500, system=SYSTEM,
                                   messages=[{"role": "user", "content": payload}])
        text = r.content[0].text
    else:  # any OpenAI-compatible on-prem server (vLLM, Ollama, TGI, LiteLLM...)
        r = requests.post(f"{cfg['base_url'].rstrip('/')}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"} if key else {},
                          json={"model": cfg["model"], "temperature": 0.1,
                                "messages": [{"role": "system", "content": SYSTEM},
                                             {"role": "user", "content": payload}]},
                          timeout=180)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    return red.restore(text) if red else text
