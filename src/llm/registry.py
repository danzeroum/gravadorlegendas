from src.llm.base import BaseLLMProvider


class ProviderRegistry:
    """Registro de provedores de LLM com descoberta e ativação."""

    def __init__(self):
        self._classes: dict[str, type[BaseLLMProvider]] = {}
        self._instances: dict[str, BaseLLMProvider] = {}
        self._active: str | None = None

    def register(self, name: str, provider_cls: type[BaseLLMProvider]):
        self._classes[name] = provider_cls

    def list_providers(self) -> list[str]:
        return list(self._classes.keys())

    def get_provider_class(self, name: str) -> type[BaseLLMProvider] | None:
        return self._classes.get(name)

    def get_instance(self, name: str) -> BaseLLMProvider | None:
        return self._instances.get(name)

    def set_instance(self, name: str, instance: BaseLLMProvider):
        self._instances[name] = instance

    @property
    def active_name(self) -> str | None:
        return self._active

    @active_name.setter
    def active_name(self, name: str | None):
        self._active = name

    def get_active(self) -> BaseLLMProvider | None:
        if self._active is None:
            return None
        return self._instances.get(self._active)


registry = ProviderRegistry()
