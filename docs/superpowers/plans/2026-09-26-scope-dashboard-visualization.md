# Scope Dashboard Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the scope hierarchy in the existing 3D dashboard graph as recursive black-hole/orbit clusters — every scope with children is a black hole; its children (sub-scopes or projects) orbit it — reusing the existing `@react-three/fiber` "Chart Room" scene rather than building new rendering infrastructure.

**Architecture:** The backend already emits a `scopes` array on `memory_dashboard_graph` (see prerequisite below). This plan adds a TypeScript type for it, a new render layer in `GraphScene.tsx` that positions scope nodes recursively by `parent_path` depth and renders "has children" nodes distinctly from leaves, and a click-to-drill interaction reusing the existing detail-panel/camera pattern.

**Tech Stack:** React 19, TypeScript, `@react-three/fiber`, `@react-three/drei`, `three`.

**Spec:** `docs/superpowers/specs/2026-09-26-hierarchical-scope-and-docs-design.md` (Section 5)

**Prerequisite:** `docs/superpowers/plans/2026-09-26-hierarchical-scope-backend.md` must be merged first — this plan consumes the `scopes` field on `memory_dashboard_graph`'s response, which that plan adds.

## Global Constraints

- No new rendering library or 3D framework — extend the existing `@react-three/fiber` scene in `dashboard/src/components/GraphScene.tsx`.
- Exact visual treatment (shaders, exact colors, sizing curve, bloom parameters) is an implementation-time design call — this plan specifies the data contract and interaction, not pixels. Follow the existing "Chart Room" star-chart aesthetic (dark space theme, brass/nebula accents) already established in this file rather than introducing a new visual language.
- No backend changes — if this plan seems to need one, stop and check whether the backend plan's contract already covers it before modifying `src/chronicle/`.
- 3D rendering in this codebase is verified manually (`chronicle dashboard start` + visual inspection), not via unit tests — there is no existing test coverage for `GraphScene.tsx` today; this plan does not introduce a testing framework for it either. Each task's "test" step is a manual verification checklist instead of an automated test.

## Review Focus

- **A scope with zero children and zero memories** (a freshly created organizational node, e.g. `work` created only because `work/azure` needed an ancestor) — must still render as *something* selectable, not silently vanish from the scene.
- **A project scope that is also a parent** (e.g. if a user later reparents `chronicle` under `work/tools`) — must render with both behaviors: it's a black hole for its own children AND still shows its own memories on drill-in, not one or the other.
- **`linked_doc_count > 0` on a scope with no children** — the connecting thread to a linked doc must render even for a leaf project, not only for scopes with sub-scopes.
- **Very deep nesting** (4+ levels) — orbit radii must not visually collapse into an unreadable cluster; verify the recursive sizing formula still separates levels at depth 4.
- **A scope path containing characters that need escaping in a DOM `key`/Three.js object name** — project/scope names are free text; verify a name with a space or slash-adjacent character doesn't crash the scene (use `path`, which is already unique, as the React key — never `name` alone).

---

### Task 1: TypeScript types for scope nodes

**Files:**
- Modify: `dashboard/src/types.ts` (after `GraphData`, line ~52)

**Interfaces:**
- Produces: `ScopeNode` interface, `GraphData.scopes: ScopeNode[]`.

- [ ] **Step 1: Add the type**

In `dashboard/src/types.ts`, after the `GraphData` interface:

```typescript
export interface ScopeNode {
  path: string;
  name: string;
  parent_path: string | null;
  child_count: number;
  core_present: boolean;
  linked_doc_count: number;
}
```

Update `GraphData` to include it:

```typescript
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  k: number;
  current_project?: string | null;
  scopes: ScopeNode[];
}
```

- [ ] **Step 2: Verify the type checks**

Run: `cd dashboard && npm run build`
Expected: TypeScript compiles with no new errors (existing consumers of `GraphData` that don't reference `.scopes` are unaffected since it's an additive field).

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/types.ts
git commit -m "feat(dashboard): add ScopeNode type for scope hierarchy data"
```

---

### Task 2: Recursive scope layout

**Files:**
- Modify: `dashboard/src/components/GraphScene.tsx` (`useLayout`, line ~40, and the module-level layout helpers above it)

**Interfaces:**
- Consumes: `ScopeNode[]` from Task 1.
- Produces: a new hook `useScopeLayout(scopes: ScopeNode[]): Map<string, { position: THREE.Vector3; isBlackHole: boolean; radius: number }>` — computed once per scopes array, keyed by `path`.

- [ ] **Step 1: Implement the layout hook**

In `dashboard/src/components/GraphScene.tsx`, add near the existing `useLayout` hook:

```typescript
function scopeDepth(path: string): number {
  return path.split("/").length - 1;
}

function useScopeLayout(scopes: ScopeNode[]) {
  return useMemo(() => {
    const byParent = new Map<string | null, ScopeNode[]>();
    scopes.forEach((scope) => {
      const list = byParent.get(scope.parent_path);
      if (list) list.push(scope);
      else byParent.set(scope.parent_path, [scope]);
    });

    const positions = new Map<string, { position: THREE.Vector3; isBlackHole: boolean; radius: number }>();

    function place(parentPath: string | null, center: THREE.Vector3, depth: number) {
      const children = (byParent.get(parentPath) || []).sort((a, b) => a.path.localeCompare(b.path));
      const orbitRadius = 3 + depth * 2.2;
      children.forEach((scope, index) => {
        const position = fibonacciPoint(index, Math.max(children.length, 1), orbitRadius).add(center);
        const isBlackHole = scope.child_count > 0;
        const radius = isBlackHole ? 0.6 + Math.sqrt(scope.child_count) * 0.25 : 0.35;
        positions.set(scope.path, { position, isBlackHole, radius });
        if (isBlackHole) place(scope.path, position, depth + 1);
      });
    }

    place(null, new THREE.Vector3(0, 0, 0), 0);
    return positions;
  }, [scopes]);
}
```

This reuses the existing `fibonacciPoint` helper already defined above `useLayout` for even angular distribution, and recurses by depth exactly as Section 5 of the spec specifies — no new distribution algorithm needed. A zero-children, zero-memory organizational scope (Review Focus item 1) still gets a `positions` entry from this loop since it iterates every scope in `byParent`, regardless of memory count.

- [ ] **Step 2: Manual verification**

Run: `cd dashboard && npm run dev`, open the dashboard, open the browser devtools console, and temporarily log `positions.size` vs `scopes.length` from `useScopeLayout` (remove the log before committing). Confirm every scope from the API response gets a position, including ones with `child_count: 0` and no associated memories.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/GraphScene.tsx
git commit -m "feat(dashboard): compute recursive scope layout"
```

---

### Task 3: Render scope nodes as black holes / orbit markers

**Files:**
- Modify: `dashboard/src/components/GraphScene.tsx` (main scene component, wherever `LayoutNode`s are currently mapped to meshes)

**Interfaces:**
- Consumes: `useScopeLayout` from Task 2.
- Produces: a `ScopeBody` sub-component rendered once per scope, visually distinct for `isBlackHole: true` (parent) vs `false` (leaf awaiting its existing project-galaxy treatment).

- [ ] **Step 1: Add the `ScopeBody` component**

In `dashboard/src/components/GraphScene.tsx`, add a component (near the other small presentational components in this file — check for an existing pattern like a `Node` or `Star` component to match its prop/style conventions):

```typescript
function ScopeBody({
  scope,
  position,
  radius,
  isBlackHole,
  onSelect,
}: {
  scope: ScopeNode;
  position: THREE.Vector3;
  radius: number;
  isBlackHole: boolean;
  onSelect: (path: string) => void;
}) {
  return (
    <group position={position}>
      <mesh onClick={() => onSelect(scope.path)}>
        <sphereGeometry args={[radius, 24, 24]} />
        <meshStandardMaterial
          color={isBlackHole ? "#0a0a12" : "#3a3550"}
          emissive={scope.core_present ? BRASS : "#000000"}
          emissiveIntensity={scope.core_present ? 0.25 : 0}
        />
      </mesh>
      {isBlackHole && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius * 1.3, radius * 1.6, 48]} />
          <meshBasicMaterial color={BRASS} transparent opacity={0.35} side={THREE.DoubleSide} />
        </mesh>
      )}
      <Html distanceFactor={12} center>
        <div style={{ color: "#cfd6e6", fontSize: 11, whiteSpace: "nowrap" }}>{scope.name}</div>
      </Html>
    </group>
  );
}
```

Import `ScopeNode` from `../types` at the top of the file.

- [ ] **Step 2: Wire it into the scene**

In the main scene component, call `useScopeLayout(graphData.scopes)` and render one `ScopeBody` per entry, passing an `onSelect` callback that will be wired to the drill-down state in Task 4. Place this rendering alongside (not replacing) the existing per-project galaxy rendering — projects continue to render their existing memory-node galaxy at their scope's computed position, so a leaf project scope shows both its `ScopeBody` marker and its existing memory-node cluster centered on the same position.

- [ ] **Step 3: Manual verification**

Run: `cd dashboard && npm run dev`, open the dashboard. Confirm:
- Every scope from Task 2's layout renders a sphere.
- Scopes with `child_count > 0` show the ring (Review Focus: verify this holds even at depth 4+ — nest a few test scopes via `memory_set_document(scope_path=...)` in a scratch project to check).
- A scope with `core_present: true` shows the brass emissive glow.
- No console errors from duplicate React keys (use `scope.path` as the `key` prop when mapping, per Review Focus item 5).
- A scope that is both a registered project AND a parent (reparent an existing project under a new scope via `memory_scope_reparent` in a scratch project to test this) renders its black-hole/ring treatment for its children AND still shows its own existing memory-node galaxy — neither behavior suppresses the other (Review Focus item 2).

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/GraphScene.tsx
git commit -m "feat(dashboard): render scope hierarchy as black holes and orbit markers"
```

---

### Task 4: Linked-doc connecting threads + click-to-drill

**Files:**
- Modify: `dashboard/src/components/GraphScene.tsx`
- Modify: `dashboard/src/App.tsx` (detail-panel/selection state, check existing pattern around line ~50-100 for how project selection currently drives the detail panel)

**Interfaces:**
- Consumes: `ScopeNode.linked_doc_count`, `onSelect` callback from Task 3.
- Produces: a faint line between a scope with `linked_doc_count > 0` and the project scope(s) it's linked to (requires knowing *which* project — if the backend contract doesn't expose the specific linked project path per scope, draw the thread from the doc scope to its own position pulsing outward rather than to a specific unresolvable target; do not block this task on a backend change).

- [ ] **Step 1: Check what the backend actually exposes**

`memory_dashboard_graph`'s `scopes[].linked_doc_count` (from the backend plan) is a count, not a list of target paths. Before drawing a specific connecting thread, confirm whether this is sufficient. It is not enough to draw a thread to a *specific* project — only to show that a link exists. Two options:
  - **(a)** Ship a visible badge/indicator on scopes with `linked_doc_count > 0` (e.g. a small secondary glow ring) without a specific connecting thread, deferring the specific-target thread until the backend exposes linked target paths.
  - **(b)** Go back to the backend plan and add the target path(s) to the contract.

Recommendation: ship (a) now — it satisfies "linkage is visible without leaving the map" from the spec without a backend round-trip, and is honest about what data exists. Do not implement a thread to a guessed or arbitrary target.

- [ ] **Step 2: Implement the linked-doc indicator**

In `ScopeBody` (Task 3), add a small secondary ring when `scope.linked_doc_count > 0`:

```typescript
      {scope.linked_doc_count > 0 && (
        <mesh rotation={[Math.PI / 3, Math.PI / 6, 0]}>
          <ringGeometry args={[radius * 1.8, radius * 1.9, 32]} />
          <meshBasicMaterial color={SEMANTIC} transparent opacity={0.5} side={THREE.DoubleSide} />
        </mesh>
      )}
```

- [ ] **Step 3: Implement click-to-drill**

In `App.tsx`, find the existing state that tracks the selected project / detail panel (check how clicking an existing memory node currently opens its detail view — reuse the identical pattern). Add a `selectedScopePath: string | null` state; `ScopeBody`'s `onSelect` sets it. When set, the camera/scene should focus on that scope's children (filter the rendered scope set to descendants of `selectedScopePath`, same filtering idea already used for per-project focus) and the detail panel shows the scope's core doc (fetch via `memory_get_document(slug=path, scope_path=path)` through the existing `dashboard/src/api/rpc.ts` client — check its existing method-calling convention and add a matching one) with the existing inline core editor reused unchanged.

- [ ] **Step 4: Manual verification**

Run: `cd dashboard && npm run dev`. Confirm:
- A scope with `linked_doc_count > 0` shows the secondary ring — including a leaf project scope with zero children (link a doc to a childless project via `memory_link`/`relates_to_project` to test this specifically; the ring must not be gated on `isBlackHole`, per Review Focus item 3).
- Clicking a black hole scope narrows the scene to its children and opens its core doc in the existing detail panel, editable inline.
- Clicking a leaf project scope still shows its existing memory graph/provenance behavior, unchanged from today.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/GraphScene.tsx dashboard/src/App.tsx
git commit -m "feat(dashboard): add linked-doc indicator and scope drill-down"
```

---

### Task 5: Reparent control in the detail panel

**Files:**
- Modify: `dashboard/src/App.tsx` (detail panel, wherever the existing core editor for a selected scope is rendered — added in Task 4)

**Interfaces:**
- Consumes: `memory_scope_reparent(path, new_parent_path)` MCP tool from the backend plan's Task 10, called via the existing `callTool` helper in `dashboard/src/api/rpc.ts`.

- [ ] **Step 1: Add a "Move to..." control**

In the detail panel shown when a scope is selected (Task 4), add a small text input plus button: "Move under:" with a text field for a parent path (empty = move to root) and a "Move" button that calls:

```typescript
await callTool("memory_scope_reparent", { path: selectedScopePath, new_parent_path: newParentInput || null });
```

On success, refetch the graph data (reuse whatever refetch function already runs after the existing core-editor save, in Task 4) so the scene reflects the new position immediately.

- [ ] **Step 2: Manual verification**

Run: `cd dashboard && npm run dev`. Select a scope, enter a new parent path, click Move, confirm the scene re-renders with the scope (and its children) now orbiting the new parent, and that a scope with descendants still carries them along (backend Task 10's `reparent_scope` already updates descendant paths — verify the frontend correctly re-derives their new positions from the refetched `scopes` array rather than caching stale ones).

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/App.tsx
git commit -m "feat(dashboard): add scope reparent control to detail panel"
```

---

## Follow-up not in this plan

- Drawing a connecting thread to the *specific* linked project (deferred in Task 4, Step 1) — needs a backend contract change (expose linked target paths, not just a count) and should go through its own brainstorming pass if wanted, not be bolted on here.
- Exact shader/bloom polish on the black-hole visual — this plan ships a functional, distinguishable render; further visual refinement is a design pass, not a functional requirement.
