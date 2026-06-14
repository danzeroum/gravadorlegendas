"""Serviço central de LLM.

Gerencia a criação, ativação e uso de provedores de IA.
Toda chamada de generate/summarize passa por ele.
"""
from src.config_store import config_store
from src.llm.registry import registry
from src.llm.providers.openai import OpenAIProvider
from src.llm.providers.deepseek import DeepSeekProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.local_gguf import LocalGGUFProvider


_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "ollama": OllamaProvider,
    "local_gguf": LocalGGUFProvider,
}


class LLMManager:
    """Gerencia o provedor de LLM ativo.

    Uso:
        mgr = LLMManager()
        mgr.initialize()
        mgr.generate("Summarize this...")
    """

    def __init__(self):
        self._initialized = False

    def initialize(self):
        """Registra provedores e ativa o configurado."""
        for name, cls in _PROVIDER_MAP.items():
            registry.register(name, cls)

        llm_cfg = config_store.get_llm_config()
        active = llm_cfg.get("active_provider", "openai")
        self._activate(active, llm_cfg.get("providers", {}).get(active, {}))
        self._initialized = True

    def _activate(self, name: str, provider_cfg: dict):
        provider_cls = registry.get_provider_class(name)
        if provider_cls is None:
            provider_cls = OpenAIProvider
        instance = provider_cls(**provider_cfg)
        registry.set_instance(name, instance)
        registry.active_name = name

    def switch_provider(self, name: str, provider_cfg: dict | None = None):
        """Troca o provedor ativo em tempo real."""
        if provider_cfg is None:
            llm_cfg = config_store.get_llm_config()
            provider_cfg = llm_cfg.get("providers", {}).get(name, {})
        self._activate(name, provider_cfg)
        llm_cfg = config_store.get_llm_config()
        llm_cfg["active_provider"] = name
        config_store.set_llm_config(llm_cfg)

    def list_providers(self) -> list[dict]:
        """Retorna lista de provedores com metadados."""
        result = []
        for name in registry.list_providers():
            inst = registry.get_instance(name)
            info = inst.get_model_info() if inst else {"provider": name}
            result.append({"name": name, **info})
        return result

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """Gera texto usando o provedor ativo."""
        provider = registry.get_active()
        if provider is None:
            self.initialize()
            provider = registry.get_active()
        if provider is None:
            return "[Erro: nenhum provedor de IA ativo]"
        return provider.generate(prompt, system_prompt, **kwargs)

    @property
    def active_provider(self) -> str | None:
        return registry.active_name

    @property
    def is_initialized(self) -> bool:
        """Indica se o manager foi inicializado."""
        return self._initialized


llm_manager = LLMManager()
