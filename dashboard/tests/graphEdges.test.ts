import assert from "node:assert/strict";

import type { GraphEdge } from "../src/types.ts";
import { edgesForRender, edgesForVisibility } from "../src/graphEdges.ts";

const semantic = (source: string, target: string, sim: number): GraphEdge => ({ source, target, sim, kind: "semantic" });
const explicit: GraphEdge = { source: "a", target: "d", sim: 0.8, kind: "explicit", relation: "blocked_by" };

// "a" and "e" each have 4 semantic neighbors; a-e is the weakest edge on
// BOTH sides (rank 4 of 4), so it should be dropped by the top-3 cull while
// every other edge (rank <= 3 on at least one side) survives.
const ab = semantic("a", "b", 0.95);
const ac = semantic("a", "c", 0.9);
const ad = semantic("a", "d", 0.85);
const ae = semantic("a", "e", 0.3);
const ef = semantic("e", "f", 0.93);
const eg = semantic("e", "g", 0.88);
const eh = semantic("e", "h", 0.8);

const edges = [ab, ac, ad, ae, ef, eg, eh, explicit];

const rendered = edgesForRender(edges);
assert.deepEqual(rendered, [ab, ac, ad, ef, eg, eh, explicit]);
assert.equal(rendered.includes(ae), false);
assert.equal(rendered.filter((edge) => edge.kind === "explicit").length, 1);
assert.deepEqual(edgesForVisibility(edges, false), [explicit]);
assert.deepEqual(edgesForVisibility(edges, true), edges);
