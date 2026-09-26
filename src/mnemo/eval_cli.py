import argparse
import math
import random
import time

from mnemo.core.budget import estimate_tokens
from mnemo.core.runtime import get_runtime
from mnemo.embeddings import embed_text


SAMPLE_LIMIT = 50
SAMPLE_SEED = 0
STALE_STATUSES = frozenset({"superseded", "expired", "wrong", "deleted"})


def _sample_active(active):
    if len(active) <= SAMPLE_LIMIT:
        return list(active)
    return random.Random(SAMPLE_SEED).sample(sorted(active, key=lambda memory: memory.id), SAMPLE_LIMIT)


def _cosine(left, right):
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _similar_pairs(records, threshold):
    pairs = 0
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            if _cosine(left["vector"], right["vector"]) >= threshold:
                pairs += 1
    return pairs


def _representative_query(active):
    return next(
        (memory for memory in active if memory.type.lower() in {"overview", "core"}),
        active[0],
    ).content


def _print_unavailable_metric(label, missing):
    print(f"  {label}: unavailable (missing vectors for {missing} sampled active memories)")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mnemo eval")
    parser.add_argument("--project", required=True)
    args = parser.parse_args(argv)

    service = get_runtime()
    all_memories = service.repository.all(args.project)
    active = [memory for memory in all_memories if memory.status == "active"]
    if not all_memories:
        print(f"Evaluation report for project '{args.project}'")
        print("  no memories to evaluate")
        return

    sampled = _sample_active(active)
    print(
        f"Evaluation report for project '{args.project}' "
        f"(sampled {len(sampled)} of {len(active)} active memories)"
    )
    if not active:
        print("  no active memories to evaluate")
        return

    self_found = 0
    for memory in sampled:
        results = service.search(
            embed_text(memory.content),
            args.project,
            query_text=memory.content,
            k=5,
        )
        if memory.id in {result["id"] for result in results}:
            self_found += 1
    print(
        f"  self-retrieval recall (proxy): {self_found / len(sampled):.3f} "
        f"({self_found}/{len(sampled)} found themselves in top-5; sanity check, not a real IR benchmark)"
    )

    stale_count = sum(memory.status in STALE_STATUSES for memory in all_memories)
    print(
        f"  stale-memory rate: {stale_count / len(all_memories):.3f} "
        f"({stale_count}/{len(all_memories)} total)"
    )

    vectors_by_id = {
        record["id"]: record
        for record in service.get_all_with_vectors(args.project)
        if record.get("vector") is not None
    }
    sampled_with_vectors = [vectors_by_id[memory.id] for memory in sampled if memory.id in vectors_by_id]
    missing_vectors = len(sampled) - len(sampled_with_vectors)
    if missing_vectors:
        _print_unavailable_metric(
            "near-duplicate proxy (sim>=0.90, NOT true contradiction detection)",
            missing_vectors,
        )
        _print_unavailable_metric("duplicate rate (sim>=0.98)", missing_vectors)
    else:
        near_duplicates = _similar_pairs(sampled_with_vectors, 0.90)
        duplicates = _similar_pairs(sampled_with_vectors, 0.98)
        print(
            f"  near-duplicate proxy (sim>=0.90, NOT true contradiction detection): "
            f"{near_duplicates / len(active):.3f} "
            f"({near_duplicates} pairs / {len(active)} active; sampled pair comparison)"
        )
        print(
            f"  duplicate rate (sim>=0.98): {duplicates / len(active):.3f} "
            f"({duplicates} pairs / {len(active)} active; sampled pair comparison)"
        )

    total_tokens = sum(estimate_tokens(memory.content) for memory in active)
    print(f"  avg tokens per memory: {total_tokens / len(active):.1f}")

    query = _representative_query(active)
    query_vector = embed_text(query)
    result_set = service.search(query_vector, args.project, query_text=query, k=5)
    result_tokens = sum(estimate_tokens(result["content"]) for result in result_set)
    print(f"  avg tokens per k=5 search result set: {result_tokens:.1f}")

    latencies = []
    for _ in range(10):
        started = time.perf_counter()
        service.search(query_vector, args.project, query_text=query, k=5)
        latencies.append((time.perf_counter() - started) * 1000)
    print(f"  search latency: mean {sum(latencies) / len(latencies):.1f}ms, max {max(latencies):.1f}ms (10 runs)")

    sourced = sum(memory.source_id is not None for memory in active)
    print(f"  provenance coverage: {sourced / len(active):.3f} ({sourced}/{len(active)} active with a source)")
