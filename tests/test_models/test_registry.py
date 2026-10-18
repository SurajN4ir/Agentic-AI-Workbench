"""
tests/test_models/test_registry.py
==================================
Tests for the model registry, configuration resolution, and UI options.
"""

from app.models.registry import (
    get_model_config,
    get_model_for_role,
    get_model_options,
    get_model_registry,
    get_role_context_windows,
    load_models_config,
)


class TestModelRegistry:
    def test_load_config_contains_models_and_options(self) -> None:
        cfg = load_models_config()
        assert "models" in cfg
        assert "options" in cfg
        assert "reasoning" in cfg["models"]
        assert "coding" in cfg["models"]

    def test_get_model_registry_returns_dict(self) -> None:
        reg = get_model_registry()
        assert isinstance(reg, dict)
        assert "reasoning" in reg
        assert "coding" in reg
        assert "embedding" in reg
        assert reg["reasoning"] != ""

    def test_get_model_for_role_known_and_unknown(self) -> None:
        coding_model = get_model_for_role("coding")
        assert any(m in coding_model for m in ["llama", "coder", "qwen"])

        # Unknown role should fall back to default or reasoning model
        fallback = get_model_for_role("unknown_role_xyz", default="fallback:latest")
        assert fallback == "fallback:latest"

        default_fallback = get_model_for_role("another_unknown")
        assert default_fallback != ""

    def test_get_model_config_typed(self) -> None:
        cfg = get_model_config("reasoning")
        assert cfg.tag != ""
        assert cfg.context_window >= 2048
        assert isinstance(cfg.supports_thinking, bool)

    def test_get_role_context_windows(self) -> None:
        windows = get_role_context_windows()
        assert "reasoning" in windows
        assert windows["reasoning"] >= 2048

    def test_get_model_options_has_auto(self) -> None:
        options = get_model_options()
        assert len(options) >= 3
        ids = [opt.id for opt in options]
        assert "auto" in ids
        assert "reasoning" in ids
        assert "coding" in ids
