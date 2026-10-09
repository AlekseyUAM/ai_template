from agentmon.pricing import cost_for


def test_known_model_cost():
    # 1M input + 1M output opus по таблице
    cost = cost_for("claude-opus-4-8", 1_000_000, 1_000_000, 0, 0)
    assert cost == 90.0  # 15 + 75


def test_unknown_model_zero():
    assert cost_for("some-unknown-model", 1_000_000, 1_000_000, 0, 0) == 0.0


def test_none_model_zero():
    assert cost_for(None, 1000, 1000, 1000, 1000) == 0.0


def test_cache_tokens_counted():
    cost = cost_for("claude-opus-4-8", 0, 0, 1_000_000, 1_000_000)
    assert round(cost, 4) == round(1.5 + 18.75, 4)
