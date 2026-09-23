import type { GraphEdge } from "./types";

const SEMANTIC_RENDER_NEIGHBORS = 2;

export function edgesForVisibility(edges: GraphEdge[], showSemanticEdges: boolean) {
  return showSemanticEdges ? edges : edges.filter((edge) => edge.kind === "explicit");
}

function edgeKey(edge: GraphEdge) {
  return `${edge.source}\u0000${edge.target}`;
}

export function edgesForRender(edges: GraphEdge[]) {
  const semanticByNode = new Map<string, GraphEdge[]>();

  for (const edge of edges) {
    if (edge.kind !== "semantic") continue;
    const sourceEdges = semanticByNode.get(edge.source) || [];
    const targetEdges = semanticByNode.get(edge.target) || [];
    sourceEdges.push(edge);
    targetEdges.push(edge);
    semanticByNode.set(edge.source, sourceEdges);
    semanticByNode.set(edge.target, targetEdges);
  }

  const retainedSemantic = new Set<GraphEdge>();
  for (const incidentEdges of semanticByNode.values()) {
    incidentEdges
      .slice()
      .sort((a, b) => b.sim - a.sim || edgeKey(a).localeCompare(edgeKey(b)))
      .slice(0, SEMANTIC_RENDER_NEIGHBORS)
      .forEach((edge) => retainedSemantic.add(edge));
  }

  return edges.filter((edge) => edge.kind === "explicit" || retainedSemantic.has(edge));
}
