"""Unit test: app.main's mode-dependent wiring (debugger, mock router, migrations)."""

from typing import Any

import debugpy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module


def test_configure_debugger_skips_non_dev_modes() -> None:
    """_configure_debugger does nothing for "production" (no debugpy call)."""
    main_module._configure_debugger("production")  # must not raise


def test_configure_debugger_enables_debugpy_for_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """_configure_debugger("dev") calls debugpy.listen, suppressing RuntimeError."""
    calls: list[tuple[str, int]] = []

    def _fake_listen(address: tuple[str, int]) -> None:
        calls.append(address)
        raise RuntimeError("already listening")

    monkeypatch.setattr(debugpy, "listen", _fake_listen)
    main_module._configure_debugger("dev")  # must not raise despite the RuntimeError
    assert calls == [("127.0.0.1", 5678)]


def test_mount_mode_specific_routers_skips_non_mock_modes() -> None:
    """_mount_mode_specific_routers leaves a "dev"-mode app without /mock/token."""
    app = FastAPI()
    main_module._mount_mode_specific_routers(app, "dev")
    response = TestClient(app).post("/mock/token", json={"sub": "u"})
    assert response.status_code == 404


def test_mount_mode_specific_routers_mounts_mock_router() -> None:
    """_mount_mode_specific_routers("mock") adds a working POST /mock/token."""
    app = FastAPI()
    main_module._mount_mode_specific_routers(app, "mock")
    response = TestClient(app).post("/mock/token", json={"sub": "u"})
    assert response.status_code == 200


async def test_lifespan_skips_migrations_when_mode_is_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lifespan context manager skips _run_migrations entirely for MODE=mock."""
    calls: list[Any] = []
    monkeypatch.setattr(main_module, "_run_migrations", lambda: calls.append(1))
    monkeypatch.setattr(main_module.settings, "mode", "mock")
    async with main_module.lifespan(main_module.app):
        pass
    assert calls == []
