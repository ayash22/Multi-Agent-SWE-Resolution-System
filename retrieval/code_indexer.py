"""
Indexes AST-chunked code into two parallel indices:

  - FAISS: dense semantic index over OpenAI text-embedding-3-small vectors
    (or a local sentence-transformers model if no OPENAI_API_KEY is set --
    see EMBEDDING_BACKEND below), for retrieving conceptually related code
    even when it doesn't share keywords with the issue text.

  - BM25 (rank_bm25): sparse keyword index, for retrieving code that shares
    exact identifiers with the issue text (e.g. a function name or error
    message quoted verbatim in the GitHub issue) -- something dense
    embeddings alone are often weaker at.

Both indices are built per-repo and persisted to disk under
`.index_cache/<repo_slug>/`, keyed by the repo's git commit, so re-running
the pipeline against the same commit reuses the cached index instead of
re-embedding the whole codebase.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle

from retrieval.ast_chunker import CodeChunk, chunk_repo

EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "auto")  # "openai" | "local" | "auto"
EMBED_DIM_OPENAI = 1536


def _repo_slug(repo_root: str, commit: str) -> str:
    h = hashlib.sha1(f"{repo_root}:{commit}".encode()).hexdigest()[:12]
    return f"{os.path.basename(repo_root.rstrip('/'))}_{h}"


def _chunk_text(chunk: CodeChunk) -> str:
    """The text actually embedded/indexed for a chunk: qualified name +
    docstring + code, so both semantic and keyword search see identifiers
    and natural-language description together."""
    parts = [f"{chunk.file_path}::{chunk.qualified_name}"]
    if chunk.docstring:
        parts.append(chunk.docstring)
    parts.append(chunk.code)
    return "\n".join(parts)


class Embedder:
    """Thin wrapper so the indexer works with either OpenAI embeddings or a
    local sentence-transformers model, chosen automatically based on
    OPENAI_API_KEY availability unless EMBEDDING_BACKEND overrides it."""

    def __init__(self, backend: str = "auto"):
        if backend == "auto":
            backend = "openai" if os.environ.get("OPENAI_API_KEY") else "local"
        self.backend = backend

        if backend == "openai":
            from openai import OpenAI
            self.client = OpenAI()
            self.model = "text-embedding-3-small"
            self.dim = EMBED_DIM_OPENAI
        else:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self.dim = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.backend == "openai":
            resp = self.client.embeddings.create(model=self.model, input=texts)
            return [d.embedding for d in resp.data]
        return self.model.encode(texts, convert_to_numpy=True).tolist()


class CodeIndex:
    def __init__(self, repo_root: str, chunks: list[CodeChunk], embedder: Embedder,
                 faiss_index, bm25_index, tokenized_corpus: list[list[str]]):
        self.repo_root = repo_root
        self.chunks = chunks
        self.embedder = embedder
        self.faiss_index = faiss_index
        self.bm25_index = bm25_index
        self.tokenized_corpus = tokenized_corpus

    def save(self, cache_dir: str) -> None:
        os.makedirs(cache_dir, exist_ok=True)
        import faiss
        faiss.write_index(self.faiss_index, os.path.join(cache_dir, "index.faiss"))
        with open(os.path.join(cache_dir, "chunks.json"), "w") as f:
            json.dump([c.to_dict() for c in self.chunks], f)
        with open(os.path.join(cache_dir, "bm25.pkl"), "wb") as f:
            pickle.dump({"bm25": self.bm25_index, "corpus": self.tokenized_corpus}, f)
        with open(os.path.join(cache_dir, "meta.json"), "w") as f:
            json.dump({"backend": self.embedder.backend, "dim": self.embedder.dim}, f)

    @classmethod
    def load(cls, cache_dir: str, repo_root: str) -> "CodeIndex":
        import faiss
        faiss_index = faiss.read_index(os.path.join(cache_dir, "index.faiss"))
        with open(os.path.join(cache_dir, "chunks.json")) as f:
            chunks = [CodeChunk(**d) for d in json.load(f)]
        with open(os.path.join(cache_dir, "bm25.pkl"), "rb") as f:
            bm25_data = pickle.load(f)
        with open(os.path.join(cache_dir, "meta.json")) as f:
            meta = json.load(f)
        embedder = Embedder(backend=meta["backend"])
        return cls(repo_root, chunks, embedder, faiss_index,
                    bm25_data["bm25"], bm25_data["corpus"])


def build_index(repo_root: str, cache_dir: str | None = None,
                 extensions: tuple[str, ...] = (".py",)) -> CodeIndex:
    """Chunks the repo with the AST-aware chunker and builds FAISS + BM25
    indices over the chunks. If cache_dir is given and already populated,
    loads from cache instead of re-indexing."""
    if cache_dir and os.path.isfile(os.path.join(cache_dir, "index.faiss")):
        return CodeIndex.load(cache_dir, repo_root)

    import faiss
    import numpy as np
    from rank_bm25 import BM25Okapi

    chunks = chunk_repo(repo_root, extensions=extensions)
    if not chunks:
        raise ValueError(f"No chunks produced for repo: {repo_root}")

    texts = [_chunk_text(c) for c in chunks]

    embedder = Embedder(EMBEDDING_BACKEND)
    vectors = embedder.embed(texts)
    arr = np.array(vectors, dtype="float32")
    faiss.normalize_L2(arr)
    index = faiss.IndexFlatIP(arr.shape[1])
    index.add(arr)

    tokenized_corpus = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized_corpus)

    code_index = CodeIndex(repo_root, chunks, embedder, index, bm25, tokenized_corpus)
    if cache_dir:
        code_index.save(cache_dir)
    return code_index


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_root")
    parser.add_argument("--cache-dir", default=None)
    args = parser.parse_args()
    idx = build_index(args.repo_root, cache_dir=args.cache_dir)
    print(f"Indexed {len(idx.chunks)} chunks from {args.repo_root} "
          f"using {idx.embedder.backend} embeddings (dim={idx.embedder.dim})")
