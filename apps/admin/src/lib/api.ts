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
