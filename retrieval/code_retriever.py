"""
Hybrid code retrieval: combines dense (FAISS) and sparse (BM25) search over
AST chunks using Reciprocal Rank Fusion (RRF), which reliably outperforms
either signal alone and needs no score-scale calibration between the two
very differently-distributed similarity scores.

Also guarantees inclusion of:
  - any file path explicitly mentioned in the issue text (regex-matched
    against `.py` paths appearing in the issue), since those are
    near-certain to be relevant regardless of embedding similarity
  - the failing test file itself, so the coder agent can see exactly what
    the patch needs to satisfy
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from retrieval.ast_chunker import CodeChunk
from retrieval.code_indexer import CodeIndex

FILE_MENTION_RE = re.compile(r"[\w./-]+\.py\b")


@dataclass
class RetrievedChunk:
    chunk: CodeChunk
    score: float
    reason: str  # "hybrid" | "explicit_file_mention" | "test_file"

    def to_dict(self) -> dict:
        d = self.chunk.to_dict()
        d["retrieval_score"] = self.score
        d["retrieval_reason"] = self.reason
        return d


def _dense_search(index: CodeIndex, query: str, k: int) -> list[tuple[int, float]]:
    vec = np.array(index.embedder.embed([query]), dtype="float32")
    import faiss
    faiss.normalize_L2(vec)
    scores, ids = index.faiss_index.search(vec, min(k, len(index.chunks)))
    return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]


def _sparse_search(index: CodeIndex, query: str, k: int) -> list[tuple[int, float]]:
    tokens = query.lower().split()
    scores = index.bm25_index.get_scores(tokens)
    top_ids = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_ids]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[int, float]]], k_const: int = 60
) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, (idx, _score) in enumerate(ranked):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k_const + rank + 1)
    return fused


def hybrid_retrieve(
    index: CodeIndex, query: str, top_k: int = 10, candidate_pool: int = 50
) -> list[RetrievedChunk]:
    dense_hits = _dense_search(index, query, candidate_pool)
    sparse_hits = _sparse_search(index, query, candidate_pool)
    fused_scores = _reciprocal_rank_fusion([dense_hits, sparse_hits])

    ranked = sorted(fused_scores.items(), key=lambda x: -x[1])[:top_k]
    return [
        RetrievedChunk(chunk=index.chunks[idx], score=score, reason="hybrid")
        for idx, score in ranked
    ]


def find_explicit_file_mentions(issue_text: str, index: CodeIndex) -> list[RetrievedChunk]:
    mentioned = set(FILE_MENTION_RE.findall(issue_text))
    if not mentioned:
        return []
    hits = []
    seen_files = set()
    for chunk in index.chunks:
        if chunk.file_path in seen_files:
            continue
        for m in mentioned:
            if chunk.file_path.endswith(m) or m.endswith(chunk.file_path):
                hits.append(RetrievedChunk(chunk=chunk, score=1.0, reason="explicit_file_mention"))
                seen_files.add(chunk.file_path)
                break
    return hits


def find_test_file_chunks(test_file_path: str, index: CodeIndex) -> list[RetrievedChunk]:
    if not test_file_path:
        return []
    return [
        RetrievedChunk(chunk=c, score=1.0, reason="test_file")
        for c in index.chunks
        if c.file_path == test_file_path or c.file_path.endswith(test_file_path)
    ]


def retrieve_context(
    index: CodeIndex,
    issue_text: str,
    fix_strategy: str = "",
    failing_test_file: str = "",
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """Full retrieval pipeline used by the retrieval_agent node: hybrid
    search over (issue + fix strategy), unioned with explicit file mentions
    and the failing test file, de-duplicated by (file_path, qualified_name),
    then trimmed back to top_k + guaranteed inclusions."""
    query = f"{issue_text}\n\n{fix_strategy}".strip()
    hybrid_hits = hybrid_retrieve(index, query, top_k=top_k)
    guaranteed = find_explicit_file_mentions(issue_text, index) + \
        find_test_file_chunks(failing_test_file, index)

    seen = set()
    combined: list[RetrievedChunk] = []
    for hit in guaranteed + hybrid_hits:
        key = (hit.chunk.file_path, hit.chunk.qualified_name, hit.chunk.start_line)
        if key not in seen:
            seen.add(key)
            combined.append(hit)

    return combined
