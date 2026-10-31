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


def test_profiles_lists_synthetic_profiles():
    client, _ = make_client([])
    resp = client.get("/profiles")
    assert resp.status_code == 200
    by_id = {p["profile_id"]: p for p in resp.json()}
    assert "story_001" in by_id and by_id["story_001"]["story"]
    assert 300 <= by_id["story_001"]["score"] <= 850


def test_guardrail_flags_keep_only_actions():
    from assistant.api import guardrail_flags

    decisions = [
        {"stage": "input", "name": "pii", "allowed": True, "action": "pass", "reasons": []},
        {
            "stage": "input",
            "name": "pii",
            "allowed": True,
            "action": "redact",
            "reasons": ["US_SSN"],
            "scores": {},
        },
    ]
    assert guardrail_flags(decisions) == [
        {"stage": "input", "name": "pii", "action": "redact", "reasons": ["US_SSN"]}
    ]


def test_transcript_event_carries_model_and_guardrails():
    client, _ = make_client([FakeTurn(text="Utilization is the share of your limits in use.")])
    resp = client.post(
        "/chat",
        json={"profile_id": "story_001", "messages": [{"role": "user", "content": "what is it?"}]},
    )
    event = parse_sse(resp.text)[-1]
    assert event[0] == "transcript"
    assert event[1]["guardrails"] == [] and event[1]["prompt_version"]
