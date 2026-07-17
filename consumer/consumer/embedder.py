from __future__ import annotations

from sentence_transformers import SentenceTransformer


class NomicEmbedder:
    def __init__(self, model_name: str, batch_size: int = 32):
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        self.batch_size = batch_size

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [row.astype(float).tolist() for row in vectors]

    def embed_prompts(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"search_query: {t}" for t in texts])

    def embed_completions(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"search_document: {t}" for t in texts])