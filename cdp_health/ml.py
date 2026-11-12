"""Optional open-source model wrappers (BERT-family). Lazy imports: the tool still runs without them."""
import math


class Embedder:
    """Sentence embeddings via sentence-transformers (BERT-family: all-MiniLM-L6-v2, bge-small-en-v1.5...)."""
    def __init__(self, model_name_or_path):
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(model_name_or_path)   # point at a local dir for air-gapped hosts

    def encode(self, texts):
        return [list(map(float, v)) for v in self.m.encode(texts, normalize_embeddings=True)]


class ZeroShot:
    """NLI zero-shot classifier (e.g. MoritzLaurer/deberta-v3-base-zeroshot-v2.0, a BERT-family model)."""
    def __init__(self, model_name_or_path):
        from transformers import pipeline
        self.p = pipeline("zero-shot-classification", model=model_name_or_path)

    def classify(self, text, labels):
        r = self.p(text, candidate_labels=labels)
        return r["labels"][0], float(r["scores"][0])


def cosine(a, b):
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def build(cfg):
    """Return (embedder|None, zeroshot|None); degrade gracefully if libs/models are missing."""
    emb = zs = None
    try:
        if cfg.get("embedding_model"):
            emb = Embedder(cfg["embedding_model"])
    except Exception as e:
        print(f"[warn] embeddings disabled: {e}")
    try:
        if cfg.get("classifier_model"):
            zs = ZeroShot(cfg["classifier_model"])
    except Exception as e:
        print(f"[warn] classifier disabled: {e}")
    return emb, zs
