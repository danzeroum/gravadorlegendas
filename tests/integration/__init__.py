"""Testes de integração real — exigem infraestrutura audiovisual.

Estes testes NÃO rodam no CI headless padrão. Eles pulam graciosamente
quando os pré-requisitos não estão disponíveis, e só executam em
ambientes Fedora desktop reais com PipeWire ativo.

Comandos:
    # CI padrão (headless) — exclui integração
    pytest -q -m "not integration"

    # Integração PipeWire (exige PipeWire rodando)
    pytest -q -m "integration and requires_pipewire"

    # Integração STT (exige modelo Whisper baixado)
    pytest -q -m "integration and requires_stt_model"

    # Integração X11 (exige sessão gráfica X11)
    pytest -q -m "integration and requires_x11"
"""
