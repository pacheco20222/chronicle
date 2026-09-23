export type MemoryType = "decision" | "architecture" | "bug" | "todo" | "note" | "checkpoint" | "overview";
export type MemoryStatus = "active" | "resolved" | "superseded";

export const TYPE_COLORS: Record<MemoryType, string> = {
  decision: "#e7c77a",
  architecture: "#a8b6dc",
  bug: "#e38b7c",
  todo: "#91b9a1",
  note: "#9ab9d8",
  checkpoint: "#e8d9b4",
  overview: "#c5b0d8",
};

export function colorForType(type: string) {
  return TYPE_COLORS[type as MemoryType] || "#b7bfd2";
}

export interface GraphNode {
  id: string;
  project: string;
  type: MemoryType;
  content: string;
  slug?: string | null;
  created_at?: string | null;
  status: MemoryStatus;
  role?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  sim: number;
  kind: "semantic" | "explicit";
  relation?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  k: number;
  current_project?: string | null;
}

export interface ProjectCard {
  name: string;
  paths: string[];
  node_count: number;
  edge_count: number;
  type_counts: Record<string, number>;
}

export interface DashboardSnapshot {
  graph: GraphData;
  projects: ProjectCard[];
  control: {
    qdrant: { healthy: boolean; collection: string; point_count: number | null; error?: string };
    docker: { available: boolean; health: string; name?: string; cpu?: string | null; memory?: string | null };
    mnemo_processes: Array<{ pid: number; cpu_percent: string; rss_kb: number; command: string }>;
    sampled: boolean;
  };
}
