"""Testes de integração REAIS para comportamento em Wayland.

Validam E2E-12: em Wayland, o app deve falhar de forma clara e explícita,
sem tela preta silenciosa, sem loop de erro, sem crash.

Exigem:
- Sessão Wayland ativa (XDG_SESSION_TYPE=wayland)

Marcadores:
    @pytest.mark.integration
    @pytest.mark.requires_display

Rodar:
    pytest -q -m "integration and requires_display" -k wayland
"""
from __future__ import annotations

import os

import pytest

from tests.integration.conftest import require_display, require_wayland


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_display,
]


class TestWaylandBehaviorReal:
    """E2E-12: Wayland — comportamento seguro e explícito."""

    def setup_method(self):
        require_display()
        # Não pula se for X11 — alguns testes são cross-session.
        # Apenas os específicos de Wayland chamam require_wayland().

    def test_e2e_12_wayland_screen_capture_fails_clearly(self):
        """E2E-12: Em Wayland, ScreenCapture lança erro claro."""
        require_wayland()

        from src.capture.screen_capture import ScreenCapture, ScreenCaptureError

        region = {"top": 0, "left": 0, "width": 100, "height": 50}
        cap = ScreenCapture(region)

        # Sem portal: deve lançar ScreenCaptureError, NÃO devolver frame preto.
        with pytest.raises(ScreenCaptureError) as exc_info:
            cap.capture()
        msg = str(exc_info.value)
        # Mensagem deve ser orientativa
        assert "Wayland" in msg or "X11" in msg or "portal" in msg

    def test_wayland_session_detected(self):
        """Confirma que PlatformCapabilities detecta Wayland."""
        require_wayland()

        from src.platform.detection import detect_capabilities, SessionType
        caps = detect_capabilities()
        assert caps.session == SessionType.WAYLAND
        assert caps.is_wayland
        # Em Wayland sem portal, screen_capture é False
        if not caps.supports_portal_screen_capture:
            assert caps.supports_screen_capture is False

    def test_wayland_app_does_not_crash_on_init(self):
        """Confirma que SessionManager inicializa em Wayland sem crash."""
        require_wayland()

        from src.main import SessionManager
        # Deve construir sem lançar exceção
        sm = SessionManager()
        assert sm.capabilities.is_wayland
        # is_running deve ser False
        assert not sm.is_running

    def test_x11_works_in_x11_session(self):
        """Em X11, captura funciona normalmente (controle regressivo)."""
        from src.platform.detection import detect_capabilities, SessionType
        caps = detect_capabilities()
        if caps.session != SessionType.X11:
            pytest.skip("Sessão não é X11 — controle cruzado não aplicável")
        # Se chegou aqui, é X11 — captura deve funcionar
        from src.capture.screen_capture import ScreenCapture
        region = {"top": 0, "left": 0, "width": 50, "height": 50}
        cap = ScreenCapture(region)
        img = cap.capture()
        extrema = img.convert("L").getextrema()
        assert extrema != (0, 0), "Frame preto em X11 — captura deveria funcionar"
