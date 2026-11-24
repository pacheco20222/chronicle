import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { transformSync } from "esbuild";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/components/VaultControls.tsx", import.meta.url), "utf8");
const { code } = transformSync(source, { loader: "tsx", format: "cjs", jsx: "automatic" });
const calls = [];
const confirmations = [];
let accepted = false;
let refreshed = 0;
const exports = {};
const context = {
  module: { exports }, exports,
  window: { confirm: (text) => { confirmations.push(text); return accepted; } },
  require: (name) => {
    if (name === "react") return { useId: () => "hint", useState: (initial) => [initial, () => {}] };
    if (name === "../api/rpc") return { callTool: async (...args) => { calls.push(args); } };
    if (name.startsWith("./ui/")) return new Proxy({}, { get: (_, key) => key });
    return require(name);
  },
};
vm.runInNewContext(code, context);
const { VaultProjectToggle } = context.module.exports;

async function click(mirrored) {
  const element = VaultProjectToggle({
    project: "Demo", vault: { path: "/vault", projects: mirrored ? ["Demo"] : [] },
    running: false, onRefresh: async () => { refreshed += 1; },
  });
  const button = element.props.children[0];
  button.props.onClick();
  await new Promise(setImmediate);
}

await click(true);
assert.deepEqual(confirmations, ["Remove Demo's pages from the Obsidian vault? Your memories are not affected."]);
assert.equal(calls.length, 0, "Cancel must prevent removal");
assert.equal(refreshed, 0, "Cancel must leave toggle idle");
accepted = true;
await click(true);
assert.equal(calls.length, 1);
assert.equal(calls[0][0], "memory_vault_remove_project");
assert.equal(calls[0][1].project, "Demo");
assert.equal(refreshed, 1);
await click(false);
assert.equal(confirmations.length, 2, "Opt-in must not ask for removal confirmation");
assert.equal(calls[1][0], "memory_vault_add_project");
assert.equal(refreshed, 2);
console.log("Vault toggle: cancel, confirm, and opt-in passed");
