import { useEffect, useMemo, useState, type ReactNode } from "react";

import { callTool } from "./api/rpc";
import { GraphScene } from "./components/GraphScene";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardHeader } from "./components/ui/card";
import { Checkbox } from "./components/ui/checkbox";
import { Input } from "./components/ui/input";
import { ScrollArea } from "./components/ui/scroll-area";
import { colorForType, TYPE_COLORS, type DashboardSnapshot, type GraphEdge, type GraphNode, type ProjectCard } from "./types";

type Tab = "graph" | "projects" | "control";
const STATUS_COLORS = { active: "#f2d68f", resolved: "#9ba8bd", superseded: "#667187", wrong: "#667187" };

function readRoute(): { tab: Tab; project: string | null } {
  const params = new URLSearchParams(window.location.search);
  const rawTab = params.get("tab");
  return { tab: rawTab === "projects" || rawTab === "control" ? rawTab : "graph", project: params.get("project") };
}

function navigate(tab: Tab, project: string | null = null) {
  const params = new URLSearchParams({ tab });
  if (project) params.set("project", project);
  window.history.pushState({}, "", `${window.location.pathname}?${params}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function truncate(value: string, length = 150) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function GraphLegend({ query, onQueryChange, onSearch, searching, results, showSemanticEdges, onSemanticToggle }: { query: string; onQueryChange: (value: string) => void; onSearch: () => void; searching: boolean; results: GraphNode[]; showSemanticEdges: boolean; onSemanticToggle: (checked: boolean) => void }) {
  return <div className="chart-plate graph-legend" aria-label="Graph legend">
    <div className="plate-label">chart key</div>
    <div className="legend-section"><span className="legend-heading">status</span>{Object.entries(STATUS_COLORS).map(([status, color]) => <span className="legend-item" key={status}><i className="legend-star" style={{ backgroundColor: color, boxShadow: `0 0 10px ${color}` }} />{status}</span>)}</div>
    <div className="legend-section"><span className="legend-heading">links</span><span className="legend-item"><Checkbox checked={showSemanticEdges} onCheckedChange={(checked) => onSemanticToggle(checked === true)} aria-label="Show semantic similarity edges" /><i className="legend-line semantic-line" />semantic similarity</span><span className="legend-item"><i className="legend-line explicit-line" />typed relation / direction</span></div>
    <div className="legend-section"><span className="legend-heading">memory taxonomy</span><TypeStrip /></div>
    <div className="graph-search"><Input value={query} onChange={(event) => onQueryChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") onSearch(); }} placeholder="search memories" aria-label="Search memories" /><Button onClick={onSearch} disabled={searching}>{searching ? "..." : "Find"}</Button></div>
    {results.length > 0 && <div className="search-results">{results.map((result) => <div key={result.id} className="search-result"><span>{result.project}</span>{truncate(result.content, 100)}</div>)}</div>}
  </div>;
}

function TypeStrip() {
  return <div className="type-strip" aria-label="Memory types">{Object.entries(TYPE_COLORS).map(([type, color]) => <span key={type} className="type-mark" style={{ color }}><i style={{ backgroundColor: color }} />{type}</span>)}</div>;
}

function GraphTab({ snapshot, project, selectedId, onSelect }: { snapshot: DashboardSnapshot; project: string | null; selectedId: string | null; onSelect: (node: GraphNode) => void }) {
  const nodes = useMemo(() => project ? snapshot.graph.nodes.filter((node) => node.project === project) : snapshot.graph.nodes, [project, snapshot.graph.nodes]);
  const ids = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);
  const edges = useMemo(() => snapshot.graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)), [ids, snapshot.graph.edges]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSemanticEdges, setShowSemanticEdges] = useState(true);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    try { setResults(await callTool<GraphNode[]>("memory_search_global", { query, k: 8 }) || []); } finally { setSearching(false); }
  }

  return <section className="graph-workspace" aria-label="Memory graph">
    <div className="graph-canvas"><GraphScene nodes={nodes} edges={edges} selectedId={selectedId} onSelect={onSelect} showSemanticEdges={showSemanticEdges} /></div>
    <GraphLegend query={query} onQueryChange={setQuery} onSearch={() => void search()} searching={searching} results={results} showSemanticEdges={showSemanticEdges} onSemanticToggle={setShowSemanticEdges} /><div className="graph-hint mono">drag / scroll to orbit · click star to focus</div>
  </section>;
}

function ProjectCardView({ project, onView }: { project: ProjectCard; onView: () => void }) {
  return <Card className="project-plate"><CardHeader><div className="project-title-row"><h2>{project.name}</h2><Badge>{project.node_count} stars</Badge></div><p className="project-path mono" title={project.paths[0]}>{project.paths[0] || "unregistered path"}</p></CardHeader><CardContent className="project-card-content"><div className="project-stats"><div><strong>{project.node_count.toLocaleString()}</strong><span className="mono">stars</span></div><div><strong>{project.edge_count.toLocaleString()}</strong><span className="mono">edges</span></div></div><div className="type-chips">{Object.entries(project.type_counts).map(([type, count]) => <span key={type} className="type-chip" style={{ color: colorForType(type), borderColor: `${colorForType(type)}55` }}><i style={{ backgroundColor: colorForType(type) }} />{type} <b>{count}</b></span>)}</div><Button className="view-graph-button" onClick={onView}>View graph <span aria-hidden="true">→</span></Button></CardContent></Card>;
}

function ProjectsTab({ snapshot, onView }: { snapshot: DashboardSnapshot; onView: (project: string) => void }) {
  return <ScrollArea className="data-page"><div className="page-heading"><div><h1>Projects in memory</h1><p>Chart plates summarize live memory counts. Select one to narrow graph without changing stored memories.</p></div><div className="page-total mono">{snapshot.projects.length.toString().padStart(2, "0")} projects</div></div><div className="project-grid">{snapshot.projects.map((project) => <ProjectCardView key={project.name} project={project} onView={() => onView(project.name)} />)}</div></ScrollArea>;
}

function ControlReadout({ label, value, tone = "" }: { label: string; value: ReactNode; tone?: string }) {
  return <div className="control-readout"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}

function ControlTab({ snapshot, onRefresh, refreshing }: { snapshot: DashboardSnapshot; onRefresh: () => void; refreshing: boolean }) {
  const { qdrant, docker, mnemo_processes } = snapshot.control;
  return <ScrollArea className="data-page"><div className="page-heading"><div><h1>Local control room</h1><p>Instrument readouts from Qdrant, Docker, and active <span className="mono">uv run mnemo</span> sessions.</p></div><Button variant="soft" onClick={onRefresh}>{refreshing ? "Sampling..." : "Refresh sample"}</Button></div><div className="control-grid"><Card className="control-plate"><CardHeader><h2>{qdrant.collection}</h2></CardHeader><CardContent><div className="readout-grid"><ControlReadout label="points" value={qdrant.point_count?.toLocaleString() ?? "—"} /><ControlReadout label="client check" value={qdrant.healthy ? "HEALTHY" : "OFFLINE"} tone={qdrant.healthy ? "good" : "bad"} /></div>{qdrant.error && <p className="control-note">{qdrant.error}</p>}</CardContent></Card><Card className="control-plate"><CardHeader><h2>{docker.name || "container not found"}</h2></CardHeader><CardContent><div className="readout-grid three"><ControlReadout label="health" value={docker.health} tone={docker.available ? "good" : "bad"} /><ControlReadout label="cpu" value={docker.cpu || "—"} /><ControlReadout label="memory" value={docker.memory || "—"} /></div></CardContent></Card></div><Card className="control-plate process-plate"><CardHeader><h2>Active <span className="mono">uv run mnemo</span> sessions</h2></CardHeader><CardContent>{mnemo_processes.length === 0 ? <p className="control-note">No matching process found, or process listing unavailable.</p> : <div className="process-list">{mnemo_processes.map((process) => <div key={process.pid} className="process-row"><span className="process-pid mono">PID {process.pid}</span><span className="mono">{process.cpu_percent}% CPU</span><span className="mono">{process.rss_kb.toLocaleString()} KB</span><span className="process-command mono">{process.command}</span></div>)}</div>}</CardContent></Card></ScrollArea>;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function CaseField({ label, value }: { label: string; value: string }) {
  return <div className="case-field"><span className="case-field-label">{label}</span><span className="case-field-value mono">{value}</span></div>;
}

function NodeReference({ label, targetId, node, onSelect, text }: { label: string; targetId: string; node?: GraphNode; onSelect: (node: GraphNode) => void; text: string }) {
  return <div className="case-reference"><span className="case-field-label">{label}</span>{node ? <Button variant="ghost" className="case-link" onClick={() => onSelect(node)} aria-label={`Open ${label} ${targetId}`}>{text} {truncate(targetId, 24)}</Button> : <span className="case-reference-missing mono">{text} {truncate(targetId, 24)} · not in current view</span>}</div>;
}

function MemoryCasePlate({ selected, snapshot, onSelect, onClose, onRefresh, onError }: { selected: GraphNode; snapshot: DashboardSnapshot; onSelect: (node: GraphNode) => void; onClose: () => void; onRefresh: () => Promise<DashboardSnapshot | null>; onError: (message: string) => void }) {
  const [action, setAction] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState(selected.content);
  const nodeById = useMemo(() => new Map(snapshot.graph.nodes.map((node) => [node.id, node])), [snapshot.graph.nodes]);
  const predecessor = selected.supersedes ? nodeById.get(selected.supersedes) : undefined;
  const successors = useMemo(() => snapshot.graph.nodes.filter((node) => node.supersedes === selected.id), [selected.id, snapshot.graph.nodes]);
  const hasConfidence = selected.confidence !== null && selected.confidence !== undefined;
  const hasProvenance = Boolean(selected.source || selected.episode_title || hasConfidence || selected.extraction_method);
  const hasTemporal = Boolean(selected.created_at || selected.valid_at || selected.invalid_at);

  useEffect(() => { setDraftContent(selected.content); }, [selected.id, selected.content]);

  async function runAction(tool: string, args: Record<string, unknown> = {}, closeAfter = false) {
    setAction(tool);
    try {
      await callTool(tool, { memory_id: selected.id, ...args });
      const refreshed = await onRefresh();
      if (closeAfter && refreshed) onClose();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Memory action failed");
    } finally {
      setAction(null);
    }
  }

  return <div className="selected-memory"><Card className="case-plate"><CardHeader className="case-head"><div className="case-header"><div><h2>{selected.type}</h2></div><button className="close-button" onClick={onClose} aria-label="Close selected memory">×</button></div><div className="case-meta mono">{selected.project} · {selected.status}</div></CardHeader><CardContent className="case-body"><div className="case-content">{selected.content}</div>{selected.slug && <div className="case-slug mono">slug: {selected.slug}</div>}<div className="case-sections">
    {hasProvenance && <section className="case-section"><div className="plate-label">provenance</div><div className="case-fields">{selected.source && <CaseField label="source" value={selected.source} />}{selected.episode_title && <CaseField label="episode" value={selected.episode_title} />}{hasConfidence && <CaseField label="confidence" value={selected.confidence!.toFixed(2)} />}{selected.extraction_method && <CaseField label="method" value={selected.extraction_method} />}</div></section>}
    {hasTemporal && <section className="case-section"><div className="plate-label">temporal</div><div className="case-fields">{selected.created_at && <CaseField label="created" value={formatTimestamp(selected.created_at) || selected.created_at} />}{selected.valid_at && <CaseField label="valid from" value={formatTimestamp(selected.valid_at) || selected.valid_at} />}{selected.invalid_at && <CaseField label="invalid at" value={formatTimestamp(selected.invalid_at) || selected.invalid_at} />}</div></section>}
    {(selected.supersedes || successors.length > 0) && <section className="case-section"><div className="plate-label">history</div><div className="case-fields">{selected.supersedes && <NodeReference label="predecessor" targetId={selected.supersedes} node={predecessor} onSelect={onSelect} text="superseded" />}{successors.map((node) => <NodeReference key={node.id} label="successor" targetId={node.id} node={node} onSelect={onSelect} text="replaced by" />)}</div></section>}
    {selected.relations && selected.relations.length > 0 && <section className="case-section"><div className="plate-label">relations</div><div className="case-fields">{selected.relations.map((relation, index) => <NodeReference key={`${relation.type}-${relation.target}-${index}`} label={relation.type} targetId={relation.target} node={nodeById.get(relation.target)} onSelect={onSelect} text="open" />)}</div></section>}
    {selected.role === "core" && <section className="case-section case-editor"><div className="plate-label">core editor</div><textarea className="case-editor-textarea" value={draftContent} onChange={(event) => setDraftContent(event.target.value)} aria-label="Core memory content" /><Button variant="solid" onClick={() => void runAction("memory_edit", { content: draftContent })} disabled={action !== null}>{action === "memory_edit" ? "Saving..." : "Save"}</Button></section>}
    <section className="case-section case-actions"><div className="plate-label">correction</div><div className="case-action-buttons"><Button variant="soft" onClick={() => void runAction("memory_confirm", { confidence: 1.0 })} disabled={action !== null}>{action === "memory_confirm" ? "Confirming..." : "Confirm"}</Button><Button variant="ghost" onClick={() => void runAction("memory_retract", {}, true)} disabled={action !== null}>{action === "memory_retract" ? "Retracting..." : "Retract"}</Button>{selected.status !== "superseded" && <Button variant="ghost" onClick={() => void runAction("memory_mark_wrong")} disabled={action !== null}>{action === "memory_mark_wrong" ? "Marking..." : "Mark wrong"}</Button>}</div></section>
  </div></CardContent></Card></div>;
}

export default function App() {
  const [route, setRoute] = useState(readRoute);
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function refresh(): Promise<DashboardSnapshot | null> {
    setRefreshing(true);
    setError(null);
    try {
      const next = await callTool<DashboardSnapshot>("memory_dashboard_snapshot");
      setSnapshot(next);
      setSelected((current) => current ? next.graph.nodes.find((node) => node.id === current.id) || current : current);
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Dashboard request failed");
      return null;
    } finally { setRefreshing(false); }
  }

  useEffect(() => { const onPopState = () => { setRoute(readRoute()); setSelected(null); }; window.addEventListener("popstate", onPopState); return () => window.removeEventListener("popstate", onPopState); }, []);
  useEffect(() => { void refresh(); }, []);

  return <main className="app-shell"><header className="topbar"><button className="brand" onClick={() => navigate("graph")} aria-label="Open all memory graph"><span className="brand-mark">✦</span><span>mnemo</span><small>memory field</small></button><nav className="tab-nav" aria-label="Dashboard sections">{(["graph", "projects", "control"] as Tab[]).map((tab) => <TabButton key={tab} active={route.tab === tab} onClick={() => navigate(tab, tab === "graph" ? route.project : null)}>{tab}<span>{tab === "graph" ? snapshot?.graph.nodes.length ?? "—" : tab === "projects" ? snapshot?.projects.length ?? "—" : ""}</span></TabButton>)}</nav><div className="endpoint-status"><i className={error ? "status-light bad" : "status-light"} />local / <span className="mono">127.0.0.1</span></div></header>{error && <div className="app-alert"><span><b>MCP unavailable:</b> {error}</span><Button variant="soft" onClick={() => void refresh()}>Retry</Button></div>}{!snapshot && !error && <div className="loading-state mono">loading memory field ...</div>}{snapshot && route.tab === "graph" && <GraphTab snapshot={snapshot} project={route.project} selectedId={selected?.id ?? null} onSelect={setSelected} />}{snapshot && route.tab === "projects" && <ProjectsTab snapshot={snapshot} onView={(project) => navigate("graph", project)} />}{snapshot && route.tab === "control" && <ControlTab snapshot={snapshot} onRefresh={() => void refresh()} refreshing={refreshing} />}{selected && snapshot && <MemoryCasePlate selected={selected} snapshot={snapshot} onSelect={setSelected} onClose={() => setSelected(null)} onRefresh={refresh} onError={setError} />}</main>;
}

function TabButton({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return <button className={`tab-button ${active ? "active" : ""}`} onClick={onClick}>{children}</button>;
}
