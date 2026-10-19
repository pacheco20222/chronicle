from pathlib import Path


def test_install_docs_cover_claude_desktop_scope_selection():
    install = (Path(__file__).parents[1] / "docs" / "INSTALL.md").read_text()

    assert "Claude Desktop" in install
    assert "claude_desktop_config.json" in install
    assert '"mcpServers"' in install
    assert "no working directory" in install
    assert "scope_path" in install


def test_packaged_compose_file_matches_the_root_one():
    root = Path(__file__).parents[1]
    assert (root / "src" / "chronicle" / "docker-compose.yml").read_text() == (root / "docker-compose.yml").read_text()
