"""Tiny runbook retriever: embeddings if available, else keyword overlap. Grounds the LLM in YOUR procedures."""
import glob
import re
from .ml import cosine


def load_chunks(directory):
    chunks = []
    for fp in glob.glob(f"{directory}/**/*.md", recursive=True):
        for part in re.split(r"\n(?=#{1,3} )", open(fp, errors="replace").read()):
            if part.strip():
                chunks.append((fp, part.strip()[:1500]))
    return chunks


def _kw(text):
    return set(re.findall(r"[a-z_]{4,}", text.lower()))


def retrieve(query, chunks, embedder=None, k=3):
    if not chunks:
        return []
    if embedder:
        qv = embedder.encode([query])[0]
        cv = embedder.encode([c for _, c in chunks])
        scored = [(cosine(qv, v), c) for v, c in zip(cv, chunks)]
    else:
        q = _kw(query)
        scored = [(len(q & _kw(c[1])) / (len(q) or 1), c) for c in chunks]
    return [c for s, c in sorted(scored, key=lambda x: -x[0])[:k] if s > 0]
