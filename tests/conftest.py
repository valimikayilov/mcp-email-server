from __future__ import annotations

import os
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent

os.environ["MCP_EMAIL_SERVER_CONFIG_PATH"] = (_HERE / "config.toml").as_posix()
os.environ["MCP_EMAIL_SERVER_LOG_LEVEL"] = "DEBUG"


@pytest.fixture(autouse=True)
def patch_env(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory):
    from mcp_email_server.config import delete_settings

    delete_settings()
    yield
