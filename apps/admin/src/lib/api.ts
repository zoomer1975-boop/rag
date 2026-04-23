const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/rag/api/v1";

export async function apiFetch<T>(
  path: string,
  apiKey: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ─── Tenant management (admin endpoints — routed through server-side proxy) ───
//
// 클라이언트는 /api/admin/... Next.js 프록시를 통해 FastAPI를 호출합니다.
// ADMIN_API_TOKEN은 서버 사이드에서만 읽으므로 빌드 시점 이슈가 없습니다.

// basePath가 /rag/admin 이므로 Next.js API 라우트는 브라우저에서
// /rag/admin/api/admin/... 경로로 접근해야 함
const ADMIN_PROXY = "/rag/admin/api/admin";

export async function adminFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${ADMIN_PROXY}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function uploadTenantIcon(tenantId: number, file: File): Promise<Tenant> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${ADMIN_PROXY}/tenants/${tenantId}/icon`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json();
}

export async function deleteTenantIcon(tenantId: number): Promise<Tenant> {
  return adminFetch<Tenant>(`/tenants/${tenantId}/icon`, { method: "DELETE" });
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Tenant {
  id: number;
  name: string;
  api_key: string;
  is_active: boolean;
  lang_policy: string;
  default_lang: string;
  allowed_langs: string;
  allowed_domains: string;
  widget_config: WidgetConfig;
  system_prompt: string | null;
  default_url_refresh_hours: number;
  has_langsmith: boolean;
  clarification_enabled: boolean;
  clarification_config: Record<string, unknown> | null;
}

export interface WidgetConfig {
  primary_color: string;
  greeting: string;
  position: string;
  title: string;
  placeholder: string;
  quick_replies?: string[];
  button_icon_url?: string;
}

export interface Document {
  id: number;
  title: string;
  source_type: string;
  source_url: string | null;
  status: string;
  chunk_count: number;
  error_message: string | null;
  refresh_interval_hours: number;
  last_refreshed_at: string | null;
  next_refresh_at: string | null;
}

export interface Stats {
  document_count: number;
  chunk_count: number;
  conversation_count: number;
  message_count: number;
}

export interface Conversation {
  id: number;
  session_id: string;
  lang_code: string;
  created_at: string;
  message_count: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  sources: Array<{ title: string; url: string }> | null;
  created_at: string;
}

export interface ApiTool {
  id: number;
  tenant_id: number;
  name: string;
  description: string;
  http_method: string;
  url_template: string;
  headers_masked: Record<string, string> | null;
  query_params_schema: Record<string, unknown> | null;
  body_schema: Record<string, unknown> | null;
  response_jmespath: string | null;
  timeout_seconds: number;
  is_active: boolean;
}

export interface SubAdmin {
  id: number;
  name: string;
  username: string;
  is_active: boolean;
  allowed_ips: string;
  created_at: string;
  tenant_ids: number[];
}

export interface BoilerplatePattern {
  id: number;
  tenant_id: number;
  pattern_type: "literal" | "regex";
  pattern: string;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface GraphNode {
  id: number;
  name: string;
  entity_type: string;
  description: string;
  degree: number;
  chunk_count: number;
}

export interface GraphEdge {
  id: number;
  source: number;
  target: number;
  description: string;
  keywords: string[];
  weight: number;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface GraphSummary {
  entity_count: number;
  relationship_count: number;
  entity_types: { type: string; count: number }[];
}

export async function fetchGraphSummary(apiKey: string): Promise<GraphSummary> {
  return apiFetch<GraphSummary>("/graph/summary", apiKey);
}

export async function fetchGraph(
  apiKey: string,
  params?: { types?: string[]; q?: string; limit?: number }
): Promise<GraphPayload> {
  const sp = new URLSearchParams();
  params?.types?.forEach((t) => sp.append("types", t));
  if (params?.q) sp.set("q", params.q);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return apiFetch<GraphPayload>(`/graph/${qs ? `?${qs}` : ""}`, apiKey);
}

export async function fetchNeighborhood(
  apiKey: string,
  entityId: number,
  params?: { depth?: number; limit?: number }
): Promise<GraphPayload> {
  const sp = new URLSearchParams();
  if (params?.depth) sp.set("depth", String(params.depth));
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return apiFetch<GraphPayload>(
    `/graph/neighborhood/${entityId}${qs ? `?${qs}` : ""}`,
    apiKey
  );
}

export interface Chunk {
  id: number;
  chunk_index: number;
  content: string;
  created_at: string;
}

export interface ChunkListResponse {
  items: Chunk[];
  total: number;
  limit: number;
  offset: number;
}

export async function listDocumentChunks(
  apiKey: string,
  docId: number,
  params?: { limit?: number; offset?: number }
): Promise<ChunkListResponse> {
  const limit = params?.limit ?? 50;
  const offset = params?.offset ?? 0;
  return apiFetch<ChunkListResponse>(
    `/ingest/documents/${docId}/chunks?limit=${limit}&offset=${offset}`,
    apiKey
  );
}

export interface BoilerplatePatternCreate {
  pattern_type: "literal" | "regex";
  pattern: string;
  description?: string;
  is_active?: boolean;
  sort_order?: number;
}

export interface BoilerplatePatternUpdate {
  pattern_type?: "literal" | "regex";
  pattern?: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
}

export interface BoilerplatePreviewResponse {
  original: string;
  applied: string;
  removed_count: number;
}

export interface ServiceStatus {
  status: "ok" | "degraded" | "down";
  latency_ms: number | null;
  message: string | null;
  enabled: boolean;
}

export interface SystemHealth {
  postgresql: ServiceStatus;
  redis: ServiceStatus;
  llm: ServiceStatus;
  embedding: ServiceStatus;
  safeguard: ServiceStatus;
  ner: ServiceStatus;
  checked_at: string;
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  return adminFetch<SystemHealth>("/admin/system/health");
}

export async function listBoilerplatePatterns(tenantId: number): Promise<BoilerplatePattern[]> {
  return adminFetch<BoilerplatePattern[]>(`/tenants/${tenantId}/boilerplate`);
}

export async function createBoilerplatePattern(
  tenantId: number,
  data: BoilerplatePatternCreate
): Promise<BoilerplatePattern> {
  return adminFetch<BoilerplatePattern>(`/tenants/${tenantId}/boilerplate`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateBoilerplatePattern(
  tenantId: number,
  patternId: number,
  data: BoilerplatePatternUpdate
): Promise<BoilerplatePattern> {
  return adminFetch<BoilerplatePattern>(`/tenants/${tenantId}/boilerplate/${patternId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteBoilerplatePattern(tenantId: number, patternId: number): Promise<void> {
  return adminFetch<void>(`/tenants/${tenantId}/boilerplate/${patternId}`, { method: "DELETE" });
}

export async function previewBoilerplatePatterns(
  tenantId: number,
  sampleText: string
): Promise<BoilerplatePreviewResponse> {
  return adminFetch<BoilerplatePreviewResponse>(`/tenants/${tenantId}/boilerplate/preview`, {
    method: "POST",
    body: JSON.stringify({ sample_text: sampleText }),
  });
}
