import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls, PerspectiveCamera, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";

import { edgesForRender, edgesForVisibility } from "../graphEdges";
import type { GraphEdge, GraphNode } from "../types";
import { colorForType } from "../types";

const BRASS = "#d8a84e";
const SEMANTIC = "#c5cee0";
const EXPLICIT = BRASS;
const STATUS_OPACITY = { active: 1, resolved: 0.62, superseded: 0.34 } as const;
type LayoutNode = GraphNode & { position: THREE.Vector3; degree: number };

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

function useLayout(nodes: GraphNode[], edges: GraphEdge[]) {
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

    const layout: LayoutNode[] = [];
    projects.forEach((project, clusterIndex) => {
      const center = projectCount <= 1 ? new THREE.Vector3() : fibonacciPoint(clusterIndex, projectCount, clusterRadius);
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

    return { layout, extent: clusterRadius + maxLocalRadius };
  }, [edges, nodes]);
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

function roleLabel(node: GraphNode) {
  if (node.role === "core") return `${node.project} · CORE`;
  if (node.role === "latest") return `${node.project} · latest checkpoint${node.created_at ? ` ${node.created_at.slice(0, 10)}` : ""}`;
  return null;
}

function geometryForType(type: string) {
  switch (type) {
    case "decision": return new THREE.ConeGeometry(0.09, 0.18, 4);
    case "architecture": return new THREE.OctahedronGeometry(0.11, 0);
    case "bug": return new THREE.TetrahedronGeometry(0.11, 0);
    case "todo": return new THREE.BoxGeometry(0.14, 0.14, 0.14);
    case "checkpoint": return new THREE.OctahedronGeometry(0.11, 0);
    case "overview": return new THREE.DodecahedronGeometry(0.11, 0);
    default: return new THREE.SphereGeometry(0.1, 8, 6);
  }
}

function NodeGlyph({ node, position, degree, highlighted, focusActive, onSelect }: { node: GraphNode; position: THREE.Vector3; degree: number; highlighted: boolean; focusActive: boolean; onSelect: (node: GraphNode) => void }) {
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);
  const glowRef = useRef<THREE.SpriteMaterial>(null);
  const ringRef = useRef<THREE.MeshBasicMaterial>(null);
  const shape = useMemo(() => geometryForType(node.type), [node.type]);
  const statusOpacity = STATUS_OPACITY[node.status] || STATUS_OPACITY.active;
  const significance = 0.68 + Math.min(degree, 8) * 0.04;
  const roleScale = node.role === "core" ? 1.3 : node.role === "latest" ? 1.12 : 1;
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
      {node.role === "core" && <mesh rotation={[Math.PI / 2, 0, 0]} scale={1.35 * scale}>
        <torusGeometry args={[0.13, 0.014, 8, 24]} />
        <meshBasicMaterial ref={ringRef} color={BRASS} transparent opacity={0.95} toneMapped={false} />
      </mesh>}
      {node.role === "latest" && <mesh scale={1.35 * scale} rotation={[0, 0, Math.PI / 4]}>
        <octahedronGeometry args={[0.12, 0]} />
        <meshBasicMaterial ref={ringRef} color={BRASS} transparent opacity={0.95} wireframe toneMapped={false} />
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

function GraphObjects({ layout, edges, selectedId, onSelect }: { layout: LayoutNode[]; edges: GraphEdge[]; selectedId: string | null; onSelect: (node: GraphNode) => void }) {
  const positionById = useMemo(() => new Map(layout.map((node) => [node.id, node.position])), [layout]);
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

  useFrame((state, delta) => {
    const chart = chartRef.current;
    const controls = controlsRef.current;
    const now = state.clock.elapsedTime * 1000;
    if (chart && !interactionRef.current.active && now - interactionRef.current.lastInteraction > 1200 && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      chart.rotation.y += delta * 0.075;
      chart.rotation.x = Math.sin(state.clock.elapsedTime * 0.04) * 0.045;
    }
    if (!controls) return;
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
    } else {
      controls.target.lerp(homeTarget, 1 - Math.exp(-delta * 1.6));
      camera.position.lerp(homeCamera, 1 - Math.exp(-delta * 1.6));
    }
    controls.update();
  });
  return null;
}

export function GraphScene({ nodes, edges, selectedId, onSelect, showSemanticEdges }: { nodes: GraphNode[]; edges: GraphEdge[]; selectedId: string | null; onSelect: (node: GraphNode) => void; showSemanticEdges: boolean }) {
  const { layout, extent } = useLayout(nodes, edges);
  const renderedEdges = useMemo(() => edgesForRender(edgesForVisibility(edges, showSemanticEdges)), [edges, showSemanticEdges]);
  const cameraDistance = Math.max(22, extent * 3.1);
  const chartRef = useRef<THREE.Group>(null);
  const controlsRef = useRef<any>(null);
  const interactionRef = useRef({ active: false, lastInteraction: 0 });
  return (
    <Canvas dpr={[1, 1.5]} gl={{ antialias: true, powerPreference: "low-power" }} frameloop="always">
      <PerspectiveCamera makeDefault position={[0, 0, cameraDistance]} fov={42} />
      <color attach="background" args={["#090d1d"]} />
      <group ref={chartRef}>
        <Stars radius={34} depth={22} count={620} factor={1.15} saturation={0} fade speed={0} />
        <GraphObjects layout={layout} edges={renderedEdges} selectedId={selectedId} onSelect={onSelect} />
      </group>
      <ChartMotion chartRef={chartRef} controlsRef={controlsRef} layout={layout} selectedId={selectedId} interactionRef={interactionRef} homeDistance={cameraDistance} />
      <OrbitControls ref={controlsRef} enableDamping dampingFactor={0.07} enablePan={false} minDistance={4} maxDistance={Math.max(42, cameraDistance * 1.4)} onStart={() => { interactionRef.current.active = true; }} onEnd={() => { interactionRef.current.active = false; interactionRef.current.lastInteraction = performance.now(); }} />
      <EffectComposer><Bloom intensity={0.7} luminanceThreshold={0.28} mipmapBlur radius={0.65} /></EffectComposer>
    </Canvas>
  );
}
