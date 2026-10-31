import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from evals.web_routes import make_router


def write_run(root, name, passed: dict[str, bool]):
    d = root / name
    d.mkdir(parents=True)
    rows = [
        {
            "case_id": cid,
            "category": "factual",
            "passed": ok,
            "status": "ok",
            "checks": [{"name": "disclaimer", "scorer": "disclaimer", "passed": ok, "detail": "x"}],
            "final_text": "answer",
            "tool_calls": [],
            "judge": {"helpfulness": {"verdict": "pass", "rationale": "fine"}},
        }
        for cid, ok in passed.items()
    ]
    (d / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = {
        "suite": "golden",
        "model": "m",
        "prompt_version": "v1",
        "created_at": f"2026-10-31T00:00:0{len(name) % 10}+00:00",
        "n_cases": len(rows),
        "n_passed": sum(passed.values()),
        "overall_pass_rate": sum(passed.values()) / len(rows),
        "categories": {},
        "cost": {"measured_total_usd": 0.1},
    }
    (d / "summary.json").write_text(json.dumps(summary))


def client_for(tmp_path):
    write_run(tmp_path, "run-a", {"fact_001": True, "fact_002": False})
    write_run(tmp_path, "run-bb", {"fact_001": False, "fact_002": True})
    app = FastAPI()
    app.include_router(make_router(search_dirs=[tmp_path]))
    return TestClient(app)


def test_lists_runs_and_shows_cases_with_failed_checks(tmp_path):
    client = client_for(tmp_path)
    assert {r["run_id"] for r in client.get("/evals/runs").json()} == {"run-a", "run-bb"}
    body = client.get("/evals/runs/run-a").json()
    rows = {r["case_id"]: r for r in body["cases"]}
    assert rows["fact_001"]["failed_checks"] == []
    assert rows["fact_002"]["failed_checks"][0]["name"] == "disclaimer"
    # Joined with the golden case: the question and expectations come along.
    assert rows["fact_001"]["question"] and rows["fact_001"]["expectations"] is not None
    assert rows["fact_001"]["judge"]["helpfulness"]["verdict"] == "pass"


def test_compare_runs(tmp_path):
    client = client_for(tmp_path)
    diff = client.get("/evals/compare", params={"a": "run-a", "b": "run-bb"}).json()
    assert [c["case_id"] for c in diff["newly_failing"]] == ["fact_001"]
    assert [c["case_id"] for c in diff["newly_passing"]] == ["fact_002"]


def test_unknown_or_path_like_run_ids_are_rejected(tmp_path):
    client = client_for(tmp_path)
    assert client.get("/evals/runs/nope").status_code == 404
    assert client.get("/evals/runs/..%2F..%2Fetc").status_code == 404
    assert (
        client.get(
            "/evals/compare", params={"a": str(tmp_path / "run-a"), "b": "run-a"}
        ).status_code
        == 404
    )


def test_real_saved_runs_load():
    app = FastAPI()
    app.include_router(make_router())
    client = TestClient(app)
    runs = client.get("/evals/runs").json()
    assert any(r["run_id"] == "matrix-claude-sonnet-5-5" for r in runs)
    body = client.get("/evals/runs/matrix-claude-sonnet-5-5").json()
    assert len(body["cases"]) == body["summary"]["n_cases"]
