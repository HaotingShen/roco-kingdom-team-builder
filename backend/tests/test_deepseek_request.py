"""
Unit tests for DeepSeek request construction (build_deepseek_request_kwargs).

Guards the DeepSeek-V4 thinking-mode migration:
- V4 models enable thinking via extra_body and omit temperature while thinking.
- Legacy model names keep their exact pre-migration request shape (rollback safety).
- response_format json_object is always forced (the analysis pipeline depends on it).
"""
from backend.llm_service import build_deepseek_request_kwargs

MESSAGES = [{"role": "user", "content": "hi"}]


def _kwargs(model, thinking_enabled=None, reasoning_effort=None):
    return build_deepseek_request_kwargs(
        model=model,
        messages=MESSAGES,
        max_tokens=32768,
        temperature=0.7,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
    )


def test_v4_flash_thinking_enabled():
    k = _kwargs("deepseek-v4-flash", thinking_enabled=True, reasoning_effort="high")
    assert k["model"] == "deepseek-v4-flash"
    assert k["response_format"] == {"type": "json_object"}
    assert k["extra_body"]["thinking"] == {"type": "enabled"}
    assert k["extra_body"]["reasoning_effort"] == "high"
    # Thinking mode ignores temperature -> must NOT be sent (R3/R1 guard)
    assert "temperature" not in k


def test_v4_flash_thinking_disabled_sends_temperature():
    k = _kwargs("deepseek-v4-flash", thinking_enabled=False)
    assert k["extra_body"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in k["extra_body"]
    assert k["temperature"] == 0.7


def test_v4_pro_thinking_enabled_max_effort():
    k = _kwargs("deepseek-v4-pro", thinking_enabled=True, reasoning_effort="max")
    assert k["extra_body"]["thinking"] == {"type": "enabled"}
    assert k["extra_body"]["reasoning_effort"] == "max"
    assert "temperature" not in k


def test_legacy_reasoner_unchanged():
    # Rollback safety: no extra_body, no temperature (byte-identical to pre-migration).
    # thinking_enabled is ignored for non-V4 models.
    k = _kwargs("deepseek-reasoner", thinking_enabled=True)
    assert "extra_body" not in k
    assert "temperature" not in k


def test_legacy_chat_unchanged():
    # Non-thinking legacy model still receives temperature, no extra_body.
    k = _kwargs("deepseek-chat", thinking_enabled=True)
    assert "extra_body" not in k
    assert k["temperature"] == 0.7


def test_json_object_always_forced():
    for model in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner", "deepseek-chat"):
        assert _kwargs(model)["response_format"] == {"type": "json_object"}
