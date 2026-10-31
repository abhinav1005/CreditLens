import pytest

from assistant.config import Usage, load_config, load_pricing, request_cost


def test_config_loads():
    config = load_config()
    assert config.assistant.model == "claude-sonnet-5-5"
    assert config.judge.model == "claude-sonnet-5-5"
    assert config.model_config_for("claude-haiku-4-5-20251001").supports_effort is False


def test_every_configured_model_has_pricing():
    config, pricing = load_config(), load_pricing()
    assert set(config.models) <= set(pricing.models)


def test_model_override(monkeypatch):
    from assistant import config as cfg

    cfg._load_config.cache_clear()
    monkeypatch.setenv("CREDITLENS_ASSISTANT_MODEL", "claude-haiku-5-5")
    assert cfg.load_config().assistant.model == "claude-haiku-5-5"
    cfg._load_config.cache_clear()


def test_unknown_model_rejected(monkeypatch):
    from assistant import config as cfg

    cfg._load_config.cache_clear()
    monkeypatch.setenv("CREDITLENS_ASSISTANT_MODEL", "gpt-unknown")
    with pytest.raises(KeyError):
        cfg.load_config()
    cfg._load_config.cache_clear()


def test_cost_by_hand():
    # Sonnet 5.5: 10,000 input × $2/M + 1,000 output × $10/M + 5,000 cache reads × $0.20/M
    # = 0.02 + 0.01 + 0.001 = $0.031
    usage = Usage(input_tokens=10_000, output_tokens=1_000, cache_read_tokens=5_000)
    assert request_cost(load_pricing(), "claude-sonnet-5-5", usage) == pytest.approx(0.031)


def test_haiku_long_context_tier():
    pricing = load_pricing()
    small = request_cost(pricing, "claude-haiku-5-5", Usage(input_tokens=100_000))
    large = request_cost(pricing, "claude-haiku-5-5", Usage(input_tokens=100_001))
    assert small == pytest.approx(0.01)
    assert large == pytest.approx(100_001 * 0.50 / 1_000_000)


def test_usage_adds():
    total = Usage(input_tokens=1, output_tokens=2) + Usage(input_tokens=3, cache_read_tokens=4)
    assert total == Usage(input_tokens=4, output_tokens=2, cache_read_tokens=4)
