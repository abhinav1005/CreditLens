from fastapi.testclient import TestClient

from assistant.ab import assign_variant
from assistant.api import create_app
from assistant.providers.fake import FakeProvider, FakeTurn
from storage.sqlite import SQLiteStorage


def test_assignment_is_sticky_and_near_percent():
    ids = [f"conv-{i}" for i in range(2000)]
    assert all(assign_variant(i, 10) == assign_variant(i, 10) for i in ids[:50])
    share = sum(assign_variant(i, 10) == "candidate" for i in ids) / len(ids)
    assert 0.07 < share < 0.13
    assert assign_variant("x", 0) == "control" and assign_variant("x", 100) == "candidate"


def test_api_routes_candidate_and_tags_transcript(monkeypatch):
    import assistant.api as api

    config = api.load_config().model_copy(deep=True)
    config.ab_test.enabled, config.ab_test.percent = True, 100
    monkeypatch.setattr(api, "load_config", lambda: config)
    seen, store = [], SQLiteStorage(":memory:")

    def factory(model):
        seen.append(model)
        return FakeProvider([FakeTurn(text="Hi.")])

    client = TestClient(create_app(provider_factory=factory, storage=store))
    body = client.post(
        "/chat",
        json={
            "profile_id": "p_001",
            "conversation_id": "c1",
            "messages": [{"role": "user", "content": "hi"}],
        },
    ).text
    tid = (
        [line for line in body.splitlines() if "transcript_id" in line][0]
        .split('"transcript_id": "')[1]
        .split('"')[0]
    )
    t = store.get(tid)
    assert (
        seen == ["claude-haiku-5-5"] and t.variant == "candidate" and t.model == "claude-haiku-5-5"
    )
