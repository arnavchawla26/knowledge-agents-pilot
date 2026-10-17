from kap.search import rrf


def test_rrf_fuses_two_rankings():
    a = [{"doc_id": "x", "score": 9}, {"doc_id": "y", "score": 5}]
    b = [{"doc_id": "y", "score": 0.9}, {"doc_id": "z", "score": 0.8}]
    fused = rrf([a, b], k=60)
    assert [d["doc_id"] for d in fused] == ["y", "x", "z"]
    assert abs(fused[0]["score"] - (1 / 61 + 1 / 62)) < 1e-5
