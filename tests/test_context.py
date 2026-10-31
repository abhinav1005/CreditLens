from assistant.context import TRIM_NOTE, estimate_tokens, trim_history
from assistant.loop import run_turn
from assistant.providers.fake import FakeProvider, FakeTurn


def long_history(n_turns, size=400):
    msgs = []
    for i in range(n_turns):
        msgs += [
            {"role": "user", "content": f"question {i} " + "x" * size},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"t{i}", "name": "explain_factor", "input": {}}],
            },
            {
                "role": "tool",
                "results": [{"tool_call_id": f"t{i}", "content": "y" * size, "is_error": False}],
            },
            {"role": "assistant", "content": f"answer {i}"},
        ]
    return msgs + [{"role": "user", "content": "latest question"}]


def test_under_budget_untouched():
    msgs = long_history(2)
    assert trim_history(msgs, 10_000) == (msgs, 0)


def test_trims_whole_turns_keeps_tool_pairs_and_latest():
    msgs = long_history(20)
    kept, dropped = trim_history(msgs, 2000)
    assert estimate_tokens(kept) <= 2000 + 100 and dropped % 4 == 0 and dropped > 0
    assert kept[-1]["content"] == "latest question" and kept[0]["role"] == "user"
    assert TRIM_NOTE.format(n=dropped) in kept[0]["content"]
    call_ids = {c["id"] for m in kept if m["role"] == "assistant" for c in m.get("tool_calls", [])}
    result_ids = {r["tool_call_id"] for m in kept if m["role"] == "tool" for r in m["results"]}
    assert call_ids == result_ids  # no orphaned tool calls or results


def test_run_turn_sends_trimmed_but_transcript_keeps_all():
    from assistant.config import load_config

    config = load_config().model_copy(deep=True)
    config.assistant.context_budget_tokens = 2000
    fake = FakeProvider([FakeTurn(text="Done.")])
    history = long_history(20)
    r = run_turn(history, "p_001", provider=fake, config=config)
    assert len(fake.requests[0].messages) < len(history)
    assert r.messages[: len(history)] == history and r.extra["trimmed_messages"] > 0
