import os

import pytest

from assistant.config import load_config
from assistant.providers import ProviderRequest, ToolCall, get_provider
from assistant.providers.anthropic_provider import AnthropicProvider, to_anthropic_messages
from assistant.providers.fake import FakeProvider, FakeTurn


def test_fake_provider_streams_and_records():
    fake = FakeProvider([FakeTurn(text="Your score is 753.")])
    chunks = []
    resp = fake.complete(ProviderRequest(model="m", system="s", messages=[]), on_text=chunks.append)
    assert "".join(chunks) == "Your score is 753."
    assert resp.stop_reason == "end_turn"
    assert len(fake.requests) == 1


def test_message_conversion_round_trip_shape():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "Let me check.",
            "tool_calls": [
                {"id": "t1", "name": "get_utilization", "input": {"profile_id": "p_001"}}
            ],
        },
        {"role": "tool", "results": [{"tool_call_id": "t1", "content": "{}", "is_error": False}]},
    ]
    out = to_anthropic_messages(messages)
    assert out[1]["content"][1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "get_utilization",
        "input": {"profile_id": "p_001"},
    }
    assert (
        out[2]["content"][0]["type"] == "tool_result"
        and out[2]["content"][0]["tool_use_id"] == "t1"
    )


def test_provider_blocks_are_replayed_unchanged():
    blocks = [
        {"type": "thinking", "thinking": "", "signature": "abc"},
        {"type": "text", "text": "ok"},
    ]
    out = to_anthropic_messages(
        [{"role": "assistant", "content": "ok", "tool_calls": [], "provider_blocks": blocks}]
    )
    assert out[0]["content"] is blocks


def test_build_params_effort_and_no_sampling():
    config = load_config()
    sonnet = AnthropicProvider(config.model_config_for("claude-sonnet-5-5"), client=object())
    params = sonnet.build_params(
        ProviderRequest(model="claude-sonnet-5-5", system="s", messages=[], effort="low")
    )
    assert params["output_config"] == {"effort": "low"}
    assert "temperature" not in params and "tool_choice" not in params


def test_haiku_45_gets_no_effort():
    config = load_config()
    haiku = AnthropicProvider(config.model_config_for("claude-haiku-4-5-20251001"), client=object())
    params = haiku.build_params(
        ProviderRequest(model="claude-haiku-4-5-20251001", system="s", messages=[], effort="low")
    )
    assert "output_config" not in params


def test_structured_output_schema():
    config = load_config()
    p = AnthropicProvider(config.model_config_for("claude-sonnet-5-5"), client=object())
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    params = p.build_params(
        ProviderRequest(model="claude-sonnet-5-5", system="s", messages=[], output_schema=schema)
    )
    assert params["output_config"]["format"] == {"type": "json_schema", "schema": schema}


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_tool_call_smoke():
    """One real request: the model should call get_utilization for the given profile."""
    from assistant.prompts import load_bundle

    bundle = load_bundle()
    provider = get_provider("claude-haiku-5-5")
    resp = provider.complete(
        ProviderRequest(
            model="claude-haiku-5-5",
            system=bundle.render_system("story_001"),
            messages=[{"role": "user", "content": "What's my credit utilization right now?"}],
            tools=bundle.tools,
            max_tokens=2000,
            effort="low",
        )
    )
    assert resp.stop_reason == "tool_use"
    assert any(isinstance(c, ToolCall) and c.name == "get_utilization" for c in resp.tool_calls)
    assert resp.usage.input_tokens > 0
