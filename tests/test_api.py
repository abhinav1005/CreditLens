import json

from fastapi.testclient import TestClient

from assistant.api import create_app
from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn
from storage.sqlite import SQLiteStorage


def parse_sse(body: str) -> list[tuple[str, dict]]:
    frames = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


def make_client(turns):
    store = SQLiteStorage(":memory:")
    app = create_app(provider_factory=lambda model: FakeProvider(turns), storage=store)
    return TestClient(app), store


def test_chat_streams_ordered_events_and_saves_transcript():
    client, store = make_client(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "story_001"})]),
            FakeTurn(
                text="Your overall utilization is 40.8%. Paying down card ****9054 lowers it."
            ),
        ]
    )
    resp = client.post(
        "/chat",
        json={"profile_id": "story_001", "messages": [{"role": "user", "content": "utilization?"}]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse(resp.text)
    assert [f[0] for f in frames] == [
        "tool_call",
        "tool_result",
        "text",
        "text",
        "done",
        "transcript",
    ]
    assert frames[0][1]["name"] == "get_utilization"
    transcript = store.get(frames[-1][1]["transcript_id"])
    assert transcript.source == "chat" and transcript.final_text.startswith(
        "Your overall utilization is 40.8%."
    )


def test_unknown_profile_404():
    client, _ = make_client([])
    resp = client.post(
        "/chat", json={"profile_id": "p_999", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 404


def test_last_message_must_be_user():
    client, _ = make_client([])
    resp = client.post(
        "/chat", json={"profile_id": "p_001", "messages": [{"role": "assistant", "content": "hi"}]}
    )
    assert resp.status_code == 422


def test_provider_failure_becomes_error_event():
    client, _ = make_client([])  # FakeProvider with no turns raises
    resp = client.post(
        "/chat", json={"profile_id": "p_001", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert parse_sse(resp.text)[-1][0] == "error"


def test_health():
    client, _ = make_client([])
    assert client.get("/health").json() == {"status": "ok"}
