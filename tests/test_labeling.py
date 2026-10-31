import json

from evals.cache import ResponseCache
from evals.labeling import build_pool, item_id


def make_fake_run_suite(tmp_path, cache, calls):
    def fake_run_suite(cases, *, suite, model, prompt_version, max_cost_usd, cache_dir, **kw):
        calls.append((model, prompt_version))
        rows = []
        for i in range(3):
            key = f"{model}-{prompt_version}-{i}"
            # Both prompts give the same answer for case c0, so it's deduplicated.
            text = "same answer" if i == 0 else f"{prompt_version} answer {i}"
            cache.put(key, {"kind": "chat", "final_text": text, "tool_calls": []})
            rows.append(
                {"case_id": f"c{i}", "category": "factual", "status": "ok", "cache_key": key}
            )
        out = tmp_path / f"{model}-{prompt_version}-{len(calls)}"
        out.mkdir()
        (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return {"run_id": out.name, "out_dir": str(out), "cost": {"api_spend_this_run_usd": 0.0}}

    return fake_run_suite


def test_pool_dedupes_shuffles_reproducibly_and_records_source(tmp_path):
    cache, calls = ResponseCache(tmp_path / "cache"), []
    run = make_fake_run_suite(tmp_path, cache, calls)
    items = build_pool(["m1"], ["v1", "v1-degraded"], max_cost_usd=1, run_suite=run, cache=cache)
    assert calls == [("m1", "v1"), ("m1", "v1-degraded")]
    assert len(items) == 5  # 6 responses, one duplicate
    assert all(i["item_id"] == item_id(i["cache_key"]) for i in items)
    assert {i["prompt_version"] for i in items} == {"v1", "v1-degraded"}
    again = build_pool(["m1"], ["v1", "v1-degraded"], max_cost_usd=1, run_suite=run, cache=cache)
    assert [i["item_id"] for i in again] == [i["item_id"] for i in items]  # fixed-seed shuffle
