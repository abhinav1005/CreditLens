import json

from assistant.loop import BLOCK_MESSAGES, run_turn
from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn
from guardrails.base import GuardrailResult, passed
from guardrails.pipeline import GuardrailSet, run_pipeline


class Redact:
    name = "redact_secret"

    def check(self, text, context):
        if "SECRET" in text:
            return GuardrailResult(
                self.name, True, "redact", text.replace("SECRET", "<X_1>"), ["secret"]
            )
        return passed(self.name, text)


class BlockWord:
    name = "block_word"

    def check(self, text, context):
        if "attack" in text:
            return GuardrailResult(self.name, False, "block", text, ["attack"], {"risk": 0.9})
        return passed(self.name, text)


def test_pipeline_redact_then_block_order():
    out = run_pipeline([Redact(), BlockWord()], "SECRET attack", {}, "input")
    assert out.blocked and out.blocked_by.name == "block_word"
    assert [d["action"] for d in out.decisions] == ["redact", "block"]
    assert "text" not in out.decisions[0]  # redacted text is never logged


def test_input_redaction_reaches_model_and_history_but_not_original():
    fake = FakeProvider([FakeTurn(text="Got it.")])
    conv = [
        {"role": "user", "content": "old SECRET"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "my SECRET is here"},
    ]
    r = run_turn(conv, "p_001", provider=fake, guardrails=GuardrailSet(input=[Redact()]))
    sent = json.dumps(fake.requests[0].messages)
    assert "SECRET" not in sent and "<X_1>" in sent
    assert "SECRET" not in json.dumps(r.messages)
    assert r.guardrail_decisions == [
        {
            "stage": "input",
            "name": "redact_secret",
            "allowed": True,
            "action": "redact",
            "reasons": ["secret"],
            "scores": {},
        }
    ]


def test_blocked_input_never_calls_model():
    fake = FakeProvider([])
    BLOCK_MESSAGES["block_word"] = "I can't do that."
    r = run_turn(
        [{"role": "user", "content": "attack now"}],
        "p_001",
        provider=fake,
        guardrails=GuardrailSet(input=[BlockWord()]),
    )
    assert r.stop == "blocked" and r.final_text == "I can't do that." and fake.requests == []
    del BLOCK_MESSAGES["block_word"]


def test_tool_result_guard_can_withhold():
    class BlockTool:
        name = "tool_guard"

        def check(self, text, context):
            return GuardrailResult(self.name, False, "block", text, ["injection"])

    fake = FakeProvider(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "p_001"})]),
            FakeTurn(text="Done."),
        ]
    )
    r = run_turn(
        [{"role": "user", "content": "util?"}],
        "p_001",
        provider=fake,
        guardrails=GuardrailSet(tool_results=[BlockTool()]),
    )
    sent = fake.requests[1].messages[-1]["results"][0]["content"]
    assert "WITHHELD" in sent
    assert r.tool_calls[0]["output"]["profile_id"] == "p_001"  # original kept for scoring
    assert (
        r.guardrail_decisions[0]["stage"] == "tool_result"
        and r.guardrail_decisions[0]["tool"] == "get_utilization"
    )


def test_output_guard_redacts_sentence():
    fake = FakeProvider([FakeTurn(text="Hello. Your SECRET is safe.")])
    r = run_turn(
        [{"role": "user", "content": "hi"}],
        "p_001",
        provider=fake,
        guardrails=GuardrailSet(output=[Redact()]),
    )
    assert r.final_text == "Hello. Your <X_1> is safe."
