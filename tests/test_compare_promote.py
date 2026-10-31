from assistant.loop import run_turn
from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn
from evals.cases import Case, Category
from evals.compare import compare_results, render_comparison
from evals.promote import build_case, conversation_before_reply, next_id
from storage.transcripts import transcript_from_turn


def row(cid, cat, passed, failing=()):
    return {
        "case_id": cid,
        "category": cat,
        "passed": passed,
        "status": "ok",
        "checks": [{"name": n, "passed": False} for n in failing],
    }


def test_compare_newly_failing_and_passing():
    a = {
        "t1": row("t1", "tool_use", True),
        "t2": row("t2", "tool_use", False),
        "c1": row("c1", "compliance", True),
    }
    b = {
        "t1": row("t1", "tool_use", False, ["disclaimer"]),
        "t2": row("t2", "tool_use", True),
        "c1": row("c1", "compliance", True),
        "x9": row("x9", "factual", True),
    }
    diff = compare_results(a, b)
    assert diff["newly_failing"] == [
        {"case_id": "t1", "category": "tool_use", "checks": ["disclaimer"]}
    ]
    assert diff["newly_passing"] == [{"case_id": "t2", "category": "tool_use"}]
    assert diff["per_category"]["tool_use"] == {"n": 2, "a_passed": 1, "b_passed": 1, "lost": 1}
    assert diff["only_in_b"] == ["x9"]
    text = render_comparison(diff, "base", "pr")
    assert "`t1` [tool_use]: `disclaimer`" in text and "| tool_use | 1/2 | 1/2 | 1 |" in text


def make_transcript():
    fake = FakeProvider(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "story_001"})]),
            FakeTurn(text="Your score will rise 40 points."),
        ]
    )
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "What if I pay my card off?"},
    ]
    return transcript_from_turn(run_turn(history, "story_001", provider=fake), "c1", source="chat")


def test_conversation_before_reply_drops_this_turn():
    t = make_transcript()
    conv = conversation_before_reply(t.messages)
    assert conv[-1] == {"role": "user", "content": "What if I pay my card off?"}
    assert len(conv) == 3


def test_build_case_valid_and_numbered():
    t = make_transcript()
    case = build_case(
        t, Category.COMPLIANCE, "Promised points", ["40 points"], [], ["comp_001", "comp_020"]
    )
    assert case["id"] == "comp_021" and case["source"] == "promoted_from_transcript"
    Case.model_validate(case)


def test_next_id_ignores_other_prefixes():
    assert next_id(Category.PII, ["pii_003", "comp_009", "pii_015"]) == "pii_016"
