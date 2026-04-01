import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { Type, type Static, type TSchema } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";

type Json = Record<string, unknown>;

type PlannerRequest = {
  prompt: string;
  history?: Array<Record<string, unknown>>;
  current_scene?: Record<string, unknown> | null;
  recent_history?: Array<Record<string, unknown>>;
  allowed_assets?: string[];
  asset_resolution?: Record<string, unknown>;
  asset_registry?: Record<string, unknown>;
  layout_templates?: Record<string, unknown>;
  asset_specs?: Array<Record<string, unknown>>;
};

type ToolTraceItem = {
  tool: string;
  args: Record<string, unknown>;
  resultPreview: string;
};

type SidecarTool<T extends TSchema> = AgentTool<T, Json> & {
  run: (args: Static<T>, request: PlannerRequest) => Promise<Json>;
};

const PORT = Number.parseInt(process.env.PORT || "8787", 10);
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || "";
const TEXT_MODEL = process.env.OPENROUTER_TEXT_MODEL || process.env.TEXT_MODEL || "openai/gpt-4.1-mini";
const REVIEW_MODEL = process.env.OPENROUTER_REVIEW_MODEL || process.env.REVIEW_MODEL || TEXT_MODEL;
const OPENROUTER_URL = process.env.OPENROUTER_URL || "https://openrouter.ai/api/v1/chat/completions";

const SYSTEM_PROMPT = `You are a planning agent for an automotive pictogram generator.
Use tools when the prompt contains typos, synonyms, or ambiguous asset names.
Always search the asset catalog when you are not fully certain about an asset name.
Produce JSON only.
Return a scene plan with symbolic placement, not pixel coordinates.

Required output shape:
{
  "version": "odd.scene.v1",
  "title": "short title",
  "prompt": "original user prompt",
  "warnings": [],
  "layoutPlan": {
    "layout": { "template": "straight_road|crosswalk_road|intersection|t_junction|roundabout|highway_3_lane" },
    "static": [
      {"id": "tl1", "kind": "traffic_light", "anchor": "roadside_top"}
    ],
    "dynamic": [
      {"id": "car1", "kind": "car", "lane": "lane_2", "laneIndex": 2, "slot": 1, "slotCount": 4, "heading": "forward"}
    ],
    "annotations": []
  }
}

Rules:
- Use only assets that exist in the catalog or placeholders.
- Prefer laneIndex + slot for vehicles on multi-lane templates.
- slot means ordinal position along the lane, not coordinates.
- Use anchors for static assets.
- If a prompt term is misspelled, use the search_assets tool and resolve it to the closest valid asset.
- Keep the scene compact and editable.
- Roads/layout must come from layoutPlan.layout.template.`;

const REVIEW_SYSTEM_PROMPT = `You are a multimodal reviewer for automotive pictogram scenes.
You receive:
- the original prompt
- a symbolic layout JSON
- a rendered PNG of the first pass

Inspect whether the first pass matches the prompt and whether assets are placed coherently.
Focus on mistakes such as:
- wrong asset chosen
- missing asset
- pedestrian not on crosswalk when prompt implies it
- vehicle in wrong lane or wrong ordering slot
- traffic lights or static assets attached to poor anchors
- scene too cluttered or semantically inconsistent

Output JSON only.
If the first pass is acceptable, return:
{
  "approved": true,
  "issues": [],
  "summary": "short review summary"
}

If changes are needed, return:
{
  "approved": false,
  "issues": ["issue 1", "issue 2"],
  "summary": "short review summary",
  "layoutPlan": { ... corrected symbolic layout plan ... }
}

Do not output prose outside JSON.
Do not output pixel coordinates unless unavoidable.
Prefer correcting laneIndex, slot, slotCount, lane, anchors, relations, and template choice.`;

const searchAssetsSchema = Type.Object({
  query: Type.String({ description: "Asset name, typo, or concept to search for" }),
  limit: Type.Optional(Type.Number({ description: "Maximum number of matches", default: 8 })),
});

const getAssetDetailsSchema = Type.Object({
  kind: Type.String({ description: "Canonical asset kind to inspect" }),
});

const listTemplatesSchema = Type.Object({});

function normalize(text: unknown): string {
  return String(text ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

function levenshtein(a: string, b: string): number {
  const aa = normalize(a);
  const bb = normalize(b);
  const dp = Array.from({ length: aa.length + 1 }, () => new Array<number>(bb.length + 1).fill(0));
  for (let i = 0; i <= aa.length; i += 1) dp[i][0] = i;
  for (let j = 0; j <= bb.length; j += 1) dp[0][j] = j;
  for (let i = 1; i <= aa.length; i += 1) {
    for (let j = 1; j <= bb.length; j += 1) {
      const cost = aa[i - 1] === bb[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }
  return dp[aa.length][bb.length];
}

function getAssetSpecs(request: PlannerRequest): Array<Record<string, unknown>> {
  return Array.isArray(request.asset_specs) ? request.asset_specs : [];
}

function scoreAsset(query: string, asset: Record<string, unknown>): number {
  const q = normalize(query);
  const kind = normalize(asset.kind);
  const label = normalize(asset.label);
  const category = normalize(asset.category);
  if (!q) return 0;
  if (q === kind || q === label) return 100;
  if (kind.includes(q) || label.includes(q)) return 90;
  if (q.includes(kind) || q.includes(label)) return 80;
  const lev = Math.min(levenshtein(q, kind), levenshtein(q, label));
  const fuzzy = Math.max(0, 70 - lev * 10);
  return Math.max(fuzzy, category.includes(q) ? 45 : 0);
}

const tools: Array<SidecarTool<any>> = [
  {
    name: "search_assets",
    label: "Search Assets",
    description: "Search the asset catalog for exact, similar, or typo-tolerant asset matches.",
    parameters: searchAssetsSchema,
    execute: async (_toolCallId: string, params: Static<typeof searchAssetsSchema>) => ({ content: [{ type: "text", text: JSON.stringify(params) }], details: params as Json }),
    run: async (args: Static<typeof searchAssetsSchema>, request: PlannerRequest) => {
      const matches = getAssetSpecs(request)
        .map((asset) => ({ asset, score: scoreAsset(args.query, asset) }))
        .filter((entry) => entry.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, Math.max(1, Math.min(Number(args.limit ?? 8), 12)))
        .map((entry) => ({
          kind: entry.asset.kind,
          label: entry.asset.label,
          category: entry.asset.category,
          placement: entry.asset.placement,
          allowedPlacements: entry.asset.allowedPlacements,
          score: entry.score,
        }));
      return { query: args.query, matches };
    },
  },
  {
    name: "get_asset_details",
    label: "Get Asset Details",
    description: "Return full metadata for a single asset kind.",
    parameters: getAssetDetailsSchema,
    execute: async (_toolCallId: string, params: Static<typeof getAssetDetailsSchema>) => ({ content: [{ type: "text", text: JSON.stringify(params) }], details: params as Json }),
    run: async (args: Static<typeof getAssetDetailsSchema>, request: PlannerRequest) => {
      const item = getAssetSpecs(request).find((asset) => String(asset.kind) === args.kind);
      return item ? { found: true, asset: item } : { found: false, kind: args.kind };
    },
  },
  {
    name: "list_layout_templates",
    label: "List Layout Templates",
    description: "List available symbolic road/layout templates and their lanes/anchors.",
    parameters: listTemplatesSchema,
    execute: async () => ({ content: [{ type: "text", text: "{}" }], details: {} }),
    run: async (_args: Static<typeof listTemplatesSchema>, request: PlannerRequest) => {
      return request.layout_templates && typeof request.layout_templates === "object"
        ? (request.layout_templates as Json)
        : { templates: [] };
    },
  },
];

function toolToOpenRouterSchema(tool: SidecarTool<any>) {
  return {
    type: "function",
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters,
    },
  };
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: any[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf-8");
}

function writeJson(res: ServerResponse, statusCode: number, payload: unknown): void {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

function extractJsonObject(text: string): Record<string, unknown> {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const match = trimmed.match(/\{[\s\S]*\}/);
  if (!match) throw new Error("No JSON object found in sidecar response");
  return JSON.parse(match[0]) as Record<string, unknown>;
}

function summarizeResult(result: Json): string {
  const text = JSON.stringify(result);
  return text.length > 240 ? `${text.slice(0, 240)}...` : text;
}

async function callOpenRouter(messages: Array<Record<string, unknown>>) {
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": process.env.OPENROUTER_REFERER || "http://planner-sidecar",
      "X-Title": "Pictogram Planner Sidecar",
    },
    body: JSON.stringify({
      model: TEXT_MODEL,
      temperature: 0.2,
      messages,
      tools: tools.map(toolToOpenRouterSchema),
      tool_choice: "auto",
    }),
  });

  if (!response.ok) {
    throw new Error(`Planner sidecar OpenRouter error: ${await response.text()}`);
  }
  return response.json() as Promise<Record<string, any>>;
}

async function callReviewModel(messages: Array<Record<string, unknown>>) {
  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": process.env.OPENROUTER_REFERER || "http://planner-sidecar",
      "X-Title": "Pictogram Planner Reviewer",
    },
    body: JSON.stringify({
      model: REVIEW_MODEL,
      temperature: 0.1,
      messages,
    }),
  });

  if (!response.ok) {
    throw new Error(`Reviewer sidecar OpenRouter error: ${await response.text()}`);
  }
  return response.json() as Promise<Record<string, any>>;
}

async function executeToolCall(
  toolName: string,
  args: Record<string, unknown>,
  request: PlannerRequest,
): Promise<Json> {
  const tool = tools.find((candidate) => candidate.name === toolName);
  if (!tool) return { error: `Unknown tool: ${toolName}` };
  return tool.run(args, request);
}

async function planScene(request: PlannerRequest) {
  const toolTrace: ToolTraceItem[] = [];
  const userPayload = {
    prompt: request.prompt,
    current_scene: request.current_scene ?? null,
    recent_history: request.recent_history ?? request.history ?? [],
    allowed_assets: request.allowed_assets ?? [],
    asset_resolution: request.asset_resolution ?? {},
    asset_registry: request.asset_registry ?? {},
    layout_templates: request.layout_templates ?? {},
    asset_specs: request.asset_specs ?? [],
  };

  const messages: Array<Record<string, unknown>> = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: JSON.stringify(userPayload) },
  ];

  for (let turn = 0; turn < 8; turn += 1) {
    const data = await callOpenRouter(messages);
    const message = data.choices?.[0]?.message ?? {};
    const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];

    if (toolCalls.length > 0) {
      messages.push({
        role: "assistant",
        content: message.content ?? "",
        tool_calls: toolCalls,
      });

      for (const toolCall of toolCalls) {
        const toolName = String(toolCall?.function?.name ?? "");
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(String(toolCall?.function?.arguments ?? "{}"));
        } catch {
          args = {};
        }
        const result = await executeToolCall(toolName, args, request);
        toolTrace.push({ tool: toolName, args, resultPreview: summarizeResult(result) });
        messages.push({
          role: "tool",
          tool_call_id: String(toolCall.id ?? toolName),
          name: toolName,
          content: JSON.stringify(result),
        });
      }
      continue;
    }

    const content = typeof message.content === "string"
      ? message.content
      : Array.isArray(message.content)
        ? message.content.map((item: any) => item?.text ?? "").join("\n")
        : "";
    const rawJson = extractJsonObject(content);
    return {
      raw_text: content,
      raw_json: rawJson,
      tool_trace: toolTrace,
    };
  }

  throw new Error("Planner sidecar exceeded tool-call turn limit");
}

async function reviewScene(request: Record<string, unknown>) {
  const content: Array<Record<string, unknown>> = [
    {
      type: "text",
      text: JSON.stringify({
        prompt: request.prompt ?? "",
        layoutPlan: request.layoutPlan ?? null,
        scene: request.scene ?? null,
        warnings: request.warnings ?? [],
      }),
    },
  ];
  if (typeof request.image === "string" && request.image.startsWith("data:image/")) {
    content.push({ type: "image_url", image_url: { url: request.image } });
  }

  const messages: Array<Record<string, unknown>> = [
    { role: "system", content: REVIEW_SYSTEM_PROMPT },
    { role: "user", content },
  ];
  const data = await callReviewModel(messages);
  const message = data.choices?.[0]?.message ?? {};
  const body = typeof message.content === "string"
    ? message.content
    : Array.isArray(message.content)
      ? message.content.map((item: any) => item?.text ?? "").join("\n")
      : "";
  return {
    raw_text: body,
    raw_json: extractJsonObject(body),
  };
}

const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    if (req.method === "GET" && url.pathname === "/health") {
      writeJson(res, 200, { ok: true, model: TEXT_MODEL, reviewModel: REVIEW_MODEL, tools: tools.map((tool) => tool.name) });
      return;
    }

    if (req.method === "POST" && url.pathname === "/plan") {
      if (!OPENROUTER_API_KEY) {
        writeJson(res, 500, { error: "OPENROUTER_API_KEY is not configured in planner sidecar" });
        return;
      }
      const body = await readBody(req);
      const payload = JSON.parse(body || "{}") as PlannerRequest;
      const result = await planScene(payload);
      writeJson(res, 200, result);
      return;
    }

    if (req.method === "POST" && url.pathname === "/review") {
      if (!OPENROUTER_API_KEY) {
        writeJson(res, 500, { error: "OPENROUTER_API_KEY is not configured in planner sidecar" });
        return;
      }
      const body = await readBody(req);
      const payload = JSON.parse(body || "{}") as Record<string, unknown>;
      const result = await reviewScene(payload);
      writeJson(res, 200, result);
      return;
    }

    writeJson(res, 404, { error: "Not found" });
  } catch (error) {
    writeJson(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`planner-sidecar listening on ${PORT}`);
});
