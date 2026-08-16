from pathlib import Path

import pytest

from app.services.agent.sandbox import ToolSandbox


def test_sandbox_restricts_filesystem_paths(tmp_path: Path):
    sandbox = ToolSandbox([str(tmp_path)])
    allowed = sandbox.validate_path(str(tmp_path / "note.txt"))
    assert allowed == (tmp_path / "note.txt").resolve()

    with pytest.raises(PermissionError):
        sandbox.validate_path("/etc/passwd")


def test_sandbox_truncates_large_output():
    sandbox = ToolSandbox()
    content, truncated = sandbox.truncate_output("a" * (11 * 1024))
    assert truncated is True
    assert content.endswith("...[truncated]")


def test_sandbox_filters_secret_env_vars():
    sandbox = ToolSandbox()
    filtered = sandbox.filtered_env({"API_TOKEN": "secret", "PATH": "/usr/bin", "NORMAL_VAR": "ok"})
    assert "API_TOKEN" not in filtered
    assert filtered["PATH"] == "/usr/bin"
    assert filtered["NORMAL_VAR"] == "ok"
