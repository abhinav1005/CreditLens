import pytest

from assistant.config import load_config
from assistant.loop import run_turn
from assistant.providers.fake import FakeProvider, FakeTurn
from assistant.router import route


@pytest.mark.parametrize(
    "text,tier",
    [
        ("How does credit utilization work?", "small"),
        ("What is a hard inquiry?", "small"),
        ("Can you write me a poem?", "big"),  # "me" → personal; the big model handles refusals too
        ("What's my utilization?", "big"),
        ("Why did I lose points?", "big"),
        ("What if the balance were paid off?", "big"),  # simulation
    ],
)
def test_route(text, tier):
    assert route([{"role": "user", "content": text}])[0] == tier


def test_follow_ups_go_big():
    conv = [
        {"role": "user", "content": "What is utilization?"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "And credit mix?"},
    ]
    assert route(conv) == ("big", "follow-up turn")


def test_run_turn_uses_cheap_model_when_routing_enabled(monkeypatch):
    config = load_config().model_copy(deep=True)
    config.routing.enabled = True
    seen = []

    def fake_get_provider(model, cfg):
        seen.append(model)
        return FakeProvider([FakeTurn(text="Utilization is balance divided by limit.")])

    monkeypatch.setattr("assistant.loop.get_provider", fake_get_provider)
    r = run_turn(
        [{"role": "user", "content": "How does utilization work?"}], "p_001", config=config
    )
    assert seen == ["claude-haiku-5-5"] and r.model == "claude-haiku-5-5"
    assert r.extra["route"]["tier"] == "small"
