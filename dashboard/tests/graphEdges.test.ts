import assert from "node:assert/strict";

import type { GraphEdge } from "../src/types.ts";
import { edgesForRender, edgesForVisibility } from "../src/graphEdges.ts";

const semantic = (source: string, target: string, sim: number): GraphEdge => ({ source, target, sim, kind: "semantic" });
const explicit: GraphEdge = { source: "a", target: "d", sim: 0.8, kind: "explicit", relation: "blocked_by" };

const edges = [
  semantic("a", "b", 0.95),
  semantic("a", "c", 0.85),
  semantic("a", "d", 0.75),
  semantic("b", "c", 0.9),
  semantic("b", "d", 0.65),
  semantic("c", "d", 0.55),
  explicit,
];

const rendered = edgesForRender(edges);
assert.deepEqual(rendered, [edges[0], edges[1], edges[2], edges[3], edges[4], explicit]);
assert.equal(rendered.filter((edge) => edge.kind === "explicit").length, 1);
assert.deepEqual(edgesForVisibility(edges, false), [explicit]);
assert.deepEqual(edgesForVisibility(edges, true), edges);
