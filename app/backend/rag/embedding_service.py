import os
import logging
from functools import lru_cache
from typing import List

import certifi
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

###############################################################################
# SWITCH EMBEDDING PROVIDER HERE
# Change this one line only:
#   "huggingface"  -> MiniLM from Sentence Transformers
#   "ollama"       -> local Ollama embeddings
###############################################################################
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface").strip().lower()
EMBEDDING_FALLBACK_PROVIDER = "ollama"  # fallback if HuggingFace fails

###############################################################################
# HuggingFace / Sentence Transformers
###############################################################################
HF_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

###############################################################################
# Ollama
###############################################################################
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

###############################################################################
# TLS / download setup for HuggingFace
###############################################################################

def _setup_hf_tls() -> None:
    """
    Make Hugging Face downloads use a trusted CA store.
    """
    try:
        import truststore  # pip install truststore

        truststore.inject_into_ssl()
        logger.info("[EMBEDDINGS] Using OS trust store via truststore")
    except Exception as e:
        logger.info("[EMBEDDINGS] truststore not available: %s", e)

    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())


_setup_hf_tls()


def _embed_ollama(text: str) -> list[float]:
    url = f"{OLLAMA_URL.rstrip('/')}/api/embeddings"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": text,
    }

    response = requests.post(
        url,
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    embedding = data.get("embedding", [])

    if not isinstance(embedding, list):
        raise ValueError("Ollama returned an invalid embedding payload")

    return [float(x) for x in embedding]


@lru_cache(maxsize=1)
def _load_hf_model():
    from sentence_transformers import SentenceTransformer

    logger.info("[EMBEDDINGS] Loading HuggingFace model: %s", HF_MODEL)
    return SentenceTransformer(HF_MODEL)


def _embed_huggingface(text: str) -> list[float]:
    model = _load_hf_model()
    vec = model.encode(text, normalize_embeddings=True)

    if hasattr(vec, "tolist"):
        return vec.tolist()

    return list(vec)


def get_embedding_model_name() -> str:
    if EMBEDDING_PROVIDER == "huggingface":
        return HF_MODEL
    if EMBEDDING_PROVIDER == "ollama":
        return OLLAMA_MODEL
    if EMBEDDING_PROVIDER == "lexical":
        return "lexical-fallback"
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def embed_text(text: str) -> List[float]:
    """
    Returns one embedding vector.

    Default:
        HuggingFace MiniLM

    Fallback:
        Ollama nomic-embed-text if HuggingFace fails
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    if EMBEDDING_PROVIDER == "lexical":
        return []

    if EMBEDDING_PROVIDER == "huggingface":
        try:
            return _embed_huggingface(cleaned)
        except Exception as e:
            logger.warning(
                "[EMBEDDINGS] HuggingFace failed, falling back to Ollama: %s",
                e,
            )
            if EMBEDDING_FALLBACK_PROVIDER == "ollama":
                return _embed_ollama(cleaned)
            raise

    if EMBEDDING_PROVIDER == "ollama":
        return _embed_ollama(cleaned)

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        vectors.append(embed_text(cleaned))
    return vectors
