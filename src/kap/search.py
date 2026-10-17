"""Elasticsearch hybrid search over runbooks and case notes.

Index `kap_docs`: one document per runbook (title, symptoms, steps) and per case note
(description, resolution_text). BM25 on the text fields plus a dense_vector from NeMo Retriever
embeddings (nvidia/nemotron-3-embed-1b, 2048 dims, through NIM); the two rankings are combined by
reciprocal rank fusion (k = 60) in Python so the fusion is explicit and testable.

    uv run python -m kap.search index            # build the index (runbooks + sample of cases)
    uv run python -m kap.search query "RAID degraded after a config change"
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch

from kap import llm
from kap.config import es_url, sois_dir

INDEX = "kap_docs"
EMBED_MODEL = "nvidia/nemotron-3-embed-1b"
DIMS = 2048
RRF_K = 60

MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "runbook_id": {"type": "keyword"},
            "case_id": {"type": "keyword"},
            "product_family": {"type": "keyword"},
            "category": {"type": "keyword"},
            "title": {"type": "text"},
            "body": {"type": "text"},
            "embedding": {"type": "dense_vector", "dims": DIMS, "index": True, "similarity": "cosine"},
        }
    },
}


def client() -> Elasticsearch:
    return Elasticsearch(es_url(), request_timeout=60)


def runbook_docs(sois: Path) -> list[dict[str, Any]]:
    docs = []
    with open(sois / "data" / "enterprise" / "runbook.csv", newline="") as f:
        for r in csv.DictReader(f):
            docs.append({
                "doc_id": f"rb:{r['runbook_id']}", "kind": "runbook", "runbook_id": r["runbook_id"],
                "product_family": r["product_family"], "category": r["category"], "title": r["title"],
                "body": f"{r['title']}. Symptoms: {r['symptoms']}. Steps: {r['steps']}",
            })
    return docs


def case_docs(sois: Path, limit: int) -> list[dict[str, Any]]:
    """Case notes: the first `limit` cases that have a resolution, as the search corpus."""
    docs = []
    with open(sois / "data" / "enterprise" / "case.csv", newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("description"):
                continue
            body = r["description"]
            if r.get("resolution_text"):
                body += f" Resolution: {r['resolution_text']}"
            docs.append({
                "doc_id": f"case:{r['case_id']}", "kind": "case", "case_id": r["case_id"],
                "category": r["category"], "title": f"{r['case_id']} {r['category']} sev{r['severity']}", "body": body,
            })
            if len(docs) >= limit:
                break
    return docs


def build_index(case_limit: int = 500) -> dict[str, int]:
    es = client()
    sois = sois_dir()
    docs = runbook_docs(sois) + case_docs(sois, case_limit)
    vectors = llm.embed([d["body"] for d in docs], input_type="passage", model_id=EMBED_MODEL)
    if es.indices.exists(index=INDEX):
        es.indices.delete(index=INDEX)
    es.indices.create(index=INDEX, **MAPPING)
    ops: list[dict[str, Any]] = []
    for d, v in zip(docs, vectors):
        ops.append({"index": {"_index": INDEX, "_id": d["doc_id"]}})
        ops.append({**d, "embedding": v})
    es.bulk(operations=ops, refresh=True)
    return {"runbooks": sum(d["kind"] == "runbook" for d in docs), "cases": sum(d["kind"] == "case" for d in docs)}


def bm25(es: Elasticsearch, query: str, kind: str | None, size: int) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"bool": {"must": [{"multi_match": {"query": query, "fields": ["title^2", "body"]}}]}}
    if kind:
        q["bool"]["filter"] = [{"term": {"kind": kind}}]
    r = es.search(index=INDEX, query=q, size=size, _source_excludes=["embedding"])
    return [{"doc_id": h["_id"], "score": h["_score"], **h["_source"]} for h in r["hits"]["hits"]]


def dense(es: Elasticsearch, query: str, kind: str | None, size: int) -> list[dict[str, Any]]:
    vec = llm.embed([query], input_type="query", model_id=EMBED_MODEL)[0]
    knn: dict[str, Any] = {"field": "embedding", "query_vector": vec, "k": size, "num_candidates": max(50, size * 5)}
    if kind:
        knn["filter"] = {"term": {"kind": kind}}
    r = es.search(index=INDEX, knn=knn, size=size, _source_excludes=["embedding"])
    return [{"doc_id": h["_id"], "score": h["_score"], **h["_source"]} for h in r["hits"]["hits"]]


def rrf(rankings: list[list[dict[str, Any]]], k: int = RRF_K) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    docs: dict[str, dict[str, Any]] = {}
    for ranking in rankings:
        for rank, d in enumerate(ranking, start=1):
            scores[d["doc_id"]] = scores.get(d["doc_id"], 0.0) + 1.0 / (k + rank)
            docs.setdefault(d["doc_id"], d)
    out = []
    for doc_id, s in sorted(scores.items(), key=lambda kv: -kv[1]):
        d = dict(docs[doc_id])
        d["score"] = round(s, 6)
        out.append(d)
    return out


def search(query: str, kind: str | None = None, size: int = 5, mode: str = "hybrid") -> list[dict[str, Any]]:
    es = client()
    if mode == "bm25":
        return bm25(es, query, kind, size)
    if mode == "dense":
        return dense(es, query, kind, size)
    return rrf([bm25(es, query, kind, size * 4), dense(es, query, kind, size * 4)])[:size]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_i = sub.add_parser("index")
    p_i.add_argument("--cases", type=int, default=500)
    p_q = sub.add_parser("query")
    p_q.add_argument("text")
    p_q.add_argument("--kind", choices=["runbook", "case"], default=None)
    p_q.add_argument("--mode", choices=["hybrid", "bm25", "dense"], default="hybrid")
    p_q.add_argument("--size", type=int, default=5)
    args = ap.parse_args(argv)
    if args.cmd == "index":
        print(json.dumps(build_index(args.cases)))
    else:
        for d in search(args.text, args.kind, args.size, args.mode):
            print(f"{d['score']:.4f}  {d['doc_id']:16s} {d.get('title', '')[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
