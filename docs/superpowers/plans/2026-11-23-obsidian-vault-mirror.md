# Obsidian Vault Mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opted-in projects' memories appear as interlinked markdown pages in one Obsidian vault under `<vault>/Chronicle/<project>/`, kept live from SQLite.

**Architecture:** A new `chronicle.vault` package in core: settings (config.json), paths/safety, atomic marker-aware writer, pure renderers, a project-folder file catalog, and a `VaultMirror` that `MemoryService` notifies after every mutation. CLI (`chronicle vault …`), MCP tools and the dashboard are thin wrappers.

**Tech Stack:** Python 3.12 stdlib (no PyYAML), SQLAlchemy 2, FastMCP 4.2, React 19 dashboard, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-23-obsidian-vault-mirror-design.md` (read its "Clarifications" section — those are binding decisions).

## Global Constraints

- No new dependencies. Frontmatter written by hand; every string value double-quoted with `\` and `"` escaped.
- SQLite is canonical; the vault is a rebuildable projection. Behavior with no vault configured is unchanged.
- Write only under `<vault>/Chronicle/`; refuse any resolved path outside it (symlinks, `..`).
- Every generated file has frontmatter `generated_by: "chronicle"`; Chronicle only overwrites/deletes files carrying it. A non-marked file at a generated path is left alone and reported.
- Nothing is written for a project not in `vault_projects`. Cross-project link targets in non-opted-in projects render as plain text `(in project <name>, not mirrored)` — never their content or page.
- Wikilinks always use full vault-relative paths with an alias: `[[Chronicle/<project>/memories/<file-stem>|<title>]]`, `[[Chronicle/<project>/<project>|<project>]]`, `[[Chronicle/<project>/log|log]]`, `[[Chronicle/<project>/files|files]]`.
- Memory page file stem: `<type>-<title>-<first 8 chars of id>`, total stem ≤ 80 chars; title = first non-empty line of content, sanitized; empty → `untitled`. Stem never changes when content is edited.
- Vault failures never fail a memory write: log to stderr, record last error for `vault status`.
- All file writes atomic (temp file in the same dir + `os.replace`).
- Business logic stays in core; CLI/MCP/dashboard are thin. `server.py` is already 453 lines: new MCP tools go in `src/chronicle/vault/tools.py` via a `register(mcp, get_service)` function.
- Files ~300 lines, functions ~40 lines.
- Tests: `uv run pytest -q` stays green (baseline 419 passed, 8 skipped). Tests use `tmp_path` vaults and `CHRONICLE_CONFIG_PATH` pointed at a tmp file — never the real `~/.chronicle/config.json` or a real vault.

## Review Focus

1. **Content that would break YAML** (a source path with `:` or `"`, a project name with quotes) → frontmatter still parses; values quoted. Test in Task 3.
2. **Vault folder deleted or unmounted after configuring** → `memory_add` still succeeds; `vault status` shows the error. Test in Task 5.
3. **Two memories with identical first lines** → distinct files via the id suffix. Test in Task 1.
4. **Unicode/emoji, Windows-reserved names (`CON`, `aux`), `/` or `..` in titles or project names, very long first lines** → safe stem ≤ 80 chars inside the project folder. Test in Task 1.
5. **Re-running `vault sync` and re-adding a project** → no changes on the second run; no duplicate pages. Test in Task 5.

---

### Task 1: Vault settings, paths and safe writer

**Files:**
- Create: `src/chronicle/vault/__init__.py` (empty), `src/chronicle/vault/settings.py`, `src/chronicle/vault/paths.py`, `src/chronicle/vault/writer.py`
- Modify: `src/chronicle/config.py` (extract shared `read_config() -> dict` / `write_config(data: dict) -> None`, atomic; `set_semantic` uses them)
- Test: `tests/test_vault_foundation.py`

**Interfaces — Produces:**
- `settings.vault_path() -> Path | None`; `settings.set_vault_path(path: Path) -> Path` (resolves, creates `<path>/Chronicle/`, raises `ValueError` for home or filesystem root); `settings.vault_projects() -> list[str]`; `settings.add_project(name: str) -> None`; `settings.remove_project(name: str) -> None`; `settings.similarity_links() -> bool` (default False); `settings.is_mirrored(project: str) -> bool` (vault set AND project opted in).
- `paths.MARKER = "chronicle"`; `paths.safe_name(text: str, max_length: int) -> str`; `paths.memory_stem(type_: str, content: str, memory_id: str) -> str`; `paths.chronicle_root(vault: Path) -> Path`; `paths.project_dir(vault: Path, project: str) -> Path`; `paths.memory_file(vault: Path, project: str, stem: str) -> Path`; `paths.wikilink(vault_relative_target: str, alias: str) -> str` (target without `.md`); `paths.inside_root(vault: Path, candidate: Path) -> Path` (resolved; raises `ValueError` if outside `<vault>/Chronicle/`).
- `writer.write_page(vault: Path, path: Path, text: str) -> bool` (False and no write if an existing file lacks the marker; True if written or already identical); `writer.delete_page(vault: Path, path: Path) -> bool` (only marked files); `writer.is_generated(path: Path) -> bool` (frontmatter contains `generated_by: "chronicle"`).

- [ ] **Step 1: Write failing tests**

```python
def test_settings_roundtrip_and_opt_in(tmp_path, monkeypatch): ...
    # set_vault_path(tmp_path/"v") creates v/Chronicle; add_project("p"); is_mirrored("p") True, ("q") False
def test_set_vault_path_refuses_home_and_root(monkeypatch, tmp_path): ...
def test_semantic_setting_survives_vault_writes(tmp_path, monkeypatch): ...  # config keys coexist
def test_identical_first_lines_get_distinct_stems():
    assert memory_stem("note", "Same line", "aaaaaaaa-1") != memory_stem("note", "Same line", "bbbbbbbb-2")
def test_stem_is_safe_and_bounded():
    for text in ["../../etc/passwd", "CON", "aux.txt", "a/b\\c:d*?\"<>|", "🙂" * 200, "x" * 500, "   \n\n"]:
        stem = memory_stem("note", text, "12345678-abcd")
        assert len(stem) <= 80 and "/" not in stem and "\\" not in stem and ".." not in stem
        assert stem.endswith("12345678")
    assert memory_stem("note", "", "12345678-x") == "note-untitled-12345678"
def test_project_dir_with_traversal_name_stays_inside(tmp_path): ...  # project "../evil" -> inside Chronicle/
def test_inside_root_rejects_symlink_escape(tmp_path): ...
def test_write_page_is_atomic_and_marker_protected(tmp_path, monkeypatch): ...
    # user file without marker at target -> write_page False, content unchanged
    # os.replace raising -> no partial target file, no leftover temp file
def test_delete_page_only_deletes_marked_files(tmp_path): ...
def test_wikilink_format():
    assert wikilink("Chronicle/p/memories/note-x-12345678", "x") == "[[Chronicle/p/memories/note-x-12345678|x]]"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_vault_foundation.py -q` — FAIL (module missing).
- [ ] **Step 3: Implement** the three modules and the config helpers. Windows reserved names (CON, PRN, AUX, NUL, COM1–9, LPT1–9, case-insensitive) get a `_` suffix; collapse whitespace to `-`; strip `<>:"/\|?*` and control chars.
- [ ] **Step 4: Run** focused tests then `uv run pytest -q` — all pass.
- [ ] **Step 5: Commit** `feat(vault): settings, safe paths and marker-aware atomic writer`

---

### Task 2: Source references on memories

**Files:**
- Modify: `src/chronicle/core/repository.py` (`create_memory` gains `source_kind: str = "external"`; Source lookup matches project + locator + kind; `get_active_by_source_locator_all` / `get_active_by_source_locator` exclude `kind="reference"`)
- Modify: `src/chronicle/core/service.py` (`add_memory` gains `source_kind: str = "external"`, passed through; `_serialize` adds `"source_kind"`)
- Modify: `src/chronicle/server.py` (`memory_add` gains `source: str | None = None`; normalize: `http://`/`https://` kept as-is, otherwise `Path(source).expanduser().resolve()` as string; passes `source_kind="reference"`)
- Test: `tests/test_source_references.py`

**Interfaces — Produces:** `MemoryService.add_memory(..., source: str | None, source_kind: str = "external")`; serialized memory dict includes `"source"` and `"source_kind"`.

- [ ] **Step 1: Failing tests**

```python
def test_memory_add_stores_a_resolved_file_reference(tmp_path, ...):  # via server.memory_add(source="~/x/../x/terms.pdf")
    # result source == str(resolved path), source_kind == "reference"
def test_memory_add_keeps_urls_verbatim(...): ...
def test_importer_never_supersedes_a_reference_memory(tmp_path, service):
    # reference memory with source=<file>; then import_directory over the folder containing <file>, change file, re-import
    # reference memory stays active; importer memories supersede only each other
def test_reference_and_import_sources_are_separate_rows(...): ...
def test_existing_add_memory_callers_unchanged(...): ...  # default kind "external"
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4:** focused + full suite pass.
- [ ] **Step 5: Commit** `feat: memories can reference a file or URL as their source`

---

### Task 3: Page renderers (pure)

**Files:**
- Create: `src/chronicle/vault/render.py`
- Test: `tests/test_vault_render.py`

**Interfaces:**
- Consumes: `paths.memory_stem`, `paths.wikilink`, `paths.MARKER`; serialized memory dicts from `MemoryService._serialize` (keys incl. `source`, `source_kind` from Task 2).
- Produces (all return `str`, no I/O except `Path.exists` for sources):
  - `LinkTarget` = `dataclass(frozen=True)`: `project: str, stem: str | None, title: str` (`stem=None` ⇒ not mirrored).
  - `render_memory(memory: dict, links: dict[str, LinkTarget], vault: Path) -> str` — `links` maps memory id → target for every id referenced by `supersedes`, `relations`, and inbound relations passed in `memory["_inbound"]` (list of `{"type","source"}`).
  - `render_project(project: str, overview: str | None, memories: list[dict], vault: Path) -> str`
  - `render_log(project: str, memories: list[dict]) -> str`
  - `render_index(projects: list[tuple[str, str]]) -> str` (name, one-line summary)

Memory page = frontmatter (`chronicle_id, project, type, status, created, updated, confidence?, source?, generated_by`), optional banner line (`> Replaced by [[…]]` / `> Marked wrong` / `> Retracted`), content verbatim, then `## Links` with `Project:`, `Replaces:`, `Replaced by:`, `<relation_type>:` (outbound), `<relation_type> (from):` (inbound), `Source:`. Source rendering: inside vault → `[[<vault-relative path without .md for .md files, with extension otherwise>]]`; other path → `[name](file:///abs/path)` plus ` (file not found)` if missing; URL → `[url](url)`. Log lines: `## [YYYY-MM-DD] created | <title>` and `## [YYYY-MM-DD] superseded|marked wrong|retracted | <title>`, newest first, each followed by the wikilink.

- [ ] **Step 1: Failing tests**

```python
def test_memory_page_frontmatter_parses_with_hostile_values(tmp_path):
    # source 'C:\\a "b": c' and project 'p"q' -> frontmatter block parses with a tiny key: "value" parser in the test; generated_by == "chronicle"
def test_supersede_and_relation_links_use_full_paths(tmp_path): ...
def test_unmirrored_link_target_renders_plain_text_without_content(tmp_path):
    # LinkTarget("secret_proj", None, "anything") -> "(in project secret_proj, not mirrored)"; the target title/content absent
def test_banners_for_superseded_wrong_retracted(tmp_path): ...
def test_source_in_vault_is_wikilink_outside_is_file_url_missing_is_flagged(tmp_path): ...
def test_log_is_newest_first_and_grep_friendly(): ...
def test_project_page_links_log_files_and_recent_memories(tmp_path): ...
```

- [ ] **Step 2–4:** fail → implement → pass (focused + full).
- [ ] **Step 5: Commit** `feat(vault): markdown renderers for memory, project, log and index pages`

---

### Task 4: File catalog

**Files:**
- Create: `src/chronicle/vault/catalog.py`
- Modify: `src/chronicle/import_cli.py` (export `SKIP_DIRS` as the public name for `_SKIP_DIRS`, keep behavior)
- Test: `tests/test_vault_catalog.py`

**Interfaces — Produces:**
- `CatalogEntry` = frozen dataclass `folder: str, relative_path: str, absolute_path: str, size: int, modified: str` (ISO date).
- `list_files(project: str, query: str | None = None, limit: int = 2000) -> tuple[list[CatalogEntry], bool]` — scans every registry folder mapped to `project` (`registry.list_projects()`), skips hidden dirs/files and `SKIP_DIRS`, case-insensitive substring filter on relative path, returns `(entries, truncated)`.
- `render_files(project: str, entries: list[CatalogEntry], truncated: bool) -> str` — marked page, grouped by folder, `[relative_path](file:///…)`, type (extension), size, modified; "No project folder registered" when the project has no folders; "Truncated at N files" when truncated.
- (Task 6 wires `memory_list_files`.)

- [ ] **Step 1: Failing tests** — skips `node_modules`, `.git`, hidden files; filter `"pay"` finds `invoices/Payment-Terms.pdf`; cap 3 with 5 files → 3 entries + truncated; two registered folders grouped; no folder → message.
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5: Commit** `feat(vault): project folder file catalog`

---

### Task 5: VaultMirror and live refresh

**Files:**
- Create: `src/chronicle/vault/mirror.py`
- Modify: `src/chronicle/core/service.py` (`self.observers: list[Callable[[list[str]], None]] = []`; private `_notify(ids)` called at the end of `add_memory`, `set_status`, `confirm_memory`, `edit_memory`, `link_memories` (both ids), `merge_memories`, `split_memory`, `set_document`; each observer call wrapped so an exception is logged to stderr and swallowed)
- Modify: `src/chronicle/core/runtime.py` (`create_runtime` appends `VaultMirror(service).on_memories_changed`)
- Modify: `src/chronicle/core/repository.py` (add `inbound_relations(project: str, target_ids: set[str]) -> list[tuple[str, str, str]]` = (source_id, type, target_id), scoped to one project — no unscoped scan)
- Test: `tests/test_vault_mirror.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4.
- Produces: `VaultMirror(service: MemoryService)` with `on_memories_changed(ids: list[str]) -> None`, `sync_project(project: str) -> SyncResult`, `sync_all() -> list[SyncResult]`, `remove_project(project: str) -> int` (deleted count), `status() -> dict` (`vault`, `projects` with page counts, `last_sync`, `last_error`, `skipped_user_files`). `SyncResult` = dataclass `project: str, written: int, unchanged: int, deleted: int, skipped: list[str]`.

Behavior: `on_memories_changed` is a no-op unless the vault is set; for each id in a mirrored project re-render that page, its supersede predecessor/successor, both ends of outbound/inbound explicit links (including a neighbor in a *different* mirrored project), the project page and `log.md`. `sync_project` renders every memory page, project page, `log.md`, `files.md`, `Chronicle/index.md`, then deletes marked files under `Chronicle/<project>/` with no matching memory. `remove_project` deletes only marked files under that project's folder and removes empty dirs, then calls `settings.remove_project`. Errors are caught, logged, stored as `last_error`. Similarity links: only when `settings.similarity_links()` is true AND semantic search is enabled, `sync_project` adds a `similar:` line per memory using the same top-k / min-similarity the dashboard graph uses (reuse `chronicle.core.graph`), same-project only; live refresh does not recompute them (next sync does). `render_memory` takes them via `memory["_similar"]` (list of ids resolved through `links`). Test: `test_similarity_links_only_when_enabled` (off by default → no `similar:` line; on + fake vectors → line present).

- [ ] **Step 1: Failing tests**

```python
def test_nothing_written_without_vault_or_opt_in(tmp_path, service): ...
def test_add_memory_writes_page_project_and_log_when_mirrored(tmp_path, service): ...
def test_supersede_updates_both_pages(tmp_path, service): ...
def test_link_across_two_mirrored_projects_updates_both(tmp_path, service): ...
def test_link_to_unmirrored_project_leaks_nothing(tmp_path, service):  # grep the vault for the secret content -> absent
def test_vault_folder_removed_does_not_break_memory_add(tmp_path, service):
    # configure, rmtree vault, memory_add returns id; mirror.status()["last_error"] set
def test_sync_is_idempotent_and_prunes_orphans(tmp_path, service):
    # second sync_project -> written == 0, deleted == 0; stray marked file deleted; user file kept and listed in skipped
def test_remove_project_deletes_only_marked_files(tmp_path, service): ...
def test_observer_failure_is_isolated(service): ...  # observer raising -> add_memory still returns id
```

- [ ] **Step 2–4:** fail → implement → pass (focused + full).
- [ ] **Step 5: Commit** `feat(vault): live mirror of opted-in projects into the Obsidian vault`

---

### Task 6: CLI, MCP tools, agent guidance, background job

**Files:**
- Create: `src/chronicle/vault_cli.py`, `src/chronicle/vault/tools.py`
- Modify: `src/chronicle/cli.py` (`"vault": _module_main("vault_cli")` + help lines), `src/chronicle/server.py` (call `vault.tools.register(mcp, _get_service)`; one instruction sentence), `src/chronicle/refresh.py` (`start_vault_sync(service) -> dict` using the existing single-job slot), `skills/chronicle-memory/SKILL.md`
- Test: `tests/test_vault_cli.py`, `tests/test_vault_tools.py`

**Interfaces:** CLI `chronicle vault set <path> | add <project> | remove <project> | status | sync [<project>]` (prints `SyncResult`/status lines; errors → exit 1 with message). MCP tools in `tools.register`: `memory_vault_status() -> dict`, `memory_vault_add_project(project: str) -> dict` (adds + `sync_project`), `memory_vault_remove_project(project: str) -> dict`, `memory_vault_sync(project: str | None = None) -> dict` (starts the background job via `refresh.start_vault_sync`; returns job status), `memory_list_files(query: str | None = None, scope_path: str | None = None) -> dict` (`{"files": [...], "truncated": bool}`, project via `scope_path` or `config.get_project()`). Errors → `ToolError`. SKILL.md: never call `memory_vault_add_project`/`remove_project` unless the user asks; when the user says "note this file/note in Chronicle", read it and call `memory_add(..., source=<path>)`; use `memory_list_files` to find documents in the project folder. Server instructions: one sentence with the same `source` + `memory_list_files` guidance.

- [ ] **Step 1: Failing tests** — CLI set/add/status/sync/remove round trip on a tmp vault (output lines, exit codes, `set` on home → exit 1); tools via `fastmcp.Client(server.mcp)` following tests/test_server.py's pattern: add_project writes pages, list_files returns filtered files, vault_sync returns running/busy per refresh rules, remove deletes pages.
- [ ] **Step 2–4:** fail → implement → pass (focused + full).
- [ ] **Step 5: Commit** `feat(vault): chronicle vault CLI, MCP tools and agent guidance`

---

### Task 7: Dashboard toggle and docs

**Files:**
- Modify: `src/chronicle/dashboard.py` (snapshot gains `vault: {"path", "projects", "last_sync", "last_error"}` from `VaultMirror.status()`), `dashboard/src/App.tsx` (per-project "Show in Obsidian" toggle on project cards calling `memory_vault_add_project`/`memory_vault_remove_project`; "Sync vault" button in the control tab calling `memory_vault_sync` and reusing the existing progress strip; vault path + last error shown; toggle disabled with hint when no vault set), `dashboard/src/index.css` (minimal), `docs/INSTALL.md` (new "Obsidian" section: `vault set`, opt-in, what pages contain, sync caveat for client data), `README.md` (one short section), `CHANGELOG.md` (Unreleased → Added)
- Test: `tests/test_dashboard.py` (snapshot includes `vault`), `tests/test_install_docs.py` (INSTALL mentions `chronicle vault set`)

- [ ] **Step 1:** failing snapshot + docs tests. **Step 2:** implement. **Step 3:** `uv run pytest -q` and `cd dashboard && npm ci && npx tsc -b && npm run build` pass.
- [ ] **Step 4: Commit** `feat(dashboard): Show in Obsidian toggle and Sync vault; docs`

---

### Task 8: Real-machine verification (controller, no code)

- [ ] Use a scratch vault in the session scratchpad and a copy of `~/.chronicle/config.json` restored afterwards. `chronicle vault set <scratch>`; `vault add chronicle`; check `Chronicle/chronicle/` has project page, log, files, memory pages; links resolve to existing files; frontmatter has the marker.
- [ ] Add a test memory via the CLI/MCP in a scratch project, confirm the page appears live; supersede it, confirm both pages update. Clean up the scratch project memories and config.
- [ ] If Obsidian is installed, open the scratch vault and check the graph; otherwise record "Obsidian UI not verified".
