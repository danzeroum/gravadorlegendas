"""Testes para a API FastAPI."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_translate_local(client):
    mock_translator = MagicMock()
    mock_translator.translate.return_value = "olá mundo"
    with patch("src.api.server._get_translator", return_value=mock_translator):
        resp = client.post("/translate", json={"text": "hello world", "use_api": False})
    assert resp.status_code == 200
    assert resp.json()["translated"] == "olá mundo"
    assert resp.json()["source"] == "local"


def test_translate_rejects_oversized_input(client):
    resp = client.post("/translate", json={"text": "x" * 10_001})
    assert resp.status_code == 422


def test_summarize(client):
    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = "resumo aqui"
    with patch("src.api.server._get_summarizer", return_value=mock_summarizer):
        resp = client.post("/summarize", json={"text": "texto longo"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == "resumo aqui"


def test_generate(client):
    mock_gen = MagicMock()
    mock_gen.generate.return_value = "Simple answer."
    with patch("src.api.server._get_answer_gen", return_value=mock_gen):
        resp = client.post("/generate", json={
            "question": "What is this?", "context": "a meeting"
        })
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Simple answer."


def test_generate_rejects_oversized_question(client):
    resp = client.post("/generate", json={
        "question": "q" * 2_001, "context": "ctx"
    })
    assert resp.status_code == 422


def test_list_providers(client):
    with patch("src.api.server.llm_manager") as mock_mgr:
        mock_mgr.is_initialized = True
        mock_mgr.list_providers.return_value = [{"name": "ollama"}]
        resp = client.get("/v1/llm/providers")
    assert resp.status_code == 200
    assert resp.json()["providers"][0]["name"] == "ollama"


def test_get_llm_config(client):
    with patch("src.api.server.config_store") as mock_store:
        mock_store.get_llm_config.return_value = {"active_provider": "ollama"}
        resp = client.get("/v1/llm/config")
    assert resp.status_code == 200
    assert resp.json()["active_provider"] == "ollama"
