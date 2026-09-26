import argparse
import time
import webbrowser
from pathlib import Path

from chronicle import config
from chronicle.core.graph import (
    K_NEIGHBORS,
    MIN_SIMILARITY,
    build_graph_data as _build_graph_data,
    cosine as _cosine,
)
from chronicle.core.runtime import get_runtime

def _render_html(graph: dict) -> str:
    import json

    data_json = json.dumps(graph, ensure_ascii=False)
    return _TEMPLATE.replace("__DATA_JSON__", data_json)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle graph")
    parser.add_argument("--project", default=None)
    parser.add_argument("--all", action="store_true", help="graph every project together, not just one")
    parser.add_argument(
        "--cross-project",
        action="store_true",
        help="allow edges between memories in different projects (only meaningful with --all)",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=MIN_SIMILARITY,
        help=f"minimum cosine similarity required to draw an edge (default {MIN_SIMILARITY})",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if args.project and args.all:
        parser.error("--project and --all are mutually exclusive")

    project = None if args.all else (args.project or config.get_project())

    if project is not None:
        default_focus = project
    else:
        try:
            default_focus = config.get_project()
        except RuntimeError:
            default_focus = None

    records = get_runtime().get_all_with_vectors(project=project)

    if len(records) < 2:
        print("Need at least 2 memories to build a graph.")
        return

    graph = _build_graph_data(
        records,
        cross_project=args.cross_project,
        min_similarity=args.min_similarity,
        current_project=default_focus,
    )
    html = _render_html(graph)

    out_path = Path(args.out) if args.out else Path.cwd() / f"chronicle-graph-{int(time.time())}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Graph written to {out_path}")
    webbrowser.open(out_path.as_uri())


_TEMPLATE = r"""<meta charset="utf-8">
<title>Chronicle Graph</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Special+Elite&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
  :root {
    --bg: #0F0D0A;
    --panel: #1B1712;
    --ink: #E8DFC8;
    --ink-dim: #948A6C;
    --edge: rgba(232, 223, 200, 0.16);
    --edge-hi: rgba(232, 223, 200, 0.68);
    --stamp: #D2604E;
    --border: #332C22;
  }

  * { box-sizing: border-box; }

  html, body {
    margin: 0;
    height: 100%;
    background: radial-gradient(ellipse at 50% 45%, #1d1812 0%, var(--bg) 70%);
    color: var(--ink);
    font-family: "Source Serif 4", Georgia, serif;
    overflow: hidden;
  }

  .mono { font-family: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace; font-variant-numeric: tabular-nums; }
  .stamp-face { font-family: "Special Elite", "Courier New", monospace; }

  a, button { color: inherit; }
  button:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid var(--stamp);
    outline-offset: 2px;
  }

  #stage { position: fixed; inset: 0; display: block; cursor: grab; }
  #stage.dragging { cursor: grabbing; }

  header.hud {
    position: fixed;
    top: 0; left: 0; right: 0;
    padding: clamp(16px, 3vw, 30px) clamp(16px, 3vw, 34px) 0;
    pointer-events: none;
    z-index: 5;
  }

  .eyebrow {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--stamp);
    display: flex; align-items: center; gap: 9px;
    margin-bottom: 8px;
  }
  .eyebrow::before {
    content: ""; width: 6px; height: 6px; border-radius: 50%;
    background: var(--stamp);
    box-shadow: 0 0 0 3px rgba(210, 96, 78, 0.22);
  }

  h1.title {
    font-family: "Special Elite", "Courier New", monospace;
    font-weight: 400;
    font-size: clamp(1.5rem, 3.4vw, 2.1rem);
    margin: 0 0 6px;
    text-wrap: balance;
  }

  .sub {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
    color: var(--ink-dim);
  }

  .legend {
    position: fixed;
    bottom: clamp(16px, 3vw, 30px);
    left: clamp(16px, 3vw, 34px);
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.74rem;
    color: var(--ink-dim);
    z-index: 5;
    pointer-events: none;
  }
  .legend-row { display: flex; align-items: center; gap: 8px; }
  .legend-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }

  .hint {
    position: fixed;
    bottom: clamp(16px, 3vw, 30px);
    right: clamp(16px, 3vw, 34px);
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
    color: var(--ink-dim);
    z-index: 5;
    text-align: right;
    pointer-events: none;
  }

  .node-label {
    position: fixed;
    pointer-events: none;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
    color: var(--ink);
    background: rgba(15, 13, 10, 0.88);
    border: 1px solid var(--border);
    padding: 3px 8px;
    white-space: nowrap;
    transform: translate(-50%, -140%);
    z-index: 8;
    opacity: 0;
    transition: opacity 120ms ease;
  }
  .node-label.show { opacity: 1; }

  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: clamp(16px, 5vh, 64px) 16px;
    overflow-y: auto;
    z-index: 20;
  }
  .overlay[hidden] { display: none; }

  .case-file {
    background: var(--panel);
    border: 1px solid var(--border);
    max-width: 720px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  }
  .case-head {
    padding: 18px 22px 14px;
    border-bottom: 3px double var(--border);
    display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  }
  .case-project {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.76rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  .close-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--ink-dim);
    font-family: "JetBrains Mono", monospace;
    font-size: 0.74rem;
    padding: 6px 10px;
    cursor: pointer;
    flex: none;
  }
  .close-btn:hover { color: var(--ink); border-color: var(--ink-dim); }

  .case-body {
    padding: 20px 22px 6px;
    max-height: 60vh;
    overflow-y: auto;
    overflow-x: auto;
    line-height: 1.65;
    font-size: 0.98rem;
  }
  .case-body h2, .case-body h3, .case-body h4 { font-family: "Source Serif 4", serif; margin: 1em 0 0.4em; text-wrap: balance; }
  .case-body h2 { font-size: 1.25rem; }
  .case-body h3 { font-size: 1.05rem; color: var(--stamp); }
  .case-body p { margin: 0 0 0.85em; }
  .case-body ul { margin: 0 0 0.85em; padding-left: 1.3em; }
  .case-body li { margin-bottom: 0.3em; }
  .case-body hr { border: none; border-top: 1px solid var(--border); margin: 1.3em 0; }
  .case-body code { font-family: "JetBrains Mono", monospace; font-size: 0.85em; background: rgba(255,255,255,0.06); padding: 0.1em 0.35em; word-break: break-word; }
  .case-body strong { color: var(--stamp); }

  .case-foot {
    padding: 10px 22px 18px;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    color: var(--ink-dim);
    display: flex; flex-wrap: wrap; gap: 4px 16px;
  }

  .controls {
    position: fixed;
    top: clamp(16px, 3vw, 30px);
    right: clamp(16px, 3vw, 34px);
    display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
    z-index: 6;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.72rem;
  }
  .controls input[type=search] {
    background: rgba(27, 23, 18, 0.85);
    border: 1px solid var(--border);
    color: var(--ink);
    padding: 6px 10px;
    width: 220px;
    font: inherit;
  }
  .chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 360px; }
  .filter-row { display: flex; gap: 6px; justify-content: flex-end; align-items: center; flex-wrap: wrap; }
  .controls select, .controls input[type=date] {
    background: rgba(27, 23, 18, 0.85);
    border: 1px solid var(--border);
    color: var(--ink);
    padding: 5px 8px;
    font: inherit;
  }
  .controls input[type=range] { accent-color: var(--stamp); vertical-align: middle; }
  .chip {
    background: rgba(27, 23, 18, 0.85);
    border: 1px solid var(--border);
    color: var(--ink-dim);
    padding: 4px 9px;
    cursor: pointer;
    font: inherit;
    display: flex; align-items: center; gap: 6px;
  }
  .chip.active { color: var(--ink); border-color: var(--ink-dim); }
  .chip i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .keytoggle { color: var(--ink-dim); display: flex; align-items: center; gap: 6px; cursor: pointer; }

  @media (max-width: 640px) {
    .legend { display: none; }
    .hint { max-width: 46%; }
  }
</style>

<canvas id="stage"></canvas>

<header class="hud">
  <div class="eyebrow">Recalled from Qdrant · linked by meaning, not by hand</div>
  <h1 class="title">Chronicle Graph</h1>
  <div class="sub" id="stat-line"></div>
</header>

<div class="legend" id="legend"></div>
<div class="controls">
  <input type="search" id="q" placeholder="search memories…" aria-label="Search memories">
  <div class="chips" id="chips"></div>
  <div class="filter-row">
    <select id="typeFilter" aria-label="Filter by memory type"><option value="">all types</option></select>
    <select id="statusFilter" aria-label="Filter by status"><option value="">all statuses</option></select>
  </div>
  <div class="filter-row">
    <input type="date" id="dateFrom" aria-label="From date">
    <input type="date" id="dateTo" aria-label="To date">
  </div>
  <div class="filter-row">
    <label class="keytoggle">min sim <input type="range" id="simRange" min="0" max="1" step="0.05" value="0"> <span id="simValue" class="mono">0.00</span></label>
  </div>
  <div class="filter-row">
    <label class="keytoggle"><input type="checkbox" id="showSemantic" checked> semantic</label>
    <label class="keytoggle"><input type="checkbox" id="showExplicit" checked> explicit</label>
  </div>
  <label class="keytoggle"><input type="checkbox" id="keyOnly"> core + latest checkpoint only</label>
</div>
<div class="hint">drag to orbit · scroll to zoom · hover to trace · click to read</div>
<div class="node-label" id="node-label"></div>

<div class="overlay" id="overlay" hidden>
  <div class="case-file" role="dialog" aria-modal="true" aria-labelledby="case-title">
    <div class="case-head">
      <div style="display:flex; flex-direction:column; gap:6px;">
        <span class="case-project" id="case-project"></span>
        <h2 id="case-title" class="stamp-face" style="margin:0; font-size:1.1rem; font-weight:400;"></h2>
      </div>
      <button class="close-btn mono" id="close-btn">CLOSE ✕</button>
    </div>
    <div class="case-body" id="case-body"></div>
    <div class="case-foot" id="case-foot"></div>
  </div>
</div>

<script>
  const GRAPH = __DATA_JSON__;

  const PROJECT_COLOR = {};
  const PALETTE = ["#D2604E", "#7FA08D", "#C9A24B", "#6C8FB0", "#A87FB0", "#8FB06C"];
  const projects = [...new Set(GRAPH.nodes.map(n => n.project))].sort();
  projects.forEach((p, i) => PROJECT_COLOR[p] = PALETTE[i % PALETTE.length]);

  const REDUCE_MOTION = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function renderMarkdown(text) {
    const lines = escapeHtml(text).split("\n");
    let html = ""; let inList = false;
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
    const inline = (s) => s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    for (const line of lines) {
      if (/^### /.test(line)) { closeList(); html += `<h4>${inline(line.slice(4))}</h4>`; continue; }
      if (/^## /.test(line)) { closeList(); html += `<h3>${inline(line.slice(3))}</h3>`; continue; }
      if (/^# /.test(line)) { closeList(); html += `<h2>${inline(line.slice(2))}</h2>`; continue; }
      if (/^-{3,}$/.test(line.trim())) { closeList(); html += "<hr>"; continue; }
      if (/^[-*]\s+/.test(line)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`; continue; }
      if (/^\d+\.\s+/.test(line)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`; continue; }
      closeList();
      if (line.trim() === "") continue;
      html += `<p>${inline(line)}</p>`;
    }
    closeList();
    return html;
  }
  function preview(text, len) {
    len = len || 60;
    const s = text.replace(/[#*`_>]/g, "").replace(/\s+/g, " ").trim();
    return s.length > len ? s.slice(0, len) + "…" : s;
  }

  const nodeById = {};
  const nodes = GRAPH.nodes.map((n, i) => {
    const total = GRAPH.nodes.length;
    const phi = Math.acos(1 - 2 * (i + 0.5) / total);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const R = 170;
    const obj = {
      ...n,
      x: R * Math.sin(phi) * Math.cos(theta),
      y: R * Math.sin(phi) * Math.sin(theta),
      z: R * Math.cos(phi),
      vx: 0, vy: 0, vz: 0, r: 9, degree: 0,
    };
    nodeById[n.id] = obj;
    return obj;
  });

  const edges = GRAPH.edges.map(e => ({ ...e, s: nodeById[e.source], t: nodeById[e.target] }));
  edges.forEach(e => { e.s.degree++; e.t.degree++; });
  nodes.forEach(n => { n.r = 7 + Math.min(n.degree, 6) * 1.1; if (n.role === "core") n.r *= 1.7; else if (n.role === "latest") n.r *= 1.35; });

  const ANCHOR = {};
  projects.forEach((p, i) => {
    const a = (i / projects.length) * Math.PI * 2;
    ANCHOR[p] = { x: Math.cos(a) * 330, y: Math.sin(a) * 190, z: Math.sin(a * 1.7) * 230 };
  });

  const state = {
    only: (projects.length > 1 && GRAPH.current_project && projects.includes(GRAPH.current_project)) ? GRAPH.current_project : null,
    keyOnly: false,
    q: "",
    type: null,
    status: null,
    dateFrom: "",
    dateTo: "",
    minSim: 0,
    showSemantic: true,
    showExplicit: true,
  };
  const inDateRange = (n) => {
    if (!n.created_at) return true;
    const d = n.created_at.slice(0, 10);
    if (state.dateFrom && d < state.dateFrom) return false;
    if (state.dateTo && d > state.dateTo) return false;
    return true;
  };
  const isVisible = (n) => (!state.only || n.project === state.only)
    && (!state.keyOnly || n.role)
    && (!state.type || n.type === state.type)
    && (!state.status || n.status === state.status)
    && inDateRange(n);
  const matches = (n) => !state.q || (n.content + " " + (n.slug || "") + " " + n.type + " " + n.project).toLowerCase().includes(state.q);

  function simTick() {
    const REPEL = 2600;
    const SPRING = 0.02;
    const CENTER = 0.0015;
    const DAMP = 0.86;

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        let distSq = dx * dx + dy * dy + dz * dz;
        if (distSq < 1) distSq = 1;
        const dist = Math.sqrt(distSq);
        const force = REPEL / distSq;
        const fx = (dx / dist) * force, fy = (dy / dist) * force, fz = (dz / dist) * force;
        a.vx += fx; a.vy += fy; a.vz += fz;
        b.vx -= fx; b.vy -= fy; b.vz -= fz;
      }
    }

    for (const e of edges) {
      const dx = e.t.x - e.s.x, dy = e.t.y - e.s.y, dz = e.t.z - e.s.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      const rest = 260 - e.sim * 190;
      const force = (dist - rest) * SPRING;
      const fx = (dx / dist) * force, fy = (dy / dist) * force, fz = (dz / dist) * force;
      e.s.vx += fx; e.s.vy += fy; e.s.vz += fz;
      e.t.vx -= fx; e.t.vy -= fy; e.t.vz -= fz;
    }

    for (const n of nodes) {
      if (projects.length > 1) {
        const anc = ANCHOR[n.project];
        n.vx += (anc.x - n.x) * 0.009; n.vy += (anc.y - n.y) * 0.009; n.vz += (anc.z - n.z) * 0.009;
      }
      n.vx -= n.x * CENTER;
      n.vy -= n.y * CENTER;
      n.vz -= n.z * CENTER;
      n.vx *= DAMP; n.vy *= DAMP; n.vz *= DAMP;
      n.x += n.vx; n.y += n.vy; n.z += n.vz;
    }
  }

  if (REDUCE_MOTION) {
    for (let i = 0; i < 400; i++) simTick();
  }

  const canvas = document.getElementById("stage");
  const ctx = canvas.getContext("2d");
  let W, H, DPR;
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * DPR; canvas.height = H * DPR;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  window.addEventListener("resize", resize);
  resize();

  let hoverNode = null;
  let yaw = 0.6, pitch = 0.25, zoom = 1;
  let autoRotate = !REDUCE_MOTION;
  let orbiting = false, orbitMoved = false, lastX = 0, lastY = 0, idleSince = 0;
  const FOCAL = 720;

  function project(n) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const x1 = n.x * cy + n.z * sy;
    const z1 = -n.x * sy + n.z * cy;
    const y2 = n.y * cp - z1 * sp;
    const z2 = n.y * sp + z1 * cp;
    const scale = (FOCAL / (FOCAL + z2 + 260)) * zoom;
    return { x: W / 2 + x1 * scale, y: H / 2 + y2 * scale, z: z2, s: scale };
  }

  function depthAlpha(z) {
    return Math.max(0.18, Math.min(1, 1 - (z + 260) / 700));
  }

  function connectedIds(n) {
    const set = new Set([n.id]);
    edges.forEach(e => { if (e.s === n) set.add(e.t.id); if (e.t === n) set.add(e.s.id); });
    return set;
  }

  function hexToRgb(h) {
    const v = parseInt(h.slice(1), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }

  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    const highlight = hoverNode ? connectedIds(hoverNode) : null;
    nodes.forEach(n => { n.p = project(n); });

    const sortedEdges = edges.slice().sort((a, b) => (b.s.p.z + b.t.p.z) - (a.s.p.z + a.t.p.z));
    for (const e of sortedEdges) {
      if (!isVisible(e.s) || !isVisible(e.t)) continue;
      if (e.kind === "explicit" && !state.showExplicit) continue;
      if (e.kind === "semantic" && (!state.showSemantic || e.sim < state.minSim)) continue;
      const p1 = e.s.p, p2 = e.t.p;
      const dim = highlight && !(highlight.has(e.s.id) && highlight.has(e.t.id));
      const da = depthAlpha((p1.z + p2.z) / 2);

      if (e.kind === "explicit") {
        const base = dim ? 0.05 : (highlight ? 0.95 : 0.55);
        ctx.save();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = `rgba(232,93,93,${base * da})`;
        ctx.lineWidth = (highlight && !dim ? 1.8 : 1.3) * Math.max(0.5, (p1.s + p2.s) / 2);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
        ctx.restore();
        if (!dim) {
          const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
          const ah = 6 * Math.max(0.6, p2.s);
          ctx.save();
          ctx.globalAlpha = base * da;
          ctx.fillStyle = "rgba(232,93,93,1)";
          ctx.translate(p2.x - Math.cos(angle) * 8, p2.y - Math.sin(angle) * 8);
          ctx.rotate(angle);
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-ah, ah * 0.55);
          ctx.lineTo(-ah, -ah * 0.55);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
        continue;
      }

      const base = dim ? 0.03 : (highlight ? 0.6 : 0.1 + e.sim * 0.3);
      const c1 = hexToRgb(PROJECT_COLOR[e.s.project]), c2 = hexToRgb(PROJECT_COLOR[e.t.project]);
      const grad = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
      grad.addColorStop(0, `rgba(${c1[0]},${c1[1]},${c1[2]},${base * da})`);
      grad.addColorStop(1, `rgba(${c2[0]},${c2[1]},${c2[2]},${base * da})`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = (highlight && !dim ? 1.6 : 1) * Math.max(0.5, (p1.s + p2.s) / 2);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();

      if (!REDUCE_MOTION && !dim) {
        const f = ((t * 0.00025 * (0.6 + e.sim) + e.phase) % 1);
        const px = p1.x + (p2.x - p1.x) * f, py = p1.y + (p2.y - p1.y) * f;
        const ps = Math.max(0.6, (p1.s + p2.s) / 2);
        ctx.save();
        ctx.globalAlpha = Math.min(1, da * 1.2);
        ctx.shadowColor = "#fff";
        ctx.shadowBlur = 8;
        ctx.fillStyle = "rgba(255,244,220,0.95)";
        ctx.beginPath();
        ctx.arc(px, py, 1.5 * ps, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }

    const sorted = nodes.slice().sort((a, b) => b.p.z - a.p.z);
    for (const n of sorted) {
      if (!isVisible(n)) continue;
      const p = n.p;
      const dim = (highlight && !highlight.has(n.id)) || !matches(n);
      const color = PROJECT_COLOR[n.project];
      const rgb = hexToRgb(color);
      const rad = n.r * p.s * (n === hoverNode ? 1.25 : 1);
      const a = (dim ? 0.25 : 1) * depthAlpha(p.z);
      const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, rad * 3.2);
      glow.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${0.55 * a})`);
      glow.addColorStop(1, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0)`);
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(p.x, p.y, rad * 3.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.save();
      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(p.x, p.y, rad, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x - rad * 0.3, p.y - rad * 0.3, rad * 0.35, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,255,255,0.35)";
      ctx.fill();
      if (n.role === "core") {
        ctx.strokeStyle = "#F2C14E";
        ctx.lineWidth = 2.4 * Math.max(0.7, p.s);
        ctx.beginPath(); ctx.arc(p.x, p.y, rad * 1.5, 0, Math.PI * 2); ctx.stroke();
        ctx.globalAlpha = a * 0.4; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(p.x, p.y, rad * 1.95, 0, Math.PI * 2); ctx.stroke();
      } else if (n.role === "latest") {
        const pulse = 1 + 0.14 * Math.sin((t || 0) / 320);
        const d = rad * 1.6 * pulse;
        ctx.strokeStyle = "#FFF4DC";
        ctx.lineWidth = 2 * Math.max(0.7, p.s);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - d); ctx.lineTo(p.x + d, p.y); ctx.lineTo(p.x, p.y + d); ctx.lineTo(p.x - d, p.y);
        ctx.closePath(); ctx.stroke();
      }
      ctx.restore();
      if (n.role && !dim) {
        ctx.save();
        ctx.globalAlpha = a;
        ctx.font = `${Math.round(11 * Math.max(0.85, p.s))}px "JetBrains Mono", monospace`;
        ctx.textAlign = "center";
        ctx.fillStyle = n.role === "core" ? "#F2C14E" : "#FFF4DC";
        const txt = n.role === "core" ? `${n.project} · CORE` : `${n.project} · latest checkpoint${n.created_at ? " " + n.created_at.slice(0, 10) : ""}`;
        ctx.fillText(txt, p.x, p.y - rad * 2.3);
        ctx.restore();
      }
    }
  }

  edges.forEach(e => { e.phase = Math.random(); });

  function loop(t) {
    if (!REDUCE_MOTION) simTick();
    if (autoRotate && !orbiting && t - idleSince > 1500) yaw += 0.0026;
    draw(t || 0);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  function nodeAt(x, y) {
    let best = null, bestZ = Infinity;
    for (const n of nodes) {
      if (!n.p || !isVisible(n)) continue;
      const dx = n.p.x - x, dy = n.p.y - y;
      const rr = n.r * n.p.s + 5;
      if (dx * dx + dy * dy <= rr * rr && n.p.z < bestZ) { best = n; bestZ = n.p.z; }
    }
    return best;
  }

  const labelEl = document.getElementById("node-label");

  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    if (orbiting) {
      const dx = e.clientX - lastX, dy = e.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) orbitMoved = true;
      yaw += dx * 0.006;
      pitch = Math.max(-1.3, Math.min(1.3, pitch + dy * 0.006));
      lastX = e.clientX; lastY = e.clientY;
      labelEl.classList.remove("show");
      return;
    }
    const hit = nodeAt(x, y);
    hoverNode = hit;
    if (hit) {
      labelEl.textContent = `${hit.project} · ${hit.type} · ${preview(hit.content, 46)}`;
      labelEl.style.left = hit.p.x + "px";
      labelEl.style.top = hit.p.y + "px";
      labelEl.classList.add("show");
      canvas.style.cursor = "pointer";
    } else {
      labelEl.classList.remove("show");
      canvas.style.cursor = "grab";
    }
  });

  canvas.addEventListener("mousedown", (e) => {
    orbiting = true; orbitMoved = false;
    lastX = e.clientX; lastY = e.clientY;
    canvas.classList.add("dragging");
  });

  window.addEventListener("mouseup", (e) => {
    if (!orbiting) return;
    orbiting = false;
    idleSince = performance.now();
    canvas.classList.remove("dragging");
    if (!orbitMoved) {
      const rect = canvas.getBoundingClientRect();
      const hit = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
      if (hit) openCase(hit.id);
    }
  });

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoom = Math.max(0.35, Math.min(3, zoom * (e.deltaY < 0 ? 1.08 : 0.93)));
    idleSince = performance.now();
  }, { passive: false });

  canvas.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    const rect = canvas.getBoundingClientRect();
    const hit = nodeAt(t.clientX - rect.left, t.clientY - rect.top);
    if (hit) openCase(hit.id);
  }, { passive: true });

  function openCase(id) {
    const n = nodeById[id];
    if (!n) return;
    document.getElementById("case-project").textContent = n.project + (n.slug ? " · " + n.slug : "");
    document.getElementById("case-title").textContent = n.type.toUpperCase();
    document.getElementById("case-body").innerHTML = renderMarkdown(n.content);
    const foot = [`id: ${n.id}`, `${n.degree} linked ${n.degree === 1 ? "memory" : "memories"}`];
    document.getElementById("case-foot").innerHTML = foot.map(f => `<span>${escapeHtml(f)}</span>`).join("");
    document.getElementById("overlay").hidden = false;
    document.getElementById("close-btn").focus();
  }
  function closeCase() { document.getElementById("overlay").hidden = true; }
  document.getElementById("close-btn").addEventListener("click", closeCase);
  document.getElementById("overlay").addEventListener("click", (e) => { if (e.target.id === "overlay") closeCase(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !document.getElementById("overlay").hidden) closeCase(); });

  document.getElementById("stat-line").textContent =
    `${nodes.length} memories · ${edges.length} connections · linked to their ${GRAPH.k} nearest neighbors by meaning`;

  document.getElementById("legend").innerHTML = projects.map(p =>
    `<div class="legend-row"><span class="legend-dot" style="background:${PROJECT_COLOR[p]}"></span>${escapeHtml(p)}</div>`
  ).join("") +
    `<div class="legend-row"><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="#F2C14E" stroke-width="2"/></svg>core memory (project overview)</div>` +
    `<div class="legend-row"><svg width="14" height="14"><path d="M7 1 L13 7 L7 13 L1 7 Z" fill="none" stroke="#FFF4DC" stroke-width="1.6"/></svg>latest checkpoint</div>` +
    `<div class="legend-row"><svg width="14" height="14"><line x1="1" y1="7" x2="13" y2="7" stroke="#E85D5D" stroke-width="1.6" stroke-dasharray="3,2"/></svg>explicit relationship (related_to / supersedes / caused_by / blocked_by / implements)</div>`;

  function fitZoom() {
    const vis = nodes.filter(isVisible);
    if (!vis.length) return;
    const R = Math.max(...vis.map(n => Math.hypot(n.x, n.y, n.z)), 60);
    zoom = Math.max(0.5, Math.min(2.6, (Math.min(W, H) * 0.36) / R));
  }
  const chipsEl = document.getElementById("chips");
  function renderChips() {
    chipsEl.innerHTML = "";
    const mk = (label, key, color) => {
      const b = document.createElement("button");
      b.className = "chip" + ((state.only === key) ? " active" : "");
      b.innerHTML = (color ? `<i style="background:${color}"></i>` : "") + escapeHtml(label);
      b.addEventListener("click", () => { state.only = (state.only === key ? null : key); renderChips(); fitZoom(); });
      chipsEl.appendChild(b);
    };
    if (projects.length > 1) projects.forEach(p => mk(p, p, PROJECT_COLOR[p]));
  }
  renderChips();
  document.getElementById("q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); });
  document.getElementById("keyOnly").addEventListener("change", (e) => { state.keyOnly = e.target.checked; fitZoom(); });

  const typeFilterEl = document.getElementById("typeFilter");
  [...new Set(GRAPH.nodes.map(n => n.type))].sort().forEach(t => {
    const o = document.createElement("option");
    o.value = t; o.textContent = t;
    typeFilterEl.appendChild(o);
  });
  typeFilterEl.addEventListener("change", (e) => { state.type = e.target.value || null; fitZoom(); });

  const statusFilterEl = document.getElementById("statusFilter");
  [...new Set(GRAPH.nodes.map(n => n.status))].sort().forEach(s => {
    const o = document.createElement("option");
    o.value = s; o.textContent = s;
    statusFilterEl.appendChild(o);
  });
  statusFilterEl.addEventListener("change", (e) => { state.status = e.target.value || null; fitZoom(); });

  document.getElementById("dateFrom").addEventListener("change", (e) => { state.dateFrom = e.target.value; fitZoom(); });
  document.getElementById("dateTo").addEventListener("change", (e) => { state.dateTo = e.target.value; fitZoom(); });

  const simRangeEl = document.getElementById("simRange");
  const simValueEl = document.getElementById("simValue");
  simRangeEl.addEventListener("input", (e) => {
    state.minSim = parseFloat(e.target.value);
    simValueEl.textContent = state.minSim.toFixed(2);
  });

  document.getElementById("showSemantic").addEventListener("change", (e) => { state.showSemantic = e.target.checked; });
  document.getElementById("showExplicit").addEventListener("change", (e) => { state.showExplicit = e.target.checked; });

  if (state.only) fitZoom();
</script>
"""
