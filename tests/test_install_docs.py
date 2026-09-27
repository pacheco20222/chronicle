from pathlib import Path


def test_install_docs_cover_claude_desktop_scope_selection():
    install = (Path(__file__).parents[1] / "docs" / "INSTALL.md").read_text()

    assert "Claude Desktop" in install
    assert "claude_desktop_config.json" in install
    assert '"mcpServers"' in install
    assert "no working directory" in install
    assert "scope_path" in install
