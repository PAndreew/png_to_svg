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
  geometry_draft?: Record<string, unknown> | null;
  planning_phase?: string;
};

type ToolTraceItem = {
  phase?: string;
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

const GEOMETRY_SYSTEM_PROMPT = `You are the road-geometry planning phase for an automotive pictogram generator.
Use tools when the prompt contains typos, synonyms, or ambiguous asset names.
Always search the asset catalog when you are not fully certain about an asset name.
Produce JSON only.
Return a scene plan with a hybrid segment-grid plus road-centerline layout, not pixel coordinates.

Required output shape:
{
  "version": "odd.scene.v1",
  "title": "short title",
  "prompt": "original user prompt",
  "warnings": [],
  "layoutPlan": {
    "map": { "cols": 10, "rows": 10 },
    "topology": {
      "roads": [
        {"id": "arterial_main", "roadRole": "arterial", "fromJunction": "west_entry", "toJunction": "east_entry", "laneCount": 4, "widthSegments": 3.5, "points": [{"col": 0, "row": 4}, {"col": 11, "row": 4}], "props": {}}
      ],
      "junctions": [
        {"id": "west_entry", "kind": "entry", "col": 0, "row": 4, "connectedRoadIds": ["arterial_main"], "control": null, "props": {}}
      ]
    },
    "geometry": [
      {"id": "arterial_main", "kind": "road", "points": [{"col": 0, "row": 4}, {"col": 11, "row": 4}], "rowSpan": 4, "laneCount": 4, "layer": 1, "props": {"roadRole": "arterial"}},
      {"id": "crosswalk1", "kind": "crosswalk", "col": 5, "row": 3, "colSpan": 1, "rowSpan": 4, "layer": 3}
    ],
    "environment": [
      {"id": "yield1", "kind": "traffic_light|placeholder", "col": 8, "row": 2, "rotation": 0, "layer": 4}
    ],
    "actors": [],
    "annotations": []
  }
}

Rules:
- Use only assets that exist in the catalog or placeholders.
- Choose map size between 10x10 and 15x15 based on scene complexity.
- First solve only geometry and controls. Leave actors empty in this phase.
- For any non-trivial network, include layoutPlan.topology with canonical road ids and junction connectivity before refining geometry.
- Use geometry rectangles for simple roads and use geometry points for arterials, connectors, curves, and staggered side roads.
- A road geometry item may include points, laneCount, rowSpan, and props.roadRole.
- Keep topology road ids aligned with geometry road ids.
- Use layer bands: arterial/base roads 1, connector roads 2, markings/crosswalks 3, controls 4, environment 5.
- For a non-signalized staggered intersection, prefer one arterial road path and separate side-road connector paths with different ids.
- If a prompt term is misspelled, use the search_assets tool and resolve it to the closest valid asset.
- Keep the scene compact and editable.
- Roads/layout must come from layoutPlan.geometry, not pixel coordinates.`;

const OBJECT_SYSTEM_PROMPT = `You are the object-placement phase for an automotive pictogram generator.
You receive an already planned road geometry draft.
Preserve the map and geometry unless there is a clear mistake.
Produce JSON only.
Return the same scene schema, but now add actors and optional annotations using the same layoutPlan language.

Rules:
- Keep layoutPlan.map and layoutPlan.geometry from the geometry draft whenever possible.
- Preserve layoutPlan.topology and use its road ids as the canonical ids for actor pathId.
- Place moving actors with either direct grid placement or path-following using pathId + s + laneIndex.
- When a vehicle belongs on a road, prefer pathId + s + laneIndex over vague language.
- Cars usually occupy 2x1 segments, trucks and buses 3x1, pedestrians 1x1.
- Actors should usually use layer 10. Annotations should usually use layer 20.
- Preserve environment/control items unless they conflict with the prompt.
- For crossing pedestrians, place them on crosswalk geometry, not on arbitrary road lanes.
- Output the full final JSON object, not a diff.`;

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
- vehicle placed in the wrong grid segment or with the wrong rotation
- vehicle attached to the wrong road path or wrong progress along the path
- arterial road missing, broken, or incorrectly represented in the geometry phase
- topology road graph missing connector roads, minor-road branches, or junction connectivity implied by the prompt
- traffic lights or static assets attached to poor grid segments
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
  "layoutPlan": { ... corrected grid layout plan ... }
}

Do not output prose outside JSON.
Do not output pixel coordinates unless unavoidable.
Prefer correcting topology connectivity, map size, geometry points, road roles, object pathId/s/laneIndex, grid segments, spans, rotation, and layers.`;

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

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

function hasOnlyHybridCollections(value: Record<string, unknown>): boolean {
  return ["topology", "geometry", "environment", "actors", "annotations"].some((key) => key in value);
}

function validateTopologyPlan(
  value: unknown,
): { ok: true; normalized: Record<string, unknown> } | { ok: false; error: string } {
  const topology = asObject(value);
  if (!topology) {
    return { ok: false, error: "layoutPlan.topology must be a JSON object when provided." };
  }
  const roads = asArray(topology.roads);
  const junctions = asArray(topology.junctions);
  if (!roads || !junctions) {
    return { ok: false, error: "layoutPlan.topology must contain roads and junctions arrays." };
  }
  for (const road of roads) {
    const roadObject = asObject(road);
    if (!roadObject) {
      return { ok: false, error: "Each topology road must be a JSON object." };
    }
    if (!String(roadObject.id ?? "").trim()) {
      return { ok: false, error: "Each topology road must include a non-empty id." };
    }
    const points = asArray(roadObject.points);
    if (!points || points.length < 2) {
      return { ok: false, error: `Topology road ${String(roadObject.id ?? "")} must include at least two points.` };
    }
  }
  for (const junction of junctions) {
    const junctionObject = asObject(junction);
    if (!junctionObject) {
      return { ok: false, error: "Each topology junction must be a JSON object." };
    }
    if (!String(junctionObject.id ?? "").trim()) {
      return { ok: false, error: "Each topology junction must include a non-empty id." };
    }
  }
  return {
    ok: true,
    normalized: {
      roads,
      junctions,
    },
  };
}

function validateHybridLayoutPlan(
  value: unknown,
  phase: "geometry" | "objects" | "review",
): { ok: true; normalized: Record<string, unknown> } | { ok: false; error: string } {
  const plan = asObject(value);
  if (!plan) {
    return { ok: false, error: "layoutPlan must be a JSON object." };
  }

  if ("elements" in plan) {
    return {
      ok: false,
      error: "Do not use layoutPlan.elements. Use layoutPlan.geometry, layoutPlan.environment, layoutPlan.actors, and layoutPlan.annotations.",
    };
  }

  const mapValue = asObject(plan.map);
  if (!mapValue) {
    return { ok: false, error: "layoutPlan.map must be present with cols and rows." };
  }

  const cols = Number(mapValue.cols);
  const rows = Number(mapValue.rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols < 10 || cols > 15 || rows < 10 || rows > 15) {
    return { ok: false, error: "layoutPlan.map.cols and layoutPlan.map.rows must be numbers between 10 and 15." };
  }

  const geometry = asArray(plan.geometry);
  const environment = asArray(plan.environment);
  const actors = asArray(plan.actors);
  const annotations = asArray(plan.annotations);
  if (!geometry || !environment || !actors || !annotations) {
    return {
      ok: false,
      error: "layoutPlan must contain geometry, environment, actors, and annotations arrays, even if some are empty.",
    };
  }

  const topologyValue = plan.topology;
  let topology: Record<string, unknown> | undefined;
  if (topologyValue !== undefined) {
    const topologyValidation = validateTopologyPlan(topologyValue);
    if (!topologyValidation.ok) {
      return { ok: false, error: topologyValidation.error };
    }
    topology = topologyValidation.normalized;
  }

  if (phase === "geometry" && actors.length > 0) {
    return { ok: false, error: "Geometry phase must leave layoutPlan.actors empty." };
  }

  if (geometry.length === 0 && (!topology || !Array.isArray(topology.roads) || topology.roads.length === 0)) {
    return { ok: false, error: "layoutPlan.geometry must contain at least one road item, or layoutPlan.topology.roads must describe the road network." };
  }

  return {
    ok: true,
    normalized: {
      ...plan,
      map: { cols, rows },
      ...(topology ? { topology } : {}),
      geometry,
      environment,
      actors,
      annotations,
    },
  };
}

function validatePhaseSceneEnvelope(
  rawJson: Record<string, unknown>,
  phase: "geometry" | "objects",
): { ok: true; normalized: Record<string, unknown> } | { ok: false; error: string } {
  const wrappedPlan = asObject(rawJson.layoutPlan);
  if (!wrappedPlan) {
    if (hasOnlyHybridCollections(rawJson)) {
      return {
        ok: false,
        error: "Return a full scene object with the hybrid plan nested under layoutPlan. Do not place map/geometry/environment/actors at the top level.",
      };
    }
    return { ok: false, error: "Response must contain layoutPlan." };
  }

  const validatedPlan = validateHybridLayoutPlan(wrappedPlan, phase);
  if (!validatedPlan.ok) {
    return { ok: false, error: validatedPlan.error };
  }

  return {
    ok: true,
    normalized: {
      version: String(rawJson.version ?? "odd.scene.v1"),
      title: String(rawJson.title ?? "ODD pictogram"),
      prompt: String(rawJson.prompt ?? ""),
      warnings: Array.isArray(rawJson.warnings) ? rawJson.warnings : [],
      layoutPlan: validatedPlan.normalized,
    },
  };
}

function validateReviewPayload(
  rawJson: Record<string, unknown>,
): { ok: true; normalized: Record<string, unknown> } | { ok: false; error: string } {
  const approved = Boolean(rawJson.approved ?? true);
  const issues = Array.isArray(rawJson.issues) ? rawJson.issues : [];
  const summary = String(rawJson.summary ?? "");
  if (approved) {
    return { ok: true, normalized: { approved: true, issues, summary } };
  }
  const layoutPlanValue = asObject(rawJson.layoutPlan);
  if (!layoutPlanValue) {
    return { ok: false, error: "When approved is false, review output must include layoutPlan." };
  }
  const validatedPlan = validateHybridLayoutPlan(layoutPlanValue, "review");
  if (!validatedPlan.ok) {
    return { ok: false, error: validatedPlan.error };
  }
  return {
    ok: true,
    normalized: {
      approved: false,
      issues,
      summary,
      layoutPlan: validatedPlan.normalized,
    },
  };
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

async function runPlanningPhase(
  phase: string,
  systemPrompt: string,
  request: PlannerRequest,
  userPayload: Record<string, unknown>,
) {
  const toolTrace: ToolTraceItem[] = [];
  const messages: Array<Record<string, unknown>> = [
    { role: "system", content: systemPrompt },
    { role: "user", content: JSON.stringify(userPayload) },
  ];
  let validationRetries = 0;

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
        toolTrace.push({ phase, tool: toolName, args, resultPreview: summarizeResult(result) });
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
    const phaseValidation = validatePhaseSceneEnvelope(rawJson, phase === "geometry" ? "geometry" : "objects");
    if (!phaseValidation.ok) {
      validationRetries += 1;
      if (validationRetries >= 3) {
        throw new Error(`${phase} planner phase produced invalid schema after retries: ${phaseValidation.error}`);
      }
      messages.push({ role: "assistant", content });
      messages.push({
        role: "user",
        content: `Schema validation error: ${phaseValidation.error}\nRegenerate the full JSON now. Keep all valid intent, but strictly follow the required schema and return JSON only.`,
      });
      continue;
    }
    return {
      raw_text: content,
      raw_json: phaseValidation.normalized,
      tool_trace: toolTrace,
    };
  }

  throw new Error(`${phase} planner phase exceeded tool-call turn limit`);
}

async function planScene(request: PlannerRequest) {
  const basePayload = {
    prompt: request.prompt,
    current_scene: request.current_scene ?? null,
    recent_history: request.recent_history ?? request.history ?? [],
    allowed_assets: request.allowed_assets ?? [],
    asset_resolution: request.asset_resolution ?? {},
    asset_registry: request.asset_registry ?? {},
    layout_templates: request.layout_templates ?? {},
    asset_specs: request.asset_specs ?? [],
  };

  const geometryPayload = {
    ...basePayload,
    planning_phase: "geometry",
  };
  const geometryResult = await runPlanningPhase("geometry", GEOMETRY_SYSTEM_PROMPT, request, geometryPayload);
  const geometryRaw = geometryResult.raw_json ?? {};
  const geometryLayoutPlan = typeof geometryRaw.layoutPlan === "object" && geometryRaw.layoutPlan
    ? geometryRaw.layoutPlan as Record<string, unknown>
    : geometryRaw;

  const objectPayload = {
    ...basePayload,
    planning_phase: "objects",
    geometry_draft: geometryLayoutPlan,
  };
  const objectRequest: PlannerRequest = { ...request, geometry_draft: geometryLayoutPlan, planning_phase: "objects" };
  const objectResult = await runPlanningPhase("objects", OBJECT_SYSTEM_PROMPT, objectRequest, objectPayload);

  return {
    raw_text: objectResult.raw_text,
    raw_json: objectResult.raw_json,
    tool_trace: [...(geometryResult.tool_trace ?? []), ...(objectResult.tool_trace ?? [])],
    geometry_draft: geometryRaw,
  };
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
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const data = await callReviewModel(messages);
    const message = data.choices?.[0]?.message ?? {};
    const body = typeof message.content === "string"
      ? message.content
      : Array.isArray(message.content)
        ? message.content.map((item: any) => item?.text ?? "").join("\n")
        : "";
    const rawJson = extractJsonObject(body);
    const validation = validateReviewPayload(rawJson);
    if (validation.ok) {
      return {
        raw_text: body,
        raw_json: validation.normalized,
      };
    }
    messages.push({ role: "assistant", content: body });
    messages.push({
      role: "user",
      content: `Schema validation error: ${validation.error}\nRegenerate the review JSON now. Keep the same review intent, but return valid JSON in the required schema only.`,
    });
  }
  throw new Error("Reviewer produced invalid schema after retries");
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
