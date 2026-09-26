const endpoint = import.meta.env.VITE_CHRONICLE_MCP_URL || "/mcp";
const protocolVersion = "2025-06-18";
let requestId = 0;
let initialized = false;

type RpcResponse = { result?: any; error?: { message?: string } };

async function postRpc(method: string, params: Record<string, unknown>, id: number | null): Promise<RpcResponse> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "mcp-protocol-version": protocolVersion,
    },
    body: JSON.stringify({ jsonrpc: "2.0", ...(id === null ? {} : { id }), method, params }),
  });
  if (!response.ok) throw new Error(`MCP HTTP ${response.status}`);
  return response.json() as Promise<RpcResponse>;
}

async function initialize() {
  if (initialized) return;
  await postRpc("initialize", {
    protocolVersion,
    capabilities: {},
    clientInfo: { name: "chronicle-dashboard", version: "0.1.0" },
  }, ++requestId);
  initialized = true;
}

function decode(result: RpcResponse): unknown {
  if (result.error) throw new Error(result.error.message || "MCP request failed");
  const body = result.result;
  if (body?.isError) {
    const message = body.content?.find((item: { type?: string }) => item.type === "text")?.text;
    throw new Error(message || "MCP tool failed");
  }
  if (body?.structuredContent?.result !== undefined) return body.structuredContent.result;
  const text = body?.content?.find((item: { type?: string }) => item.type === "text")?.text;
  if (typeof text === "string") {
    try { return JSON.parse(text); } catch { return text; }
  }
  return body;
}

export async function callTool<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
  await initialize();
  const result = await postRpc("tools/call", { name, arguments: args }, ++requestId);
  return decode(result) as T;
}
