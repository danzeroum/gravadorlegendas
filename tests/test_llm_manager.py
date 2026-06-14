"""Testes para LLMManager."""
import pytest
from unittest.mock import MagicMock, patch

from src.llm.manager import LLMManager


@pytest.fixture
def manager():
    return LLMManager()


def test_not_initialized_by_default(manager):
    assert manager.is_initialized is False


def test_initialize_sets_flag(manager):
    mock_provider = MagicMock()
    mock_provider.generate.return_value = "ok"
    with patch("src.llm.manager.config_store") as mock_store, \
         patch("src.llm.manager.registry") as mock_registry:
        mock_store.get_llm_config.return_value = {
            "active_provider": "openai",
            "providers": {"openai": {"api_key": "test", "model": "gpt-3.5-turbo"}},
        }
        mock_registry.get_provider_class.return_value = MagicMock(return_value=mock_provider)
        mock_registry.list_providers.return_value = ["openai"]
        manager.initialize()
    assert manager.is_initialized is True


def test_generate_returns_error_when_no_provider(manager):
    with patch("src.llm.manager.registry") as mock_registry:
        mock_registry.get_active.return_value = None
        with patch.object(manager, "initialize"):
            mock_registry.get_active.return_value = None
            result = manager.generate("prompt")
    assert "Erro" in result


def test_active_provider_initially_none(manager):
    with patch("src.llm.manager.registry") as mock_registry:
        mock_registry.active_name = None
        assert manager.active_provider is None


def test_is_initialized_property_reflects_state(manager):
    assert manager.is_initialized is False
    manager._initialized = True
    assert manager.is_initialized is True
