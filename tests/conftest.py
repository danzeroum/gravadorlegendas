"""Configuração global de testes: reset de structlog e outros estados globais."""
from __future__ import annotations

import logging
import structlog


def pytest_configure(config):
    """Executa antes de todos os testes: configura structlog com logger stdlib válido."""
    # Configurar logging stdlib primeiro
    logging.basicConfig(level=logging.DEBUG)
    
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def pytest_unconfigure(config):
    """Executa após todos os testes."""
    structlog.reset_defaults()