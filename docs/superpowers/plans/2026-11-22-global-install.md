# Global Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Chronicle once per machine; git repos become projects automatically, other folders are registered after asking, Claude Desktop uses one entry and passes `scope_path`.

**Architecture:** A new core module `chronicle/project_resolution.py` owns "which project is this?" (env → registry → auto-register git repo → fail closed with guidance). `config.get_project()`, the recall hook and the MCP server all go through it. A new `chronicle/setup_global.py` writes user-level configs for each installed app without a pinned project, reusing `setup_cli` helpers.

**Tech Stack:** Python 3.12, FastMCP 4.2, pytest, uv. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-22-global-install-design.md`

## Global Constraints

- No new dependencies or services; local-first.
- Every request resolves to exactly one project or fails closed (unless explicit `scope_path` / global search).
- Never register home or filesystem root (existing `registry.register` guard).
- Never auto-register a name already used by a different path.
- `CHRONICLE_PROJECT` env var always wins; existing registry, pinned configs, per-project installs unchanged.
- Auto-registered project name = the repo top-level folder's name, verbatim (`Path.name`), matching manual registration (no normalization exists today).
- Business logic stays out of MCP tool bodies and CLI handlers (project CLAUDE.md).
- Files ~300 lines max: `setup_cli.py` is already ~300, so global setup goes in its own module.
- Run tests with `uv run pytest -q`; full suite must stay green (currently 357 passed, 8 skipped).

## Review Focus

1. **Home folder is itself a git repo (dotfiles).** Repo root = home → must not register; fall through to the ask-the-user error. Test in Task 1.
2. **Agent opened in a subfolder of an unregistered repo.** Must register the repo root, not the subfolder. Test in Task 1.
3. **`git` missing or hanging.** Treat as non-git (no crash, ask-the-user error). Test in Task 1.
4. **Claude Desktop's working folder is `/` (or home).** Error must carry the `memory_list_scopes` + `scope_path` guidance. Test in Task 1.
5. **Second process after auto-registration** (hook registered, then MCP server starts). Must resolve via registry with `registered_now=False` — no duplicate notice. Test in Task 2.

---

### Task 1: Core project resolution with git auto-registration

**Files:**
- Create: `src/chronicle/project_resolution.py`
- Modify: `src/chronicle/registry.py` (rename `_main_worktree` → `main_worktree`, update its caller in `lookup`)
- Modify: `src/chronicle/config.py:44-62` (`get_project` delegates)
- Test: `tests/test_project_resolution.py`

**Interfaces:**
- Produces:
  - `class ProjectNotFoundError(RuntimeError)` — message is agent-facing guidance.
  - `@dataclass(frozen=True) class Resolution: project: str; registered_now: bool`
  - `def resolve(cwd: Path) -> Resolution`
  - `def take_registration_notice() -> str | None` — returns and clears the pending notice set by the last auto-registration in this process.
  - `registry.main_worktree(cwd: Path) -> Path | None` (renamed, behavior unchanged).
  - `config.get_project() -> str` now returns `resolve(Path.cwd()).project` (still raises a `RuntimeError` subclass, so existing callers and `except RuntimeError` keep working).

Resolution order inside `resolve`:
1. `CHRONICLE_PROJECT` (stripped) → `Resolution(project, False)`.
2. `registry.lookup(cwd)` hit → `Resolution(hit, False)`. `RegistryError` → raise `ProjectNotFoundError` with today's "registry couldn't be read" message.
3. `root = registry.main_worktree(cwd)`; if `root` is not None, not home, not filesystem root, and `root.name` is not already a project at a different path (`registry.list_projects()`), call `registry.register(root, root.name)`, set the pending notice to `f"Registered {root} as Chronicle project '{root.name}' (git repo, automatic)."`, return `Resolution(root.name, True)`.
4. Name clash → raise `ProjectNotFoundError` containing `"already used by"`, the other path, and `"memory_register_project"`.
5. Otherwise raise `ProjectNotFoundError` whose message contains both: `"ask the user"` + `"memory_register_project"` (folder clients) and `"memory_list_scopes"` + `"scope_path"` (no-folder clients such as Claude Desktop).

- [ ] **Step 1: Write the failing tests** in `tests/test_project_resolution.py`. Fixture: `monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", tmp_path / "projects.json")`, `monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)`, helper `git_repo(path)` running `git init -q` via `subprocess.run(check=True)`.

```python
def test_env_var_wins_and_registers_nothing(repo, monkeypatch):
    monkeypatch.setenv("CHRONICLE_PROJECT", "pinned")
    assert resolve(repo) == Resolution("pinned", False)
    assert registry.list_projects() == {}

def test_git_repo_is_registered_under_its_folder_name(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    assert resolve(repo) == Resolution("dolphin", True)
    assert registry.list_projects() == {"dolphin": [str(repo.resolve())]}
    assert "dolphin" in take_registration_notice()
    assert take_registration_notice() is None

def test_subfolder_registers_the_repo_root(tmp_path):
    repo = git_repo(tmp_path / "dolphin"); (repo / "src").mkdir()
    assert resolve(repo / "src").project == "dolphin"
    assert registry.list_projects() == {"dolphin": [str(repo.resolve())]}

def test_already_registered_repo_is_not_reregistered(tmp_path):
    repo = git_repo(tmp_path / "dolphin"); resolve(repo); take_registration_notice()
    assert resolve(repo) == Resolution("dolphin", False)
    assert take_registration_notice() is None

def test_name_used_by_another_path_is_refused(tmp_path):
    git_repo(tmp_path / "a" / "api"); registry.register(tmp_path / "a" / "api", "api")
    other = git_repo(tmp_path / "b" / "api")
    with pytest.raises(ProjectNotFoundError, match="already used by"):
        resolve(other)
    assert registry.list_projects() == {"api": [str((tmp_path / "a" / "api").resolve())]}

def test_plain_folder_asks_the_user(tmp_path):
    with pytest.raises(ProjectNotFoundError) as error:
        resolve(tmp_path)
    assert "ask the user" in str(error.value) and "memory_register_project" in str(error.value)
    assert registry.list_projects() == {}

def test_home_dotfiles_repo_is_not_registered(tmp_path, monkeypatch):
    home = git_repo(tmp_path / "home"); monkeypatch.setattr(Path, "home", lambda: home)
    with pytest.raises(ProjectNotFoundError):
        resolve(home)
    assert registry.list_projects() == {}

def test_missing_git_counts_as_plain_folder(tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "dolphin")
    monkeypatch.setattr(registry.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    with pytest.raises(ProjectNotFoundError):
        resolve(repo)

def test_no_folder_client_gets_scope_path_guidance(monkeypatch):
    with pytest.raises(ProjectNotFoundError) as error:
        resolve(Path("/"))
    assert "memory_list_scopes" in str(error.value) and "scope_path" in str(error.value)

def test_worktree_resolves_to_the_main_repo(tmp_path):
    # one commit, `git worktree add`, then resolve(worktree).project == "dolphin"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_project_resolution.py -q` — expected: FAIL (`ModuleNotFoundError: chronicle.project_resolution`).
- [ ] **Step 3: Rename** `registry._main_worktree` → `main_worktree`; update `lookup`. Run `uv run pytest tests/test_registry.py -q` — expected PASS (fix any test that references the old name).
- [ ] **Step 4: Implement** `project_resolution.py` per the order above; pending notice is a module-level `str | None`. Make `config.get_project()` return `project_resolution.resolve(Path.cwd()).project` (import inside the function if needed to avoid a `config` ↔ `registry` cycle).
- [ ] **Step 5: Run** `uv run pytest tests/test_project_resolution.py tests/test_config.py tests/test_server.py -q` — expected PASS.
- [ ] **Step 6: Run full suite** `uv run pytest -q` — expected: all pass, 8 skipped.
- [ ] **Step 7: Commit**

```bash
git add src/chronicle/project_resolution.py src/chronicle/registry.py src/chronicle/config.py tests/test_project_resolution.py tests/test_registry.py
git commit -m "feat: auto-register git repos as projects on first use"
```

---

### Task 2: Tell the user once (recall hook + MCP notice + agent guidance)

**Files:**
- Modify: `src/chronicle/recall.py` (`main`)
- Modify: `src/chronicle/server.py` (new middleware next to `QdrantUnavailableMiddleware`; server `instructions` text)
- Modify: `skills/chronicle-memory/SKILL.md` (Setup section)
- Test: `tests/test_recall.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `project_resolution.resolve`, `ProjectNotFoundError`, `take_registration_notice` (Task 1).
- Produces: `class RegistrationNoticeMiddleware(Middleware)` in `server.py`.

Behavior:
- `recall.main()`: replace the env/`registry.lookup` block with `resolve(Path.cwd())`; on `ProjectNotFoundError` (or any exception) return silently as today. If `registered_now`, print `f"[Chronicle] {take_registration_notice()}"` before the checkpoint/overview.
- `RegistrationNoticeMiddleware.on_call_tool`: after `call_next`, if `take_registration_notice()` returns text, append `TextContent(type="text", text=f"[Chronicle] {notice}")` to the result's content and return it. Register it with `mcp.add_middleware`.
- Server instructions: replace the "if no project is set… call memory_register_project" sentence with: git repos register automatically; for other folders ask the user, then `memory_register_project(name)`; clients with no project folder (Claude Desktop) call `memory_list_scopes`, confirm the project with the user, and pass `scope_path` on every call for that chat.
- SKILL.md Setup: same rule in two bullets, replacing the current "not registered" bullet.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_recall.py
def test_recall_announces_an_automatic_registration(tmp_path, monkeypatch, capsys):
    repo = git_repo(tmp_path / "dolphin"); monkeypatch.chdir(repo)
    recall.main()
    assert "[Chronicle] Registered" in capsys.readouterr().out

def test_recall_after_registration_does_not_announce_again(tmp_path, monkeypatch, capsys):
    repo = git_repo(tmp_path / "dolphin"); registry.register(repo, "dolphin"); monkeypatch.chdir(repo)
    recall.main()
    assert "Registered" not in capsys.readouterr().out

# tests/test_server.py — through fastmcp.Client(server.mcp), cwd = fresh git repo
async def test_first_tool_call_in_a_new_repo_carries_the_notice_once(...):
    first = await client.call_tool("memory_add", {"content": "x", "type": "note"})
    second = await client.call_tool("memory_add", {"content": "y", "type": "note"})
    assert any("[Chronicle] Registered" in c.text for c in first.content)
    assert not any("Registered" in getattr(c, "text", "") for c in second.content)
```

(Move `git_repo` into `tests/conftest.py` so all three files share it.)

- [ ] **Step 2: Run** `uv run pytest tests/test_recall.py tests/test_server.py -q` — expected: the three new tests FAIL.
- [ ] **Step 3: Implement** recall change, middleware, instructions, SKILL.md bullets.
- [ ] **Step 4: Run** `uv run pytest -q` — expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add src/chronicle/recall.py src/chronicle/server.py skills/chronicle-memory/SKILL.md tests/
git commit -m "feat: announce automatic project registration once; guide agents for unregistered and folderless clients"
```

---

### Task 3: `chronicle setup --global`

**Files:**
- Create: `src/chronicle/setup_global.py`
- Modify: `src/chronicle/setup_cli.py` (`_server_entry`, `_recall_hook_command` accept `project: str | None`; `main` adds `--global`)
- Test: `tests/test_setup_global.py`

**Interfaces:**
- Consumes from `setup_cli`: `_server_entry(project: str | None, install_dir: Path) -> dict` (omit `"env"` when `project is None`), `_recall_hook_command(project: str | None, install_dir: Path) -> str` (no `CHRONICLE_PROJECT=` / `$env:` prefix when `None`), `_merge_server`, `_merge_hook`, `_desktop_config_path`.
- Produces: `def setup_global(dry_run: bool, hook: bool) -> list[str]` — returns the printed lines (one or more per app), so tests assert on them.

Per app, in this order; skip with a one-line "skipped: <app> not found" when absent:
- **Claude Code** (`shutil.which("claude")`): run `["claude", "mcp", "add", "--scope", "user", "chronicle", "--", *command]` (`--print` → print it instead). If `hook`, `_merge_hook(Path.home() / ".claude" / "settings.json", _recall_hook_command(None, install_dir), dry_run)`.
- **Cursor** (`(Path.home() / ".cursor").is_dir()`): `_merge_server(Path.home() / ".cursor" / "mcp.json", "chronicle", entry, dry_run)`.
- **Codex** (`shutil.which("codex")`): `["codex", "mcp", "add", "chronicle", "--", *command]`; no registration.
- **Claude Desktop** (macOS/Windows only; config folder exists): `_merge_server(_desktop_config_path(), "chronicle", entry, dry_run)`, then the existing "fully quit Claude Desktop" line.
- If `Path.cwd() / ".mcp.json"` defines `mcpServers.chronicle`, add a warning line containing `"also defines 'chronicle'"` (do not modify it).

`main`: `--global` is mutually exclusive with `agent` and `--project` (`parser.error`). `--print` and `--no-hook` apply.

- [ ] **Step 1: Write failing tests** (monkeypatch `Path.home` to `tmp_path / "home"`, `shutil.which`, `subprocess.run` to record calls, and `setup_cli._desktop_config_path`).

```python
def test_entries_have_no_pinned_project(fake_home):
    setup_global(dry_run=False, hook=True)
    cursor = json.loads((fake_home / ".cursor" / "mcp.json").read_text())
    assert "env" not in cursor["mcpServers"]["chronicle"]

def test_claude_code_uses_user_scope_and_user_hook(fake_home, calls):
    setup_global(dry_run=False, hook=True)
    assert calls[0][:6] == ["claude", "mcp", "add", "--scope", "user", "chronicle"]
    settings = (fake_home / ".claude" / "settings.json").read_text()
    assert "chronicle-recall" in settings and "CHRONICLE_PROJECT" not in settings

def test_print_mode_changes_nothing(fake_home, calls):
    lines = setup_global(dry_run=True, hook=True)
    assert calls == [] and not (fake_home / ".cursor" / "mcp.json").exists()
    assert any("claude mcp add --scope user chronicle" in line for line in lines)

def test_missing_apps_are_skipped(fake_home_without_apps):
    assert any(line.startswith("skipped: Cursor") for line in setup_global(dry_run=True, hook=True))

def test_warns_about_a_project_level_chronicle_server(fake_home, tmp_path, monkeypatch):
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"chronicle": {}}}'); monkeypatch.chdir(tmp_path)
    assert any("also defines 'chronicle'" in line for line in setup_global(dry_run=True, hook=True))

def test_global_rejects_project_flag(capsys):
    with pytest.raises(SystemExit):
        setup_cli.main(["--global", "--project", "x"])
```

- [ ] **Step 2: Run** `uv run pytest tests/test_setup_global.py -q` — expected: FAIL (module missing).
- [ ] **Step 3: Implement** the `None`-project paths in the two helpers, `setup_global.py`, and the `--global` flag.
- [ ] **Step 4: Run** `uv run pytest tests/test_setup_global.py tests/test_setup_cli.py tests/test_windows_compat.py -q` — expected PASS (existing per-project setup output unchanged).
- [ ] **Step 5: Run full suite** `uv run pytest -q` — expected: all pass.
- [ ] **Step 6: Commit**

```bash
git add src/chronicle/setup_global.py src/chronicle/setup_cli.py tests/test_setup_global.py
git commit -m "feat: chronicle setup --global writes user-level config for every installed app"
```

---

### Task 4: Docs lead with global install

**Files:**
- Modify: `docs/INSTALL.md`, `README.md` (install snippet only), `src/chronicle/cli.py` (help line for `setup --global`), `CHANGELOG.md` (Unreleased → Added)
- Test: `tests/test_install_docs.py` (existing; extend if it asserts on install commands)

Content:
- INSTALL.md opens with "Install once": `chronicle setup --global`; what happens in a git repo (automatic, one-line notice), in other folders and Obsidian vaults (the agent asks once), in Claude Desktop (say which project; one entry for all). Existing per-project sections move under "Alternative: per-project install", text otherwise unchanged.
- CHANGELOG Unreleased → Added: auto-registration of git repos, ask-first for other folders, `setup --global`, single Claude Desktop entry with `scope_path`.

- [ ] **Step 1:** Add a test to `tests/test_install_docs.py` asserting `"chronicle setup --global"` appears in INSTALL.md before the first `"--scope project"`. Run it — expected FAIL.
- [ ] **Step 2:** Edit the docs and CLI help.
- [ ] **Step 3: Run** `uv run pytest -q` — expected: all pass.
- [ ] **Step 4: Commit**

```bash
git add docs/INSTALL.md README.md src/chronicle/cli.py CHANGELOG.md tests/test_install_docs.py
git commit -m "docs: lead with global install; per-project install becomes the alternative"
```

---

### Task 5: Real-world verification (no code)

- [ ] `uv run chronicle setup --global --print` on this Mac — output lists Claude Code, Cursor/Codex/Desktop as found or skipped; nothing written.
- [ ] In a scratch git repo outside any registered path (cwd = that repo), run `uv run --project <this worktree> chronicle-recall` — prints the `[Chronicle] Registered … automatic` line once; second run prints none. Remove the scratch entry from `~/.chronicle/projects.json` afterwards.
- [ ] In a scratch non-git folder, `uv run --project <this worktree> python -c "from chronicle import config; config.get_project()"` — raises with the ask-the-user guidance; registry unchanged.
- [ ] Obsidian assumption from the spec: note in the PR whether it could be confirmed (Claude Code started in a vault root); if not confirmed, say so.
