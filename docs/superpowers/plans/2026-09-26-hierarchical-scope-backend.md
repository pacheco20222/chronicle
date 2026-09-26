# Hierarchical Scope + Docs Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a materialized-path scope hierarchy above the existing project-only isolation, a chunked project-agnostic docs pipeline, and the 2 new/extended MCP tools the design spec calls for — all backward-compatible with every existing `project=` call.

**Architecture:** One new `scope` table (id, name, parent_id, path) that existing `project` strings map onto by value — no FK column added to `memory`/`source`/`episode`, so every existing query keeps working unchanged. Docs chunking reuses the existing `Source`/`Episode`/`Memory` triple (one `Source` per file, N `Memory` rows sharing it via a new `chunk_index` column). Cross-project doc linking reuses the existing `memory_link`/`relations` JSON mechanism with a new conventional relation type, consumed via a new opt-in search parameter.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, FastMCP, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-hierarchical-scope-and-docs-design.md`

## Global Constraints

- `project=` parameter semantics on every existing MCP tool must not change — a caller that never passes `scope_path`/`include_linked`/`chunk_index` sees identical behavior to today.
- No LLM calls anywhere in this plan — chunking and link-consumption are deterministic (size/boundary splitting, JSON relation matching).
- No new services/infra (no new vector store, no Redis, no separate DB) — everything extends the existing SQLite + Qdrant-behind-`VectorIndex` stack.
- Every new DB change ships as an Alembic migration under `alembic/versions/`, following the numbering (`0003_...`, `0004_...`) and `upgrade()`/`downgrade()` structure of `alembic/versions/0001_initial_schema.py` and `0002_memory_fts.py`.
- Existing test suite (164 passing as of the 2026-09-26 rename) must still pass unmodified at the end of this plan.

## Review Focus

- **A file exactly at the chunking threshold** — off-by-one at the boundary must not silently produce a 1-token trailing chunk or crash; test the exact-threshold case explicitly, not just "big" vs "small."
- **Rescanning a large (chunked) doc with no changes** — must produce zero writes, same as the existing single-file-per-doc path does today, not re-superscede-and-recreate every chunk on every scan.
- **`memory_list_scopes` with a prefix that matches no scope** — must return an empty list, not raise.
- **`include_linked=True` when no link exists for the current project** — must return the same results as `include_linked=False`, not error or return an empty list.
- **`scope_path` pointing at a path whose parent doesn't exist yet** (e.g. `"work/azure/vm_config"` when neither `work` nor `work/azure` exist) — `memory_set_document` must create the missing ancestor scope rows, not fail with a foreign-key error.

---

### Task 1: `scope` table + migration + backfill

**Files:**
- Modify: `src/chronicle/storage/models.py` (add `Scope` class after `Base`, ~line 13)
- Create: `alembic/versions/0003_scope_hierarchy.py`
- Test: `tests/test_scope_migration.py`

**Interfaces:**
- Produces: `Scope` model — `id: str`, `name: str`, `parent_id: str | None`, `path: str` (unique), `created_at: datetime`. Table name `scope`.

- [ ] **Step 1: Write the failing migration test**

```python
# tests/test_scope_migration.py
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _alembic_config(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_scope_table_backfills_existing_projects(tmp_path):
    db_path = tmp_path / "pre_scope.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    cfg = _alembic_config(url)

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0002_memory_fts")

    # Simulate pre-existing data from two different projects, written
    # before the scope table existed.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source (id, project, kind, locator, created_at) "
                "VALUES (:id, :project, 'external', 'x', '2026-01-01 00:00:00')"
            ),
            {"id": str(uuid.uuid4()), "project": "alpha"},
        )
        connection.execute(
            text(
                "INSERT INTO memory (id, project, type, content, status, "
                "created_at, updated_at, relations) VALUES "
                "(:id, :project, 'note', 'hi', 'active', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '[]')"
            ),
            {"id": str(uuid.uuid4()), "project": "beta"},
        )

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0003_scope_hierarchy")

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT name, path, parent_id FROM scope ORDER BY name")).all()

    assert [(r.name, r.path, r.parent_id) for r in rows] == [
        ("alpha", "alpha", None),
        ("beta", "beta", None),
    ]

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0002_memory_fts")
    with engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='scope'")
        ).all()
    assert tables == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scope_migration.py -v`
Expected: FAIL — `alembic.util.exc.CommandError` (no revision `0003_scope_hierarchy`) or `no such table: scope`.

- [ ] **Step 3: Add the `Scope` model**

In `src/chronicle/storage/models.py`, add after the `Base` class (after line 12):

```python
class Scope(Base):
    __tablename__ = "scope"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("scope.id"), index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
```

- [ ] **Step 4: Write the migration**

```python
# alembic/versions/0003_scope_hierarchy.py
"""add scope hierarchy table, backfilled from existing project values

Revision ID: 0003_scope_hierarchy
Revises: 0002_memory_fts
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "0003_scope_hierarchy"
down_revision: Union[str, Sequence[str], None] = "0002_memory_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scope",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["scope.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scope_parent_id", "scope", ["parent_id"], unique=False)
    op.create_index("ix_scope_path", "scope", ["path"], unique=True)

    connection = op.get_bind()
    existing = connection.execute(
        text(
            "SELECT DISTINCT project FROM ("
            "SELECT project FROM memory UNION "
            "SELECT project FROM source UNION "
            "SELECT project FROM episode"
            ")"
        )
    ).scalars().all()
    now = connection.execute(text("SELECT CURRENT_TIMESTAMP")).scalar()
    for project in sorted(p for p in existing if p):
        connection.execute(
            text(
                "INSERT INTO scope (id, name, parent_id, path, created_at) "
                "VALUES (:id, :name, NULL, :path, :created_at)"
            ),
            {"id": str(uuid.uuid4()), "name": project, "path": project, "created_at": now},
        )


def downgrade() -> None:
    op.drop_index("ix_scope_path", table_name="scope")
    op.drop_index("ix_scope_parent_id", table_name="scope")
    op.drop_table("scope")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scope_migration.py -v`
Expected: PASS

- [ ] **Step 6: Run the full existing suite to confirm no regression**

Run: `uv run pytest -q`
Expected: PASS, same count as before plus the 1 new test.

- [ ] **Step 7: Commit**

```bash
git add src/chronicle/storage/models.py alembic/versions/0003_scope_hierarchy.py tests/test_scope_migration.py
git commit -m "feat: add scope hierarchy table, backfilled from existing projects"
```

---

### Task 2: Repository scope helpers

**Files:**
- Modify: `src/chronicle/core/repository.py` (add methods to `MemoryRepository`, after `all()` at line ~269)
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `Scope` model from Task 1.
- Produces: `MemoryRepository.get_or_create_scope(path: str) -> Scope`, `MemoryRepository.get_scope_by_path(path: str) -> Scope | None`, `MemoryRepository.list_scopes(prefix: str = "") -> list[Scope]`, `MemoryRepository.child_scope_count(scope_id: str) -> int`. `path` uses `/` as separator, e.g. `"work/azure/vm_config"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py (add at end of file)
def test_get_or_create_scope_creates_missing_ancestors(service):
    repo = service.repository
    leaf = repo.get_or_create_scope("work/azure/vm_config")
    assert leaf.path == "work/azure/vm_config"
    assert leaf.name == "vm_config"

    work = repo.get_scope_by_path("work")
    azure = repo.get_scope_by_path("work/azure")
    assert work is not None and work.parent_id is None
    assert azure is not None and azure.parent_id == work.id
    assert leaf.parent_id == azure.id


def test_get_or_create_scope_is_idempotent(service):
    repo = service.repository
    first = repo.get_or_create_scope("work/azure")
    second = repo.get_or_create_scope("work/azure")
    assert first.id == second.id


def test_get_scope_by_path_missing_returns_none(service):
    assert service.repository.get_scope_by_path("nope") is None


def test_list_scopes_prefix_filters(service):
    repo = service.repository
    repo.get_or_create_scope("work/azure/vm_config")
    repo.get_or_create_scope("work/azure/cosmos_db")
    repo.get_or_create_scope("personal/health")

    under_azure = {s.path for s in repo.list_scopes("work/azure")}
    assert under_azure == {"work/azure", "work/azure/vm_config", "work/azure/cosmos_db"}

    everything = {s.path for s in repo.list_scopes("")}
    assert "personal/health" in everything

    assert repo.list_scopes("nonexistent") == []


def test_child_scope_count(service):
    repo = service.repository
    repo.get_or_create_scope("work/azure/vm_config")
    repo.get_or_create_scope("work/azure/cosmos_db")
    work = repo.get_scope_by_path("work")
    azure = repo.get_scope_by_path("work/azure")
    assert repo.child_scope_count(work.id) == 1
    assert repo.child_scope_count(azure.id) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py -k scope -v`
Expected: FAIL — `AttributeError: 'MemoryRepository' object has no attribute 'get_or_create_scope'`

- [ ] **Step 3: Implement the repository methods**

In `src/chronicle/core/repository.py`, add `Scope` to the import on line 8 (`from chronicle.storage.models import Episode, Memory, Scope, Source, utc_now`), then add at the end of `MemoryRepository` (after `all()`):

```python
    def get_scope_by_path(self, path: str) -> Scope | None:
        with self.session_factory() as session:
            return session.scalar(select(Scope).where(Scope.path == path))

    def get_or_create_scope(self, path: str) -> Scope:
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            raise ValueError("scope path must not be empty")
        with self.session_factory() as session:
            parent_id = None
            current_path = ""
            scope_row = None
            for segment in segments:
                current_path = f"{current_path}/{segment}" if current_path else segment
                scope_row = session.scalar(select(Scope).where(Scope.path == current_path))
                if scope_row is None:
                    scope_row = Scope(
                        id=str(uuid.uuid4()),
                        name=segment,
                        parent_id=parent_id,
                        path=current_path,
                    )
                    session.add(scope_row)
                    session.flush()
                parent_id = scope_row.id
            session.commit()
            return scope_row

    def list_scopes(self, prefix: str = "") -> list[Scope]:
        with self.session_factory() as session:
            statement = select(Scope)
            if prefix:
                statement = statement.where(
                    (Scope.path == prefix) | (Scope.path.like(f"{prefix}/%"))
                )
            return list(session.scalars(statement.order_by(Scope.path)).all())

    def child_scope_count(self, scope_id: str) -> int:
        with self.session_factory() as session:
            return session.scalar(
                select(text("count(*)")).select_from(Scope).where(Scope.parent_id == scope_id)
            ) or 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py -k scope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicle/core/repository.py tests/test_core.py
git commit -m "feat: add scope resolution and listing to MemoryRepository"
```

---

### Task 3: `memory_list_scopes` tool

**Files:**
- Modify: `src/chronicle/core/service.py` (add method after `count()` at line ~257)
- Modify: `src/chronicle/server.py` (add tool after `memory_register_project` at line ~279)
- Test: `tests/test_core.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `MemoryRepository.list_scopes`, `MemoryRepository.child_scope_count` from Task 2.
- Produces: `MemoryService.list_scopes(prefix: str = "") -> list[dict]` — each dict: `{"path": str, "name": str, "parent_path": str | None, "child_count": int}`. MCP tool `memory_list_scopes(prefix: str = "") -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_service_list_scopes(service):
    service.repository.get_or_create_scope("work/azure/vm_config")
    result = service.list_scopes("work")
    paths = {item["path"] for item in result}
    assert paths == {"work", "work/azure", "work/azure/vm_config"}
    vm_config = next(item for item in result if item["path"] == "work/azure/vm_config")
    assert vm_config["name"] == "vm_config"
    assert vm_config["parent_path"] == "work/azure"
    assert vm_config["child_count"] == 0
    work = next(item for item in result if item["path"] == "work")
    assert work["parent_path"] is None
    assert work["child_count"] == 1
```

```python
# tests/test_server.py (add near other tool tests)
def test_memory_list_scopes_tool(server, service):
    service.repository.get_or_create_scope("work/azure")
    result = server.memory_list_scopes.fn(prefix="work")
    assert {item["path"] for item in result} == {"work", "work/azure"}


def test_memory_list_scopes_no_match_returns_empty(server, service):
    assert server.memory_list_scopes.fn(prefix="nonexistent") == []
```

Check `tests/test_server.py`'s existing pattern for calling tools (e.g. `server.memory_add.fn(...)`) and match it — FastMCP tools are called via `.fn(...)` in this test suite.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k list_scopes -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement service method**

In `src/chronicle/core/service.py`, add after `count()`:

```python
    def list_scopes(self, prefix: str = "") -> list[dict]:
        scopes = self.repository.list_scopes(prefix)
        return [
            {
                "path": scope.path,
                "name": scope.name,
                "parent_path": scope.path.rsplit("/", 1)[0] if "/" in scope.path else None,
                "child_count": self.repository.child_scope_count(scope.id),
            }
            for scope in scopes
        ]
```

- [ ] **Step 4: Implement MCP tool**

In `src/chronicle/server.py`, add after `memory_register_project`:

```python
@mcp.tool
def memory_list_scopes(prefix: str = "") -> list[dict]:
    return _get_service().list_scopes(prefix)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k list_scopes -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicle/core/service.py src/chronicle/server.py tests/test_core.py tests/test_server.py
git commit -m "feat: add memory_list_scopes tool"
```

---

### Task 4: Core docs at any scope path

**Files:**
- Modify: `src/chronicle/server.py` (`memory_set_document` line ~228, `memory_get_document` line ~259)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `MemoryRepository.get_or_create_scope`, `get_scope_by_path` from Task 2. Existing `MemoryService.set_document`/`get_document` (unchanged signatures — this task only changes what string gets passed as their `project` argument).
- Produces: `memory_set_document(slug, content, type, confidence=None, extraction_method=None, scope_path=None)`, `memory_get_document(slug, scope_path=None)`.
- Convention: when `scope_path` is given, the resolved scope's `path` is used as the underlying `project` string, and by convention the scope's own core/overview doc uses `slug == scope_path` (mirrors the existing per-project convention where a project's overview doc has `slug == project`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
def test_memory_set_document_at_scope_path_creates_ancestors(server, service):
    result = server.memory_set_document.fn(
        slug="work", content="work domain core", type="overview", scope_path="work/azure"
    )
    assert result["project"] == "work/azure"
    assert service.repository.get_scope_by_path("work") is not None
    assert service.repository.get_scope_by_path("work/azure") is not None


def test_memory_get_document_at_scope_path(server, service):
    server.memory_set_document.fn(
        slug="work/azure", content="azure notes", type="overview", scope_path="work/azure"
    )
    result = server.memory_get_document.fn(slug="work/azure", scope_path="work/azure")
    assert result["content"] == "azure notes"


def test_memory_get_document_at_missing_scope_path_returns_none(server, service):
    assert server.memory_get_document.fn(slug="x", scope_path="never/created") is None


def test_memory_set_document_without_scope_path_unchanged(server, service):
    result = server.memory_set_document.fn(slug="chronicle-test", content="c", type="overview")
    assert result["project"] == "chronicle-test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -k "scope_path" -v`
Expected: FAIL — `TypeError: memory_set_document() got an unexpected keyword argument 'scope_path'`

- [ ] **Step 3: Implement**

In `src/chronicle/server.py`, replace `memory_set_document`:

```python
@mcp.tool
def memory_set_document(
    slug: str,
    content: str,
    type: str,
    confidence: float | None = None,
    extraction_method: float | None = None,
    scope_path: str | None = None,
) -> dict:
    if scope_path:
        project = _get_service().repository.get_or_create_scope(scope_path).path
    else:
        project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    doc_id = _get_service().set_document(
        vector,
        content,
        project,
        slug,
        type,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    return {
        "id": doc_id,
        "project": project,
        "slug": slug,
        "type": type,
        "content": content,
        "confidence": confidence,
        "extraction_method": extraction_method,
    }
```

(Note: fix the pre-existing `extraction_method: float | None` typo introduced above — it must be `str | None`, matching every other tool's `extraction_method` parameter in this file.)

Replace `memory_get_document`:

```python
@mcp.tool
def memory_get_document(slug: str, scope_path: str | None = None) -> dict | None:
    if scope_path:
        scope = _get_service().repository.get_scope_by_path(scope_path)
        if scope is None:
            return None
        project = scope.path
    else:
        project = config.get_project()
    return _get_service().get_document(project, slug)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_server.py -k "scope_path" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicle/server.py tests/test_server.py
git commit -m "feat: allow core documents at any scope path, not just a project"
```

---

### Task 5: `chunk_index` column + `get_by_source`

**Files:**
- Modify: `src/chronicle/storage/models.py` (`Memory` class, line ~35)
- Modify: `src/chronicle/core/repository.py` (`create_memory`, `get_active_by_source_locator`)
- Create: `alembic/versions/0004_memory_chunk_index.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces: `Memory.chunk_index: int | None`. `MemoryRepository.create_memory(..., chunk_index: int | None = None)`. `MemoryRepository.get_by_source(source_id: str) -> list[Memory]` (ordered by `chunk_index`, nulls first). `MemoryRepository.get_active_by_source_locator_all(project: str, locator: str) -> list[Memory]` (all active memories for that source, not just the latest one — needed because a chunked doc has N active rows per source, not 1).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_create_memory_with_chunk_index(service):
    repo = service.repository
    row = repo.create_memory(
        id="m1", project="p", type_="document", content="part 1", chunk_index=0
    )
    assert row.chunk_index == 0


def test_get_by_source_orders_by_chunk_index(service):
    repo = service.repository
    repo.create_memory(id="m1", project="p", type_="document", content="c1", source="doc.md", chunk_index=1)
    repo.create_memory(id="m0", project="p", type_="document", content="c0", source="doc.md", chunk_index=0)
    row = repo.get(("m0"))
    chunks = repo.get_by_source(row.source_id)
    assert [c.id for c in chunks] == ["m0", "m1"]


def test_get_active_by_source_locator_all_returns_every_active_chunk(service):
    repo = service.repository
    repo.create_memory(id="m0", project="p", type_="document", content="c0", source="doc.md", chunk_index=0)
    repo.create_memory(id="m1", project="p", type_="document", content="c1", source="doc.md", chunk_index=1)
    rows = repo.get_active_by_source_locator_all("p", "doc.md")
    assert {r.id for r in rows} == {"m0", "m1"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py -k "chunk_index or get_by_source or get_active_by_source_locator_all" -v`
Expected: FAIL — `TypeError: create_memory() got an unexpected keyword argument 'chunk_index'`

- [ ] **Step 3: Add the column to the model**

In `src/chronicle/storage/models.py`, add to `Memory` (after `relations`, line 57):

```python
    chunk_index: Mapped[int | None] = mapped_column(sa.Integer, index=True)
```

Add `import sqlalchemy as sa` at the top alongside the existing `sqlalchemy` imports (or add `Integer` to the existing `from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint` line and use `Integer` directly instead of `sa.Integer`).

- [ ] **Step 4: Write the migration**

```python
# alembic/versions/0004_memory_chunk_index.py
"""add chunk_index to memory for docs chunking

Revision ID: 0004_memory_chunk_index
Revises: 0003_scope_hierarchy
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_memory_chunk_index"
down_revision: Union[str, Sequence[str], None] = "0003_scope_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memory", sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.create_index("ix_memory_chunk_index", "memory", ["chunk_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_chunk_index", table_name="memory")
    op.drop_column("memory", "chunk_index")
```

- [ ] **Step 5: Implement repository changes**

In `src/chronicle/core/repository.py`, `create_memory` signature gains `chunk_index: int | None = None` (add to the parameter list after `episode_id`) and the `Memory(...)` construction gains `chunk_index=chunk_index,`.

Add after `get_active_by_source_locator`:

```python
    def get_by_source(self, source_id: str) -> list[Memory]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Memory).where(Memory.source_id == source_id)
            ).all()
            return sorted(rows, key=lambda row: (row.chunk_index is None, row.chunk_index or 0))

    def get_active_by_source_locator_all(self, project: str, locator: str) -> list[Memory]:
        project = _require_project(project)
        statement = (
            select(Memory)
            .join(Source, Memory.source_id == Source.id)
            .where(
                Memory.project == project,
                Source.project == project,
                Source.locator == locator,
                Memory.status.not_in(HIDDEN_STATUSES),
            )
        )
        with self.session_factory() as session:
            rows = session.scalars(statement).all()
            return sorted(rows, key=lambda row: (row.chunk_index is None, row.chunk_index or 0))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py -k "chunk_index or get_by_source or get_active_by_source_locator_all" -v`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicle/storage/models.py src/chronicle/core/repository.py alembic/versions/0004_memory_chunk_index.py tests/test_core.py
git commit -m "feat: add chunk_index column and source-based chunk lookup"
```

---

### Task 6: Chunking in the folder importer

**Files:**
- Modify: `src/chronicle/core/service.py` (`add_memory`, line ~54)
- Modify: `src/chronicle/import_cli.py` (`_import_directory`, line ~31)
- Test: `tests/test_import_cli.py`

**Interfaces:**
- Consumes: `MemoryRepository.create_memory(..., chunk_index=...)`, `get_active_by_source_locator_all` from Task 5.
- Produces: `MemoryService.add_memory(..., chunk_index: int | None = None)`. `_import_directory` now splits files over `_DOCS_CHUNK_MAX_CHARS` (6000, matching the existing `_chunk_text` proportional-safety-margin comment) into multiple `Memory` rows sharing one `Source`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_import_cli.py (add; check existing file for the fixture/helper pattern already used, e.g. tmp_path directory setup)
def test_import_directory_file_at_exact_threshold_stays_single_chunk(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    exact = tmp_path / "exact.md"
    # Exactly _DOCS_CHUNK_MAX_CHARS characters, no paragraph break, so
    # _chunk_text has nothing to split on and must not produce a
    # trailing near-empty chunk.
    exact.write_text("a" * import_cli._DOCS_CHUNK_MAX_CHARS)

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = service.repository.all("p")
    assert len(rows) == 1
    assert rows[0].chunk_index is None


def test_import_directory_file_one_over_threshold_splits_cleanly(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    over = tmp_path / "over.md"
    half = import_cli._DOCS_CHUNK_MAX_CHARS // 2
    over.write_text(("a" * half) + "\n\n" + ("b" * (half + 10)))

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = [r for r in service.repository.all("p") if r.status == "active"]
    assert len(rows) == 2
    assert all(r.content.strip() for r in rows)
    assert [r.chunk_index for r in sorted(rows, key=lambda r: r.chunk_index)] == [0, 1]


def test_import_directory_chunks_large_file(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))

    import_cli._import_directory(str(tmp_path), "p", "note")

    source = service.repository.database.session_factory().execute(
        __import__("sqlalchemy").select(__import__("chronicle.storage.models", fromlist=["Source"]).Source)
    ).scalars().all()
    assert len(source) == 1
    chunks = service.repository.get_by_source(source[0].id)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_import_directory_small_file_stays_single_row(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    small = tmp_path / "small.md"
    small.write_text("just a short note")

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = service.repository.all("p")
    assert len(rows) == 1
    assert rows[0].chunk_index is None


def test_import_directory_rescanning_unchanged_large_file_is_noop(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))

    import_cli._import_directory(str(tmp_path), "p", "note")
    first_pass_count = len(service.repository.all("p"))

    import_cli._import_directory(str(tmp_path), "p", "note")
    assert len(service.repository.all("p")) == first_pass_count


def test_import_directory_changed_large_file_supersedes_all_chunks(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))
    import_cli._import_directory(str(tmp_path), "p", "note")
    old_active = [r for r in service.repository.all("p") if r.status == "active"]

    big.write_text(("changed " * 3000) + "\n\n" + ("content " * 3000))
    import_cli._import_directory(str(tmp_path), "p", "note")

    all_rows = {r.id: r for r in service.repository.all("p")}
    for old in old_active:
        assert all_rows[old.id].status == "superseded"
    new_active = [r for r in all_rows.values() if r.status == "active"]
    assert len(new_active) >= 1
```

Check the top of `tests/test_import_cli.py` for the existing fixture/monkeypatch conventions already used there and match them instead of duplicating `monkeypatch.setattr(runtime, "_runtime", service)` if a fixture already provides it (the `isolate_server_runtime` autouse fixture in `conftest.py` already sets `runtime._runtime = service` — the explicit `monkeypatch.setattr` above may be redundant; check and remove if so).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_import_cli.py -k chunk -v`
Expected: FAIL

- [ ] **Step 3: Add `chunk_index` passthrough to the service**

In `src/chronicle/core/service.py`, `add_memory` gains `chunk_index: int | None = None` in its parameter list (after `episode_id`) and passes it through to `self.repository.create_memory(...)`.

- [ ] **Step 4: Implement chunking in `_import_directory`**

In `src/chronicle/import_cli.py`, add a constant and rewrite the per-file loop body:

```python
_DOCS_CHUNK_MAX_CHARS = 6000  # ~1500 tokens at ~4 chars/token
```

Replace the loop body (from `content_hash = ...` through `ingested += 1`) with:

```python
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        episode_title = f"{os.path.basename(file_path)} sha256:{content_hash[:16]}"
        active_chunks = service.repository.get_active_by_source_locator_all(project, file_path)
        if active_chunks and active_chunks[0].episode_record and active_chunks[0].episode_record.title == episode_title:
            unchanged += 1
            continue

        for old in active_chunks:
            service.set_status(old.id, "superseded")

        episode = service.repository.create_episode(
            project=project,
            locator=file_path,
            title=episode_title,
        )
        pieces = _chunk_text(content, max_chars=_DOCS_CHUNK_MAX_CHARS)
        for index, piece in enumerate(pieces):
            vector = embeddings.embed_text(piece)
            service.add_memory(
                vector,
                piece,
                project,
                type_,
                source=file_path,
                episode_id=episode.id,
                chunk_index=index if len(pieces) > 1 else None,
            )
        ingested += 1
```

Remove the now-unused `_FOLDER_IMPORT_MAX_CHARS` constant and its truncation logic — chunking replaces truncation for large files (a file no longer needs its tail silently dropped; it needs splitting, which is exactly what `_chunk_text` already does for the single-file CLI path).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_import_cli.py -v`
Expected: PASS (including pre-existing tests in this file — check none of them asserted on `_FOLDER_IMPORT_MAX_CHARS` truncation behavior; if one did, update it to assert chunking instead, since truncation no longer happens).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicle/core/service.py src/chronicle/import_cli.py tests/test_import_cli.py
git commit -m "feat: chunk large files on import instead of truncating"
```

---

### Task 7: `memory_get_by_source` tool + neighbor-bundled search

**Files:**
- Modify: `src/chronicle/core/service.py` (`_serialize` line ~29, `_search` line ~141, add `get_by_source` method)
- Modify: `src/chronicle/server.py` (add tool)
- Test: `tests/test_core.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `MemoryRepository.get_by_source` from Task 5.
- Produces: `MemoryService.get_by_source(source_id: str) -> list[dict]`. `_search` results now include a `"context": list[dict]` key (immediate chunk neighbors, empty list when not chunked). MCP tool `memory_get_by_source(source_id: str) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_service_get_by_source_returns_ordered_chunks(service):
    v = [0.1] * 768
    id0 = service.add_memory(v, "chunk 0", "p", "document", source="doc.md", chunk_index=0)
    id1 = service.add_memory(v, "chunk 1", "p", "document", source="doc.md", chunk_index=1)
    source_id = service.repository.get(id0).source_id
    result = service.get_by_source(source_id)
    assert [r["id"] for r in result] == [id0, id1]


def test_search_bundles_neighbor_chunks(service):
    v = [0.1] * 768
    ids = [
        service.add_memory(v, f"chunk {i} about widgets", "p", "document", source="doc.md", chunk_index=i)
        for i in range(3)
    ]
    results = service.search(v, "p", query_text="widgets", k=1)
    assert len(results) == 1
    hit = results[0]
    context_ids = {c["id"] for c in hit["context"]}
    assert context_ids <= set(ids)
    assert hit["id"] not in context_ids


def test_search_non_chunked_memory_has_empty_context(service):
    v = [0.1] * 768
    service.add_memory(v, "a plain note", "p", "note")
    results = service.search(v, "p", query_text="plain")
    assert results[0]["context"] == []
```

```python
# tests/test_server.py
def test_memory_get_by_source_tool(server, service):
    v = [0.1] * 768
    id0 = service.add_memory(v, "chunk 0", "p", "document", source="doc.md", chunk_index=0)
    source_id = service.repository.get(id0).source_id
    import os
    os.environ["CHRONICLE_PROJECT"] = "p"
    result = server.memory_get_by_source.fn(source_id=source_id)
    assert result[0]["id"] == id0
```

Check `tests/test_server.py`'s existing conventions for setting the active project in a test (likely the `isolate_server_runtime` fixture sets `CHRONICLE_PROJECT=chronicle-test`; use whichever project the fixture already sets rather than overriding the env var directly, to match the file's existing style — read a nearby existing test first).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k "get_by_source or bundles_neighbor or empty_context" -v`
Expected: FAIL

- [ ] **Step 3: Implement `_serialize` context field and `get_by_source`**

In `src/chronicle/core/service.py`, `_serialize` gains `chunk_index` in the returned dict (add `"chunk_index": row.chunk_index,` after `"slug": row.slug,`).

Add method:

```python
    def get_by_source(self, source_id: str) -> list[dict]:
        return [self._serialize(row) for row in self.repository.get_by_source(source_id)]
```

- [ ] **Step 4: Implement neighbor bundling in `_search`**

In `_search`, after `results = self._merge(ranked_lists, rows, k)` and before the `max_tokens` handling, add:

```python
        for item in results:
            item["context"] = []
            if item.get("chunk_index") is None or not item.get("source_id"):
                continue
            siblings = self.repository.get_by_source(item["source_id"])
            neighbors = [
                self._serialize(sibling)
                for sibling in siblings
                if sibling.chunk_index is not None
                and sibling.id != item["id"]
                and abs(sibling.chunk_index - item["chunk_index"]) == 1
            ]
            item["context"] = neighbors
```

Then update the `max_tokens` packing loop so a bundle's neighbors count toward the budget as one unit — change:

```python
            item_tokens = estimate_tokens(item["content"])
```
to:
```python
            item_tokens = estimate_tokens(item["content"]) + sum(
                estimate_tokens(c["content"]) for c in item["context"]
            )
```

- [ ] **Step 5: Implement MCP tool**

In `src/chronicle/server.py`, add after `memory_dashboard_snapshot`:

```python
@mcp.tool
def memory_get_by_source(source_id: str) -> list[dict]:
    return _get_service().get_by_source(source_id)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py tests/test_server.py -v`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicle/core/service.py src/chronicle/server.py tests/test_core.py tests/test_server.py
git commit -m "feat: add memory_get_by_source and neighbor-bundled chunk search"
```

---

### Task 8: `relates_to_project` linking + `include_linked` search

**Files:**
- Modify: `src/chronicle/config.py` (`VALID_RELATION_TYPES`, line 13)
- Modify: `src/chronicle/core/repository.py` (add `find_relation_sources`)
- Modify: `src/chronicle/core/service.py` (`_search`, `search`, `search_global`)
- Modify: `src/chronicle/server.py` (`memory_search`, `memory_search_global`)
- Test: `tests/test_core.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: existing `Memory.relations` JSON (`{"type": ..., "target": ...}` entries), existing `MemoryRepository.get_by_source` from Task 5.
- Produces: `MemoryRepository.find_relation_sources(relation_type: str, target_id: str) -> list[Memory]`. `MemoryService.search`/`search_global`/`_search` gain `include_linked: bool = False`. Results from a linked source are tagged `"via_link": True`; native results have `"via_link": False`.
- Convention: to link a doc chunk to project `X`, call `memory_link(chunk_memory_id, "relates_to_project", X_overview_doc_memory_id)` — the target is project `X`'s own overview/core document memory id (obtainable via `memory_get_document(slug=X)`), not a bare project string. This reuses the existing per-project convention that a project's overview doc has `slug == project`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_find_relation_sources(service):
    v = [0.1] * 768
    target_id = service.set_document(v, "proj overview", "proj", "proj", "overview")
    doc_id = service.add_memory(v, "a linked doc chunk", "docs/general", "document")
    service.link_memories(doc_id, "relates_to_project", target_id)
    unrelated_id = service.add_memory(v, "unrelated", "docs/general", "document")

    matches = service.repository.find_relation_sources("relates_to_project", target_id)
    assert [m.id for m in matches] == [doc_id]


def test_search_include_linked_pulls_linked_docs(service):
    v = [0.1] * 768
    target_id = service.set_document(v, "proj overview", "proj", "proj", "overview")
    doc_id = service.add_memory(v, "azure runbook contents", "docs/azure", "document")
    service.link_memories(doc_id, "relates_to_project", target_id)

    without_link = service.search(v, "proj", query_text="runbook", include_linked=False)
    assert all(r["id"] != doc_id for r in without_link)

    with_link = service.search(v, "proj", query_text="runbook", include_linked=True)
    linked_hit = next(r for r in with_link if r["id"] == doc_id)
    assert linked_hit["via_link"] is True


def test_search_include_linked_no_link_matches_default(service):
    v = [0.1] * 768
    service.set_document(v, "proj overview", "proj", "proj", "overview")
    default = service.search(v, "proj", query_text="anything", include_linked=False)
    with_flag = service.search(v, "proj", query_text="anything", include_linked=True)
    assert [r["id"] for r in default] == [r["id"] for r in with_flag]
```

```python
# tests/test_server.py
def test_memory_link_accepts_relates_to_project(server, service):
    v = [0.1] * 768
    target_id = service.set_document(v, "overview", "chronicle-test", "chronicle-test", "overview")
    doc_id = service.add_memory(v, "doc", "docs/general", "document")
    result = server.memory_link.fn(
        source_id=doc_id, relation_type="relates_to_project", target_id=target_id
    )
    assert result["relation_type"] == "relates_to_project"


def test_memory_search_include_linked_param(server, service):
    v = [0.1] * 768
    target_id = service.set_document(v, "overview", "chronicle-test", "chronicle-test", "overview")
    doc_id = service.add_memory(v, "widget spec details", "docs/general", "document")
    service.link_memories(doc_id, "relates_to_project", target_id)
    results = server.memory_search.fn(query="widget", include_linked=True)
    assert any(r["id"] == doc_id for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k "relation_sources or include_linked or relates_to_project" -v`
Expected: FAIL

- [ ] **Step 3: Add the relation type**

In `src/chronicle/config.py`, line 13:

```python
VALID_RELATION_TYPES = frozenset({"related_to", "supersedes", "caused_by", "blocked_by", "implements", "relates_to_project"})
```

- [ ] **Step 4: Implement `find_relation_sources`**

In `src/chronicle/core/repository.py`, add after `link`:

```python
    def find_relation_sources(self, relation_type: str, target_id: str) -> list[Memory]:
        with self.session_factory() as session:
            candidates = session.scalars(
                select(Memory).where(Memory.relations.isnot(None))
            ).all()
            return [
                row
                for row in candidates
                if any(
                    relation.get("type") == relation_type and relation.get("target") == target_id
                    for relation in (row.relations or [])
                )
            ]
```

- [ ] **Step 5: Implement `include_linked` in the service**

In `src/chronicle/core/service.py`, update `_search`, `search`, `search_global` signatures to add `include_linked: bool = False`, and inside `_search`, after the neighbor-bundling block from Task 7 and before the `max_tokens` handling:

```python
        for item in results:
            item["via_link"] = False
        if include_linked and project is not None:
            doc = self.repository.get_document(project, project)
            if doc is not None:
                linked_sources = self.repository.find_relation_sources("relates_to_project", doc.id)
                seen = {item["id"] for item in results}
                for linked in linked_sources:
                    for sibling in self.repository.get_by_source(linked.source_id):
                        if sibling.id in seen or sibling.status in HIDDEN_STATUSES:
                            continue
                        serialized = self._serialize(sibling)
                        serialized["context"] = []
                        serialized["via_link"] = True
                        results.append(serialized)
                        seen.add(sibling.id)
```

Update `search`/`search_global` to accept and forward `include_linked` to `_search`.

- [ ] **Step 6: Update the MCP tools**

In `src/chronicle/server.py`, add `include_linked: bool = False` to `memory_search` and `memory_search_global`, forwarding it to `_get_service().search(...)`/`.search_global(...)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py tests/test_server.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicle/config.py src/chronicle/core/repository.py src/chronicle/core/service.py src/chronicle/server.py tests/test_core.py tests/test_server.py
git commit -m "feat: add relates_to_project linking and include_linked search"
```

---

### Task 9: Dashboard graph data contract — scope nodes

**Files:**
- Modify: `src/chronicle/core/service.py` (add `list_scope_graph_nodes` or extend `list_scopes`)
- Modify: `src/chronicle/server.py` (`memory_dashboard_graph`, line ~282)
- Test: `tests/test_server.py`, `tests/test_graph_cli.py` if `_build_graph_data` itself changes

**Interfaces:**
- Produces: `memory_dashboard_graph` response gains a top-level `"scopes"` key: `list[dict]` with `{"path": str, "name": str, "parent_path": str | None, "child_count": int, "core_present": bool, "linked_doc_count": int}`. This is the data contract the dashboard-visualization plan consumes — do not change the shape of the existing `"nodes"`/`"edges"` keys.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
def test_memory_dashboard_graph_includes_scopes(server, service):
    v = [0.1] * 768
    target_id = service.set_document(v, "azure core", "work/azure", "work/azure", "overview")
    service.add_memory(v, "unrelated memory", "chronicle-test", "note")
    service.repository.get_or_create_scope("work/azure/vm_config")

    result = server.memory_dashboard_graph.fn(project="chronicle-test")
    assert "scopes" in result
    paths = {s["path"] for s in result["scopes"]}
    assert {"work", "work/azure", "work/azure/vm_config", "chronicle-test"} <= paths
    azure = next(s for s in result["scopes"] if s["path"] == "work/azure")
    assert azure["core_present"] is True
    assert azure["child_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_server.py -k dashboard_graph_includes_scopes -v`
Expected: FAIL — `KeyError: 'scopes'`

- [ ] **Step 3: Implement scope-graph-node building in the service**

In `src/chronicle/core/service.py`, add:

```python
    def scope_graph_nodes(self) -> list[dict]:
        scopes = self.repository.list_scopes("")
        nodes = []
        for scope in scopes:
            core = self.repository.get_document(scope.path, scope.path)
            linked_count = 0
            if core is not None:
                linked_count = len(self.repository.find_relation_sources("relates_to_project", core.id))
            nodes.append(
                {
                    "path": scope.path,
                    "name": scope.name,
                    "parent_path": scope.path.rsplit("/", 1)[0] if "/" in scope.path else None,
                    "child_count": self.repository.child_scope_count(scope.id),
                    "core_present": core is not None,
                    "linked_doc_count": linked_count,
                }
            )
        return nodes
```

Note: registered projects that have never had `get_or_create_scope`/`memory_set_document(scope_path=...)` called on them only exist as `Memory.project` string values, not `Scope` rows, until Task 1's migration backfill or first use. `list_scopes("")` only sees rows in the `scope` table, so a project created after this feature ships but never explicitly scoped won't appear here — this is acceptable per the spec's migration section (scope rows are created lazily via `get_or_create_scope`, called by `memory_set_document`/`memory_add`'s existing project resolution path... note this plan does NOT wire `memory_add`/`memory_set_document`-without-scope_path to auto-create scope rows for bare projects, so **add that wiring now**: in `MemoryService.add_memory` and `set_document`, after resolving `project`, call `self.repository.get_or_create_scope(project)` unconditionally so every project a memory is ever written to has a corresponding scope row. Add this one line near the top of both methods, right after `project = _require_project(project)`.

- [ ] **Step 4: Wire scope auto-creation into `add_memory` and `set_document`**

In `src/chronicle/core/service.py`, in `add_memory` (after `project = _require_project(project)`):
```python
        self.repository.get_or_create_scope(project)
```
Same line in `set_document` after its `project = _require_project(project)`.

- [ ] **Step 5: Wire into `memory_dashboard_graph`**

In `src/chronicle/server.py`:

```python
@mcp.tool
def memory_dashboard_graph(
    project: str | None = None,
    cross_project: bool = False,
    k: int = graph_cli.K_NEIGHBORS,
    min_similarity: float = graph_cli.MIN_SIMILARITY,
) -> dict:
    records = _get_service().get_all_with_vectors(project=project)
    graph = graph_cli._build_graph_data(
        records,
        k=k,
        cross_project=cross_project,
        min_similarity=min_similarity,
        current_project=project,
    )
    graph["scopes"] = _get_service().scope_graph_nodes()
    return graph
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_server.py -k dashboard_graph_includes_scopes -v`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — this is the last backend task, confirm the full 164+ test count still passes.

- [ ] **Step 8: Commit**

```bash
git add src/chronicle/core/service.py src/chronicle/server.py tests/test_server.py
git commit -m "feat: emit scope nodes in memory_dashboard_graph"
```

---

### Task 10: Scope reparenting

**Note on the spec:** Section 3 of the design spec describes reparenting as "dashboard-only, not an agent-facing MCP tool," implying a separate transport. Checking `dashboard/src/api/rpc.ts` shows the dashboard has no such separate channel — every dashboard action, including the existing inline core editor, goes through the same MCP `tools/call` protocol (`callTool` in `rpc.ts`). There is no non-MCP backend surface to add this to. This task implements reparenting as an MCP tool like everything else, and preserves the spec's intent (curation, not autonomous agent action) the same way the existing server instructions already do for other human-curation actions — via the tool description telling an agent-caller not to invoke it unprompted, not via a transport boundary that doesn't exist in this codebase.

**Files:**
- Modify: `src/chronicle/core/repository.py` (add `reparent_scope`)
- Modify: `src/chronicle/core/service.py` (add `reparent_scope`)
- Modify: `src/chronicle/server.py` (add `memory_scope_reparent` tool + update the `mcp.tool`'s instructions string)
- Test: `tests/test_core.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Scope` model, `get_or_create_scope`, `get_scope_by_path` from Task 2.
- Produces: `MemoryRepository.reparent_scope(path: str, new_parent_path: str | None) -> Scope` — moves the scope at `path` (and updates the `path` of every descendant) under `new_parent_path` (or to root if `None`). `MemoryService.reparent_scope(path, new_parent_path)`. MCP tool `memory_scope_reparent(path: str, new_parent_path: str | None = None) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
def test_reparent_scope_moves_node_and_updates_path(service):
    repo = service.repository
    repo.get_or_create_scope("chronicle")
    repo.get_or_create_scope("work")

    moved = repo.reparent_scope("chronicle", "work")
    assert moved.path == "work/chronicle"
    assert repo.get_scope_by_path("chronicle") is None
    assert repo.get_scope_by_path("work/chronicle") is not None


def test_reparent_scope_updates_descendant_paths(service):
    repo = service.repository
    repo.get_or_create_scope("azure/vm_config")
    repo.get_or_create_scope("work")

    repo.reparent_scope("azure", "work")
    assert repo.get_scope_by_path("work/azure") is not None
    assert repo.get_scope_by_path("work/azure/vm_config") is not None
    assert repo.get_scope_by_path("azure/vm_config") is None


def test_reparent_scope_to_root(service):
    repo = service.repository
    repo.get_or_create_scope("work/chronicle")
    moved = repo.reparent_scope("work/chronicle", None)
    assert moved.path == "chronicle"
    assert moved.parent_id is None


def test_reparent_scope_rejects_moving_under_own_descendant(service):
    repo = service.repository
    repo.get_or_create_scope("work/azure")
    with pytest.raises(ValueError):
        repo.reparent_scope("work", "work/azure")
```

Add `import pytest` at the top of `tests/test_core.py` if not already present (check the file first).

```python
# tests/test_server.py
def test_memory_scope_reparent_tool(server, service):
    service.repository.get_or_create_scope("chronicle")
    service.repository.get_or_create_scope("work")
    result = server.memory_scope_reparent.fn(path="chronicle", new_parent_path="work")
    assert result["path"] == "work/chronicle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k reparent -v`
Expected: FAIL

- [ ] **Step 3: Implement `reparent_scope` in the repository**

In `src/chronicle/core/repository.py`, add after `child_scope_count`:

```python
    def reparent_scope(self, path: str, new_parent_path: str | None) -> Scope:
        with self.session_factory() as session:
            scope_row = session.scalar(select(Scope).where(Scope.path == path))
            if scope_row is None:
                raise ValueError(f"no scope found at path {path!r}")

            new_parent_id = None
            new_prefix = ""
            if new_parent_path is not None:
                if new_parent_path == path or new_parent_path.startswith(f"{path}/"):
                    raise ValueError("cannot move a scope under its own descendant")
                parent_row = session.scalar(select(Scope).where(Scope.path == new_parent_path))
                if parent_row is None:
                    raise ValueError(f"no scope found at path {new_parent_path!r}")
                new_parent_id = parent_row.id
                new_prefix = new_parent_path

            old_path = scope_row.path
            new_path = f"{new_prefix}/{scope_row.name}" if new_prefix else scope_row.name
            scope_row.parent_id = new_parent_id
            scope_row.path = new_path
            session.flush()

            descendants = session.scalars(
                select(Scope).where(Scope.path.like(f"{old_path}/%"))
            ).all()
            for descendant in descendants:
                descendant.path = new_path + descendant.path[len(old_path):]

            session.commit()
            return scope_row
```

- [ ] **Step 4: Implement service + tool**

In `src/chronicle/core/service.py`:

```python
    def reparent_scope(self, path: str, new_parent_path: str | None) -> dict:
        scope = self.repository.reparent_scope(path, new_parent_path)
        return {"path": scope.path, "name": scope.name}
```

In `src/chronicle/server.py`:

```python
@mcp.tool
def memory_scope_reparent(path: str, new_parent_path: str | None = None) -> dict:
    """Move a scope (and its descendants) under a different parent, or to
    root if new_parent_path is omitted. This reorganizes the user's own
    taxonomy — call it only when the user explicitly asks to reorganize or
    re-file something, never as a side effect of another task."""
    return _get_service().reparent_scope(path, new_parent_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_core.py tests/test_server.py -k reparent -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicle/core/repository.py src/chronicle/core/service.py src/chronicle/server.py tests/test_core.py tests/test_server.py
git commit -m "feat: add memory_scope_reparent for taxonomy reorganization"
```

---

## Handoff notes for the dashboard-visualization plan

`memory_dashboard_graph` now returns `{"nodes": [...], "edges": [...], "k": int, "current_project": str | None, "scopes": [{"path", "name", "parent_path", "child_count", "core_present", "linked_doc_count"}]}`. The dashboard-visualization plan (`docs/superpowers/plans/2026-09-26-scope-dashboard-visualization.md`) starts from this contract on the frontend side. `memory_scope_reparent(path, new_parent_path)` (Task 10) is also available for that plan to wire a "move this scope" control to — it is a normal MCP tool, called the same way `rpc.ts` already calls every other tool.
