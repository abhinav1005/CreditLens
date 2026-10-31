from evals.guardrail_eval import evaluate_pii, load_set


def test_pii_set_is_well_formed():
    items = load_set("pii")
    assert {i["split"] for i in items} == {"dev", "test"}
    assert all(p["value"] in i["text"] for i in items for p in i["pii"])
    assert sum(not i["pii"] for i in items) >= 30  # hard negatives


def test_evaluate_pii_counts_misses_and_false_positives():
    items = [
        {
            "id": "a",
            "text": "My SSN is 912-34-5678.",
            "pii": [{"type": "SSN", "value": "912-34-5678"}],
        },
        {"id": "b", "text": "i'm maria lopez", "pii": [{"type": "NAME", "value": "maria lopez"}]},
        {"id": "c", "text": "What was my score in March 2026?", "pii": []},
    ]
    r = evaluate_pii(items)
    assert r["recall"] == 0.5 and r["recall_by_type"] == {"NAME": 0.0, "SSN": 1.0}
    assert r["negative_false_positive_rate"] == 0.0
