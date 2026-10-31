from assistant.loop import INCOMPLETE_MESSAGE, REFUSAL_MESSAGE, run_turn
from assistant.output_filters import FilterDecision, SentenceBuffer
from assistant.providers import ToolCall
from assistant.providers.fake import FakeProvider, FakeTurn

USER = [{"role": "user", "content": "What's my utilization?"}]


def test_tool_then_answer():
    fake = FakeProvider(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_utilization", {"profile_id": "story_001"})]),
            FakeTurn(text="Your overall utilization is 40.8%. That's above 30%."),
        ]
    )
    result = run_turn(USER, "story_001", provider=fake)
    assert result.stop == "complete"
    assert result.final_text == "Your overall utilization is 40.8%. That's above 30%."
    assert result.tool_calls[0]["output"]["overall_utilization_pct"] == 40.8
    assert [e["type"] for e in result.events] == [
        "tool_call",
        "tool_result",
        "text",
        "text",
        "done",
    ]
    assert result.iterations == 2 and result.model_requests == 2
    # The tool result was sent back to the model on the second request.
    second = fake.requests[1].messages
    assert second[-1]["role"] == "tool" and second[-1]["results"][0]["tool_call_id"] == "t1"
    assert result.prompt_version == "system:v1+tools:v1" and len(result.prompt_hash) == 16
    assert result.cost_usd > 0


def test_other_profile_ids_are_refused():
    fake = FakeProvider(
        [
            FakeTurn(tool_calls=[ToolCall("t1", "get_credit_profile", {"profile_id": "p_002"})]),
            FakeTurn(text="Sorry."),
        ]
    )
    result = run_turn(USER, "story_001", provider=fake)
    assert result.tool_calls[0]["is_error"]
    assert "story_001" in result.tool_calls[0]["output"]["error"]["message"]


def test_system_prompt_names_profile():
    fake = FakeProvider([FakeTurn(text="Hi.")])
    run_turn(USER, "story_002", provider=fake)
    assert "`story_002`" in fake.requests[0].system


def test_max_iterations_stops_loop():
    looping = [
        FakeTurn(tool_calls=[ToolCall(f"t{i}", "explain_factor", {"factor_code": "UTILIZATION"})])
        for i in range(10)
    ]
    result = run_turn(USER, "story_001", provider=FakeProvider(looping))
    assert result.stop == "max_iterations"
    assert result.final_text == INCOMPLETE_MESSAGE
    assert result.iterations == 6


def test_refusal_returns_safe_message():
    result = run_turn(USER, "story_001", provider=FakeProvider([FakeTurn(stop_reason="refusal")]))
    assert result.stop == "refusal" and result.final_text == REFUSAL_MESSAGE


def test_conversation_must_end_with_user():
    import pytest

    with pytest.raises(ValueError):
        run_turn([{"role": "assistant", "content": "hi"}], "p_001", provider=FakeProvider([]))


class BlockWord:
    name = "block_word"

    def check_sentence(self, sentence, context):
        if "forbidden" in sentence:
            return FilterDecision("block", filter_name=self.name, reasons=["word"])
        return FilterDecision("pass", filter_name=self.name)

    def check_final(self, full_text, context):
        if "retract-me" in full_text:
            return FilterDecision("retract", text="Replaced.", filter_name=self.name)
        return FilterDecision("pass", filter_name=self.name)


def test_filter_blocks_a_sentence():
    fake = FakeProvider([FakeTurn(text="This is fine. This is forbidden. Also fine.")])
    result = run_turn(USER, "p_001", provider=fake, output_filters=[BlockWord()])
    assert result.final_text == "This is fine. Also fine."


def test_filter_retracts_final():
    fake = FakeProvider([FakeTurn(text="Please retract-me now.")])
    result = run_turn(USER, "p_001", provider=fake, output_filters=[BlockWord()])
    assert result.retracted and result.final_text == "Replaced."
    assert any(e["type"] == "retract" for e in result.events)


def test_sentence_buffer_keeps_decimals_together():
    buf = SentenceBuffer()
    out = buf.feed("Utilization is 40") + buf.feed(".8% now. Next")
    assert out == ["Utilization is 40.8% now. "]
    assert buf.flush() == ["Next"]
