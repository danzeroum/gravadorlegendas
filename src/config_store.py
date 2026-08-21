"""Persistência de preferências do usuário em config.json.

Salva e carrega configurações de UI como tema, região de captura,
prefixo padrão, etc. O arquivo fica em data/config.json.
"""
import json
from pathlib import Path

_CONFIG_FILE = Path("data") / "config.json"

_DEFAULTS = {
    "theme": "light",
    "screen_region": {"top": 0, "left": 50, "width": 1820, "height": 80},
    "last_prefix": "legendas",
    "activate_captions": True,
    "use_api_translate": False,
    "use_api_answer": False,
    "window_geometry": "1200x800",
    "ui_scaling": 1.0,
    "llm": {
        "active_provider": "ollama",
        "providers": {
            "openai":     {"api_key": "", "model": "gpt-3.5-turbo"},
            "deepseek":   {"api_key": "", "model": "deepseek-chat"},
            "ollama":     {
                "base_url": "https://api.buildtovalue.cloud",
                "model": "mistral:latest",
            },
            "local_gguf": {
                "model_path": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
                "n_ctx": 2048, "n_threads": 4
            },
        },
    },
}


class ConfigStore:
    """Gerencia leitura e escrita de preferências do usuário.

    Uso:
        store = ConfigStore()
        theme = store.get("theme")
        store.set("theme", "dark")
    """

    def __init__(self):
        self._data = dict(_DEFAULTS)
        self._load()

    def _load(self):
        try:
            if _CONFIG_FILE.exists():
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self):
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        """Retorna o valor de uma chave de configuração.

        Args:
            key: Nome da chave.
            default: Valor padrão se a chave não existir.

        Returns:
            Valor armazenado ou default.
        """
        return self._data.get(key, default)

    def set(self, key: str, value):
        """Atualiza e persiste uma chave de configuração.

        Args:
            key: Nome da chave.
            value: Novo valor.
        """
        self._data[key] = value
        self._save()

    def set_region(self, region: dict):
        """Atualiza a região de captura e persiste."""
        self.set("screen_region", region)

    def get_llm_config(self) -> dict:
        """Retorna a configuração completa de LLM."""
        return self.get("llm", _DEFAULTS["llm"])

    def set_llm_config(self, llm_cfg: dict):
        """Persiste a configuração de LLM."""
        self.set("llm", llm_cfg)

    def get_llm_provider_config(self, name: str) -> dict:
        """Retorna a configuração de um provedor específico."""
        llm_cfg = self.get_llm_config()
        return llm_cfg.get("providers", {}).get(name, {})

    def set_llm_provider_config(self, name: str, provider_cfg: dict):
        """Atualiza a configuração de um provedor específico."""
        llm_cfg = self.get_llm_config()
        llm_cfg.setdefault("providers", {})[name] = provider_cfg
        self.set_llm_config(llm_cfg)


config_store = ConfigStore()
