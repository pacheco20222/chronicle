import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls, PerspectiveCamera, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";

import { edgesForRender, edgesForVisibility } from "../graphEdges";
import type { GraphEdge, GraphNode, ScopeNode } from "../types";
import { colorForType } from "../types";

const BRASS = "#d8a84e";
const BRASS_BRIGHT = "#f0ca76";
const SEMANTIC = "#c5cee0";
const EXPLICIT = BRASS;
const STATUS_OPACITY = { active: 1, resolved: 0.62, superseded: 0.34, wrong: 0.34 } as const;
type LayoutNode = GraphNode & { position: THREE.Vector3; degree: number };
type Cluster = { project: string; center: THREE.Vector3; radius: number; color: string };

/* Deterministic hue per project name so each constellation reads as a
 * distinct "galaxy" color at a glance, without a lookup table to maintain
 * as projects come and go. */
function projectColor(project: string) {
  let hash = 0;
  for (let i = 0; i < project.length; i++) hash = (hash * 31 + project.charCodeAt(i)) >>> 0;
  const hue = hash % 360;
  return `hsl(${hue}, 62%, 68%)`;
}

function localClusterRadius(count: number) {
  return Math.max(0.75, 0.5 + Math.sqrt(count) * 0.42);
}

function fibonacciPoint(index: number, total: number, radius: number) {
  const phi = Math.acos(1 - (2 * (index + 0.5)) / total);
  const theta = Math.PI * (1 + Math.sqrt(5)) * index;
  return new THREE.Vector3(
    radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.sin(phi) * Math.sin(theta),
    radius * Math.cos(phi),
  );
}

type ScopePosition = { position: THREE.Vector3; isBlackHole: boolean; radius: number; scope: ScopeNode };

function computeProjectRadii(nodes: GraphNode[]) {
  const counts = new Map<string, number>();
  nodes.forEach((node) => counts.set(node.project, (counts.get(node.project) || 0) + 1));
  const radii = new Map<string, number>();
  counts.forEach((count, project) => radii.set(project, localClusterRadius(count)));
  return radii;
}

/* A scope with no memories of its own (a pure organizational node, e.g.
 * "work" created only because "work/azure" needed an ancestor) has no
 * node-count to size itself by, so its extent is a heuristic based on how
 * many children it holds instead — same shape as localClusterRadius, just
 * fed a different quantity. */
function scopeExtent(scope: ScopeNode, projectRadii: Map<string, number>) {
  return projectRadii.get(scope.path) ?? Math.max(0.9, 0.6 + Math.sqrt(Math.max(scope.child_count, 1)) * 0.5);
}

/* Recursively places every scope node using the exact same fibonacci-orbit
 * technique the flat per-project layout already used for a single level —
 * applied once per tree depth instead of once total. When no scope has ever
 * been reparented (the common case: every project is still a top-level
 * scope), this produces the same flat ring the dashboard always rendered;
 * nesting only appears once the user actually organizes their taxonomy. */
function useScopeLayout(scopes: ScopeNode[], projectRadii: Map<string, number>) {
  return useMemo(() => {
    const byParent = new Map<string | null, ScopeNode[]>();
    scopes.forEach((scope) => {
      const list = byParent.get(scope.parent_path);
      if (list) list.push(scope);
      else byParent.set(scope.parent_path, [scope]);
    });

    const positions = new Map<string, ScopePosition>();

    function place(parentPath: string | null, center: THREE.Vector3) {
      const children = [...(byParent.get(parentPath) || [])].sort((a, b) => a.path.localeCompare(b.path));
      if (children.length === 0) return;
      const extents = children.map((child) => scopeExtent(child, projectRadii));
      const maxExtent = Math.max(0.75, ...extents);
      const orbitRadius = children.length <= 1 ? 0 : Math.max(4, maxExtent * 2.4 + Math.sqrt(children.length) * 1.1);
      children.forEach((child, index) => {
        const local = children.length === 1 ? new THREE.Vector3() : fibonacciPoint(index, children.length, orbitRadius);
        const position = center.clone().add(local);
        positions.set(child.path, { position, isBlackHole: child.child_count > 0, radius: extents[index], scope: child });
        place(child.path, position);
      });
    }

    place(null, new THREE.Vector3(0, 0, 0));
    return positions;
  }, [scopes, projectRadii]);
}

function useLayout(nodes: GraphNode[], edges: GraphEdge[], scopePositions: Map<string, ScopePosition>) {
  return useMemo(() => {
    const degree = new Map(nodes.map((node) => [node.id, 0]));
    edges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    });

    const byProject = new Map<string, GraphNode[]>();
    nodes.forEach((node) => {
      const list = byProject.get(node.project);
      if (list) list.push(node);
      else byProject.set(node.project, [node]);
    });
    const projects = [...byProject.keys()].sort();
    const projectCount = Math.max(projects.length, 1);
    const localRadii = projects.map((project) => localClusterRadius(byProject.get(project)!.length));
    const maxLocalRadius = Math.max(0.75, ...localRadii);
    const clusterRadius = projectCount <= 1 ? 0 : Math.max(4.5, maxLocalRadius * 2.4 + Math.sqrt(projectCount) * 1.1);
    const fallbackCenter = (clusterIndex: number) =>
      projectCount <= 1 ? new THREE.Vector3() : fibonacciPoint(clusterIndex, projectCount, clusterRadius);

    const layout: LayoutNode[] = [];
    const clusterCenters: THREE.Vector3[] = [];
    projects.forEach((project, clusterIndex) => {
      const center = scopePositions.get(project)?.position ?? fallbackCenter(clusterIndex);
      clusterCenters.push(center);
      const projectNodes = byProject.get(project)!;
      const total = Math.max(projectNodes.length, 1);
      const radius = localClusterRadius(total);
      projectNodes.forEach((node, index) => {
        const local = total === 1 ? new THREE.Vector3() : fibonacciPoint(index, total, radius);
        layout.push({
          ...node,
          degree: degree.get(node.id) || 0,
          position: center.clone().add(local),
        });
      });
    });

    const clusters: Cluster[] = projects.map((project, clusterIndex) => ({
      project,
      center: clusterCenters[clusterIndex],
      radius: localRadii[clusterIndex],
      color: projectColor(project),
    }));

    let extent = clusterRadius + maxLocalRadius;
    clusters.forEach((cluster) => { extent = Math.max(extent, cluster.center.length() + cluster.radius); });
    scopePositions.forEach((scopePosition) => {
      extent = Math.max(extent, scopePosition.position.length() + scopePosition.radius);
    });

    return { layout, clusters, extent };
  }, [edges, nodes, scopePositions]);
}

let glowTexture: THREE.Texture | null = null;
function getGlowTexture() {
  if (glowTexture) return glowTexture;
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.4, "rgba(255,255,255,0.4)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  glowTexture = new THREE.CanvasTexture(canvas);
  return glowTexture;
}

/* Procedural granulation texture for a scope beacon's surface — mottled
 * light/dark blotches over a warm base gradient, the way a real sun's
 * photosphere looks grainy up close rather than a flat color. This is what
 * gives the beacon actual surface character instead of reading as a glow
 * effect with nothing solid underneath it. */
let sunSurfaceTexture: THREE.Texture | null = null;
function getSunSurfaceTexture() {
  if (sunSurfaceTexture) return sunSurfaceTexture;
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const base = ctx.createRadialGradient(size * 0.42, size * 0.38, size * 0.04, size * 0.5, size * 0.5, size * 0.72);
  base.addColorStop(0, "#fff3d6");
  base.addColorStop(0.32, "#ffb562");
  base.addColorStop(0.68, "#e8703a");
  base.addColorStop(1, "#a83e1c");
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < 520; i++) {
    const x = Math.random() * size;
    const y = Math.random() * size;
    const r = 1.5 + Math.random() * 6;
    ctx.globalAlpha = 0.08 + Math.random() * 0.14;
    ctx.fillStyle = Math.random() > 0.5 ? "#fff3d6" : "#7a2e14";
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  sunSurfaceTexture = new THREE.CanvasTexture(canvas);
  sunSurfaceTexture.wrapS = sunSurfaceTexture.wrapT = THREE.RepeatWrapping;
  return sunSurfaceTexture;
}

function roleLabel(node: GraphNode) {
  if (node.role === "core") return `${node.project} · CORE`;
  if (node.role === "latest") return `${node.project} · latest checkpoint${node.created_at ? ` ${node.created_at.slice(0, 10)}` : ""}`;
  return null;
}

function ProjectNebula({ cluster }: { cluster: Cluster }) {
  const nebulaScale = (cluster.radius + 0.9) * 2.6;
  return (
    <sprite position={cluster.center} scale={[nebulaScale, nebulaScale, 1]} renderOrder={-1}>
      <spriteMaterial map={getGlowTexture()} color={cluster.color} transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
    </sprite>
  );
}

function ProjectLabel({ cluster }: { cluster: Cluster }) {
  const position = useMemo(() => cluster.center.clone().add(new THREE.Vector3(0, cluster.radius + 0.55, 0)), [cluster]);
  return (
    <Html position={position} center distanceFactor={11} zIndexRange={[5, 0]} style={{ pointerEvents: "none", whiteSpace: "nowrap", fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: "13px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: cluster.color, textShadow: "0 0 8px rgba(2,3,7,0.95), 0 0 3px rgba(2,3,7,0.95)" }}>
      {cluster.project}
    </Html>
  );
}

/* The scope-hierarchy signature element: a scope with children renders as
 * a red giant — a big, soft, warm-colored star — rather than a dark
 * occluding body or a hard-edged ring (an earlier pass added a bright
 * equatorial ring, which read as "planet with rings," not "star"; dropped
 * entirely). Built from layered spheres and glow sprites the way real
 * astrophoto renderings of a red giant look: a hot small core, a large
 * warm-orange visible disk, and a big, slowly-pulsing soft corona — no ring
 * geometry anywhere. Children of any kind (sub-scopes or leaf projects)
 * orbit it via useScopeLayout and are joined to it by a plain orbit line
 * (see ScopeOrbitLine) that targets each child's own core-memory marker
 * when it has one, not an empty point in space. A leaf project scope with
 * no children renders no beacon here at all — it's still just its existing
 * star cluster. */
function ScopeBody({ scope, position, radius, isBlackHole, onSelect }: { scope: ScopeNode; position: THREE.Vector3; radius: number; isBlackHole: boolean; onSelect: (scope: ScopeNode) => void }) {
  const surfaceRef = useRef<THREE.Mesh>(null);
  const coronaRef = useRef<THREE.SpriteMaterial>(null);
  const baseCoronaOpacity = scope.core_present ? 0.28 : 0.18;

  useFrame((_, delta) => {
    if (surfaceRef.current) surfaceRef.current.rotation.y += delta * 0.06;
  });

  if (!isBlackHole) return null;

  return (
    <group position={position} onPointerDown={(event) => { event.stopPropagation(); onSelect(scope); }}>
      {/* thin, dim corona — just enough to read as radiating heat, not a
       * glow effect standing in for the body itself. The body does that. */}
      <sprite scale={[radius * 2.6, radius * 2.6, 1]}>
        <spriteMaterial ref={coronaRef} map={getGlowTexture()} color="#ff8f57" transparent opacity={baseCoronaOpacity} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </sprite>
      {/* the star's actual body — a slowly-rotating, granulated surface,
       * not a flat-colored ball. Rotation is this element's one authored
       * motion; the old pulsing corona is gone so it doesn't compete. */}
      <mesh ref={surfaceRef} renderOrder={1}>
        <sphereGeometry args={[radius * 0.78, 40, 28]} />
        <meshBasicMaterial map={getSunSurfaceTexture()} toneMapped={false} />
      </mesh>
      {scope.linked_doc_count > 0 && (
        <sprite position={[radius * 1.4, radius * 0.75, radius * 0.3]} scale={[radius * 0.55, radius * 0.55, 1]}>
          <spriteMaterial map={getGlowTexture()} color={SEMANTIC} transparent opacity={0.85} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </sprite>
      )}
      <Html position={[0, radius * 0.78 + 0.4, 0]} center distanceFactor={11} zIndexRange={[5, 0]} style={{ pointerEvents: "none", whiteSpace: "nowrap", fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: "11px", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: BRASS_BRIGHT, textShadow: "0 0 8px rgba(2,3,7,0.95), 0 0 3px rgba(2,3,7,0.95)" }}>
        {scope.name}
      </Html>
    </group>
  );
}

/* A plain structural line from a scope to its parent — never additive glow,
 * never dashed (dashed brass is already spoken for by explicit memory
 * relations, see ExplicitEdgeLine) — so the hierarchy itself reads as a
 * real connection, not a coincidence of two beacons happening to line up. */
function ScopeOrbitLine({ from, to }: { from: THREE.Vector3; to: THREE.Vector3 }) {
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints([from, to]), [from, to]);
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={BRASS} transparent opacity={0.22} toneMapped={false} />
    </lineSegments>
  );
}

let nodeSphereGeometry: THREE.SphereGeometry | null = null;
function getNodeSphere() {
  if (!nodeSphereGeometry) nodeSphereGeometry = new THREE.SphereGeometry(0.1, 20, 14);
  return nodeSphereGeometry;
}

function NodeGlyph({ node, position, degree, highlighted, focusActive, onSelect }: { node: GraphNode; position: THREE.Vector3; degree: number; highlighted: boolean; focusActive: boolean; onSelect: (node: GraphNode) => void }) {
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);
  const glowRef = useRef<THREE.SpriteMaterial>(null);
  const ringRef = useRef<THREE.MeshBasicMaterial>(null);
  const shape = getNodeSphere();
  const statusOpacity = STATUS_OPACITY[node.status] || STATUS_OPACITY.active;
  const significance = 0.68 + Math.min(degree, 8) * 0.04;
  const roleScale = node.role === "core" ? 3.2 : node.role === "latest" ? 1.12 : 1;
  const scale = significance * roleScale * (node.status === "superseded" ? 0.82 : node.status === "resolved" ? 0.92 : 1);
  const color = colorForType(node.type);
  const label = useMemo(() => roleLabel(node), [node]);

  useFrame((_, delta) => {
    const target = focusActive ? (highlighted ? 1 : 0.28) : statusOpacity;
    if (materialRef.current) materialRef.current.opacity = THREE.MathUtils.damp(materialRef.current.opacity, target, 5, delta);
    if (glowRef.current) glowRef.current.opacity = THREE.MathUtils.damp(glowRef.current.opacity, target * 0.56, 5, delta);
    if (ringRef.current) ringRef.current.opacity = THREE.MathUtils.damp(ringRef.current.opacity, node.role ? (highlighted || !focusActive ? 0.95 : 0.28) : 0, 5, delta);
  });

  return (
    <group position={position} onPointerDown={(event) => { event.stopPropagation(); onSelect(node); }}>
      <sprite scale={[0.52 * scale, 0.52 * scale, 1]}>
        <spriteMaterial ref={glowRef} map={getGlowTexture()} color={color} transparent opacity={statusOpacity * 0.56} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </sprite>
      <mesh geometry={shape} scale={scale}>
        <meshBasicMaterial ref={materialRef} color={color} transparent opacity={statusOpacity} toneMapped={false} />
      </mesh>
      {/* Distinctiveness comes from scale (roleScale 3.2x vs. latest's
       * 1.12x) and a thicker single ring, not from stacking more rings. */}
      {node.role === "core" && <mesh rotation={[Math.PI / 2, 0, 0]} scale={1.35 * scale}>
        <torusGeometry args={[0.13, 0.024, 8, 24]} />
        <meshBasicMaterial ref={ringRef} color={BRASS} transparent opacity={0.95} toneMapped={false} />
      </mesh>}
      {node.role === "latest" && <mesh rotation={[Math.PI / 2.3, 0, Math.PI / 4]} scale={1.35 * scale}>
        <torusGeometry args={[0.13, 0.01, 8, 24]} />
        <meshBasicMaterial ref={ringRef} color={BRASS} transparent opacity={0.85} toneMapped={false} />
      </mesh>}
      {label && <Html position={[0, 0.3 * scale + 0.08, 0]} center distanceFactor={9} zIndexRange={[10, 0]} style={{ pointerEvents: "none", whiteSpace: "nowrap", fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: "10px", letterSpacing: "0.03em", color: BRASS, textShadow: "0 0 5px rgba(5,7,18,0.95), 0 0 2px rgba(5,7,18,0.95)" }}>{label}</Html>}
    </group>
  );
}

function ExplicitEdgeLine({ source, target, highlighted, focusActive }: { source: THREE.Vector3; target: THREE.Vector3; highlighted: boolean; focusActive: boolean }) {
  const materialRef = useRef<THREE.LineDashedMaterial>(null);
  const geometry = useMemo(() => {
    const result = new THREE.BufferGeometry().setFromPoints([source, target]);
    new THREE.Line(result).computeLineDistances();
    return result;
  }, [source, target]);

  useFrame((_, delta) => {
    if (!materialRef.current) return;
    const targetOpacity = focusActive ? (highlighted ? 1 : 0.05) : 0.7;
    materialRef.current.opacity = THREE.MathUtils.damp(materialRef.current.opacity, targetOpacity, 5, delta);
  });

  return <lineSegments geometry={geometry}>
    <lineDashedMaterial ref={materialRef} color={EXPLICIT} transparent opacity={0.7} dashSize={0.22} gapSize={0.14} toneMapped={false} />
  </lineSegments>;
}

/* Batches every semantic edge into one additively-blended lineSegments draw
 * call, per-vertex-colored by cosine similarity. Overlapping lines add their
 * glow, which is what produces the "spiderweb nebula" look instead of a flat
 * wash of uniform-opacity segments (one draw call per edge otherwise, and no
 * glow buildup where lines cross). Static per render — no per-frame damping —
 * matching how sparse this graph actually is (tens, not tens of thousands). */
function SemanticEdgeField({ edges, positionById, connectedIds, focusActive }: { edges: GraphEdge[]; positionById: Map<string, THREE.Vector3>; connectedIds: Set<string>; focusActive: boolean }) {
  const geometry = useMemo(() => {
    const color = new THREE.Color(SEMANTIC);
    const positions = new Float32Array(edges.length * 6);
    const colors = new Float32Array(edges.length * 6);
    let count = 0;
    for (const edge of edges) {
      const source = positionById.get(edge.source);
      const target = positionById.get(edge.target);
      if (!source || !target) continue;
      const highlighted = connectedIds.has(edge.source) && connectedIds.has(edge.target);
      let intensity = 0.05 + edge.sim * 0.22;
      if (focusActive) intensity = highlighted ? 0.55 : intensity * 0.15;

      const off = count * 6;
      positions[off] = source.x; positions[off + 1] = source.y; positions[off + 2] = source.z;
      positions[off + 3] = target.x; positions[off + 4] = target.y; positions[off + 5] = target.z;
      colors[off] = color.r * intensity; colors[off + 1] = color.g * intensity; colors[off + 2] = color.b * intensity;
      colors[off + 3] = colors[off]; colors[off + 4] = colors[off + 1]; colors[off + 5] = colors[off + 2];
      count++;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions.slice(0, count * 6), 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors.slice(0, count * 6), 3));
    return geo;
  }, [edges, positionById, connectedIds, focusActive]);

  return <lineSegments geometry={geometry}>
    <lineBasicMaterial vertexColors transparent opacity={1} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
  </lineSegments>;
}

function RelationArrow({ source, target, highlighted, focusActive }: { source: THREE.Vector3; target: THREE.Vector3; highlighted: boolean; focusActive: boolean }) {
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);
  const direction = useMemo(() => target.clone().sub(source).normalize(), [source, target]);
  const position = useMemo(() => target.clone().sub(direction.clone().multiplyScalar(0.2)), [direction, target]);
  const quaternion = useMemo(() => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction), [direction]);
  useFrame((_, delta) => {
    if (!materialRef.current) return;
    const targetOpacity = focusActive ? (highlighted ? 1 : 0.04) : 0.7;
    materialRef.current.opacity = THREE.MathUtils.damp(materialRef.current.opacity, targetOpacity, 5, delta);
  });
  return <mesh position={position} quaternion={quaternion}>
    <coneGeometry args={[0.075, 0.24, 4]} />
    <meshBasicMaterial ref={materialRef} color={EXPLICIT} transparent opacity={0.7} toneMapped={false} />
  </mesh>;
}

function GraphObjects({ layout, clusters, edges, scopePositions, selectedId, onSelect, onSelectScope }: { layout: LayoutNode[]; clusters: Cluster[]; edges: GraphEdge[]; scopePositions: Map<string, ScopePosition>; selectedId: string | null; onSelect: (node: GraphNode) => void; onSelectScope: (scope: ScopeNode) => void }) {
  const positionById = useMemo(() => new Map(layout.map((node) => [node.id, node.position])), [layout]);
  /* A project's core memory is stored keyed by its bare name (see the
   * backend's own scope_graph_nodes fallback for why), same as scope.name
   * for a reparented leaf project — so this is the same lookup key an
   * orbit line needs to land on the actual core marker instead of the
   * cluster's empty fibonacci-computed centroid. */
  const coreNodeByProjectName = useMemo(
    () => new Map(layout.filter((node) => node.role === "core").map((node) => [node.project, node.position])),
    [layout],
  );
  const connectedIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const ids = new Set([selectedId]);
    edges.forEach((edge) => { if (edge.source === selectedId) ids.add(edge.target); if (edge.target === selectedId) ids.add(edge.source); });
    return ids;
  }, [edges, selectedId]);
  const focusActive = Boolean(selectedId);
  const semanticEdges = useMemo(() => edges.filter((edge) => edge.kind === "semantic"), [edges]);
  const explicitEdges = useMemo(() => edges.filter((edge) => edge.kind === "explicit"), [edges]);

  return <group>
    {clusters.map((cluster) => <ProjectNebula key={`nebula-${cluster.project}`} cluster={cluster} />)}
    {clusters.map((cluster) => <ProjectLabel key={`label-${cluster.project}`} cluster={cluster} />)}
    {[...scopePositions.entries()].map(([path, scopePosition]) => {
      const parentPath = scopePosition.scope.parent_path;
      const parentPosition = parentPath ? scopePositions.get(parentPath)?.position : undefined;
      const lineTarget = coreNodeByProjectName.get(scopePosition.scope.name) ?? scopePosition.position;
      return (
        <group key={`scope-${path}`}>
          {parentPosition && <ScopeOrbitLine from={parentPosition} to={lineTarget} />}
          <ScopeBody scope={scopePosition.scope} position={scopePosition.position} radius={scopePosition.radius} isBlackHole={scopePosition.isBlackHole} onSelect={onSelectScope} />
        </group>
      );
    })}
    <SemanticEdgeField edges={semanticEdges} positionById={positionById} connectedIds={connectedIds} focusActive={focusActive} />
    {explicitEdges.map((edge, index) => {
      const source = positionById.get(edge.source);
      const target = positionById.get(edge.target);
      if (!source || !target) return null;
      const highlighted = connectedIds.has(edge.source) && connectedIds.has(edge.target);
      return <group key={`${edge.source}-${edge.target}-${index}`}>
        <ExplicitEdgeLine source={source} target={target} highlighted={highlighted} focusActive={focusActive} />
        <RelationArrow source={source} target={target} highlighted={highlighted} focusActive={focusActive} />
      </group>;
    })}
    {layout.map((node) => <NodeGlyph key={node.id} node={node} position={node.position} degree={node.degree} highlighted={connectedIds.has(node.id)} focusActive={focusActive} onSelect={onSelect} />)}
  </group>;
}

function ChartMotion({ chartRef, controlsRef, layout, selectedId, interactionRef, homeDistance }: { chartRef: React.RefObject<THREE.Group | null>; controlsRef: React.RefObject<any>; layout: LayoutNode[]; selectedId: string | null; interactionRef: React.MutableRefObject<{ active: boolean; lastInteraction: number }>; homeDistance: number; }) {
  const { camera } = useThree();
  const selectedPoint = useMemo(() => new THREE.Vector3(), []);
  const desiredCamera = useMemo(() => new THREE.Vector3(), []);
  const homeCamera = useMemo(() => new THREE.Vector3(0, 0, homeDistance), [homeDistance]);
  const homeTarget = useMemo(() => new THREE.Vector3(), []);
  const direction = useMemo(() => new THREE.Vector3(), []);
  const nodeById = useMemo(() => new Map(layout.map((node) => [node.id, node])), [layout]);
  const wasSelectedRef = useRef(false);
  const homingRef = useRef(false);

  useFrame((state, delta) => {
    const chart = chartRef.current;
    const controls = controlsRef.current;
    const now = state.clock.elapsedTime * 1000;
    if (chart && !interactionRef.current.active && now - interactionRef.current.lastInteraction > 1200 && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      chart.rotation.y += delta * 0.075;
      chart.rotation.x = Math.sin(state.clock.elapsedTime * 0.04) * 0.045;
    }
    if (!controls) return;

    if (selectedId) {
      wasSelectedRef.current = true;
      homingRef.current = false;
    } else if (wasSelectedRef.current) {
      wasSelectedRef.current = false;
      homingRef.current = true;
    }

    if (selectedId && chart) {
      const node = nodeById.get(selectedId);
      if (node) {
        selectedPoint.copy(node.position);
        chart.localToWorld(selectedPoint);
        controls.target.lerp(selectedPoint, 1 - Math.exp(-delta * 2.8));
        direction.copy(camera.position).sub(controls.target).normalize();
        desiredCamera.copy(selectedPoint).add(direction.multiplyScalar(6.4));
        camera.position.lerp(desiredCamera, 1 - Math.exp(-delta * 2.1));
      }
    } else if (homingRef.current && !interactionRef.current.active) {
      // One-shot return to the overview framing right after a selection is
      // cleared. Cancelled the instant the user touches the controls, and
      // otherwise self-terminates on arrival — never fights free orbit/zoom
      // when nothing was ever selected.
      controls.target.lerp(homeTarget, 1 - Math.exp(-delta * 1.6));
      camera.position.lerp(homeCamera, 1 - Math.exp(-delta * 1.6));
      if (camera.position.distanceTo(homeCamera) < 0.05) homingRef.current = false;
    }
    controls.update();
  });
  return null;
}

export function GraphScene({ nodes, edges, scopes, selectedId, onSelect, onSelectScope, showSemanticEdges }: { nodes: GraphNode[]; edges: GraphEdge[]; scopes: ScopeNode[]; selectedId: string | null; onSelect: (node: GraphNode) => void; onSelectScope: (scope: ScopeNode) => void; showSemanticEdges: boolean }) {
  const projectRadii = useMemo(() => computeProjectRadii(nodes), [nodes]);
  const scopePositions = useScopeLayout(scopes, projectRadii);
  const { layout, clusters, extent } = useLayout(nodes, edges, scopePositions);
  const renderedEdges = useMemo(() => edgesForRender(edgesForVisibility(edges, showSemanticEdges)), [edges, showSemanticEdges]);
  const cameraDistance = Math.max(22, extent * 3.1);
  const chartRef = useRef<THREE.Group>(null);
  const controlsRef = useRef<any>(null);
  const interactionRef = useRef({ active: false, lastInteraction: 0 });
  return (
    <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "low-power" }} frameloop="always">
      <PerspectiveCamera makeDefault position={[0, 0, cameraDistance]} fov={42} />
      <color attach="background" args={["#040509"]} />
      <Stars radius={90} depth={60} count={9000} factor={2.1} saturation={0} fade speed={0.15} />
      <Stars radius={40} depth={30} count={3200} factor={1.3} saturation={0} fade speed={0.35} />
      <group ref={chartRef}>
        <GraphObjects layout={layout} clusters={clusters} edges={renderedEdges} scopePositions={scopePositions} selectedId={selectedId} onSelect={onSelect} onSelectScope={onSelectScope} />
      </group>
      <ChartMotion chartRef={chartRef} controlsRef={controlsRef} layout={layout} selectedId={selectedId} interactionRef={interactionRef} homeDistance={cameraDistance} />
      <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.07} enablePan={false} minDistance={4} maxDistance={Math.max(42, cameraDistance * 1.4)} onStart={() => { interactionRef.current.active = true; }} onEnd={() => { interactionRef.current.active = false; interactionRef.current.lastInteraction = performance.now(); }} />
      <EffectComposer><Bloom intensity={0.7} luminanceThreshold={0.28} mipmapBlur radius={0.65} /></EffectComposer>
    </Canvas>
  );
}
