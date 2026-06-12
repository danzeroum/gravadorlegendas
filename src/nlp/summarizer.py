from src.llm.manager import llm_manager


class Summarizer:
    """Resumo de texto usando o provedor de LLM ativo."""

    def summarize(
        self,
        text: str,
        model: str | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> str:
        """Gera um resumo do texto fornecido via LLMManager.

        Args:
            text: Texto completo a ser resumido.
            model: Ignorado (o modelo é definido no provedor ativo).
            system_prompt: Instrução para o sistema.
            user_prompt: Instrução para o usuário (prefixo do texto).

        Returns:
            Resumo gerado ou mensagem de erro.
        """
        if not text.strip():
            return "[Erro: texto vazio]"
        sys = system_prompt or "Você é um assistente que resume reuniões."
        usr = user_prompt or "Por favor, resuma o seguinte texto:"
        prompt = f"{usr}\n\n{text}"
        return llm_manager.generate(prompt, system_prompt=sys)
