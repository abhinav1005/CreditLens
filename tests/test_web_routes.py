import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from evals.labeling import load_pool
from evals.web_routes import make_router

ALL_PASS = {"helpfulness": "pass", "clarity": "pass", "compliance": "fail", "groundedness": "pass"}


def make_client(tmp_path, n_items=3):
    pool = tmp_path / "pool.jsonl"
    pool.write_text("".join(json.dumps(i) + "\n" for i in load_pool()[:n_items]))
    labels = tmp_path / "labels.jsonl"
    app = FastAPI()
    app.include_router(make_router(pool_path=pool, labels_path=labels))
    return TestClient(app), labels


def test_next_item_is_blind(tmp_path):
    client, _ = make_client(tmp_path)
    body = client.get("/labeling/next", params={"labeler": "a"}).json()
    item = body["item"]
    assert body["progress"] == {"done": 0, "target": 100, "pool_size": 3}
    # Nothing that reveals the source: model, prompt version, run id, cache key, judge.
    text = json.dumps(item)
    for hidden in ("claude-", "v1-degraded", "run_id", "cache_key", "judge"):
        assert hidden not in text
    assert item["category"] and (item["reply"] is not None or item["cards"] is not None)


def test_label_saved_then_next_item_advances(tmp_path):
    client, labels = make_client(tmp_path)
    first = client.get("/labeling/next", params={"labeler": "a"}).json()["item"]["item_id"]
    resp = client.post(
        "/labeling/labels",
        json={"item_id": first, "labeler": "a", "verdicts": ALL_PASS, "note": "x"},
    )
    assert resp.status_code == 200
    saved = json.loads(labels.read_text())
    assert saved["item_id"] == first and saved["verdicts"] == ALL_PASS and saved["labeler"] == "a"
    after = client.get("/labeling/next", params={"labeler": "a"}).json()
    assert after["item"]["item_id"] != first and after["progress"]["done"] == 1
    # Another labeler still starts from the first item.
    assert client.get("/labeling/next", params={"labeler": "b"}).json()["item"]["item_id"] == first


def test_skip_and_exhausted(tmp_path):
    client, _ = make_client(tmp_path, n_items=2)
    ids = [i["item_id"] for i in load_pool()[:2]]
    body = client.get("/labeling/next", params={"labeler": "a", "skip": ids[0]}).json()
    assert body["item"]["item_id"] == ids[1]
    body = client.get("/labeling/next", params={"labeler": "a", "skip": ",".join(ids)}).json()
    assert body["item"] is None


def test_rejects_bad_labels(tmp_path):
    client, _ = make_client(tmp_path)
    item_id = load_pool()[0]["item_id"]
    post = lambda **kw: client.post(  # noqa: E731
        "/labeling/labels", json={"item_id": item_id, "labeler": "a", "verdicts": ALL_PASS, **kw}
    )
    assert post(verdicts={"helpfulness": "pass"}).status_code == 422
    assert post(item_id="lp_nope").status_code == 404
    assert post().status_code == 200
    assert post().status_code == 409  # no duplicate label from a double submit
