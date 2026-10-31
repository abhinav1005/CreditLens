from assistant.loop import run_turn
from assistant.prompts import load_bundle
from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn
from storage.sqlite import SQLiteStorage
from storage.transcripts import transcript_from_turn


def _turn():
    fake = FakeProvider(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "story_001"})]),
            FakeTurn(text="Your utilization is 40.8%."),
        ]
    )
    return run_turn(
        [{"role": "user", "content": "utilization?"}],
        "story_001",
        provider=fake,
        bundle=load_bundle("v1"),
    )


def test_round_trip(tmp_path):
    store = SQLiteStorage(tmp_path / "t.sqlite")
    t = transcript_from_turn(_turn(), conversation_id="c1", source="chat")
    store.put(t)
    back = store.get(t.transcript_id)
    assert back == t
    assert back.prompt_version == "system:v1+tools:v1"
    assert back.model == "claude-sonnet-5-5"
    assert back.tool_calls[0]["name"] == "get_utilization"


def test_get_missing_returns_none():
    assert SQLiteStorage(":memory:").get("nope") is None


def test_list_by_date_newest_first():
    store = SQLiteStorage(":memory:")
    base = transcript_from_turn(_turn(), conversation_id="c1", source="eval")
    for day in ["2026-10-01", "2026-10-02", "2026-10-03"]:
        store.put(
            base.model_copy(update={"transcript_id": day, "created_at": f"{day}T12:00:00+00:00"})
        )
    assert [t.transcript_id for t in store.list()] == ["2026-10-03", "2026-10-02", "2026-10-01"]
    assert [t.transcript_id for t in store.list(start="2026-10-02", end="2026-10-03")] == [
        "2026-10-02"
    ]
    assert len(store.list(limit=1)) == 1
