"use client";

import { useEffect, useState } from "react";
import { adminFetch, type ApiTool, type Tenant } from "@/lib/api";
import styles from "./ApiToolsPanel.module.css";

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const DEFAULT_MAX_TOOLS = 10;

interface Props {
  tenant: Tenant;
}

// ─── Form state ───────────────────────────────────────────────────────────────

interface FormState {
  name: string;
  description: string;
  http_method: string;
  url_template: string;
  headers: string;          // JSON text
  query_params_schema: string; // JSON text
  body_schema: string;      // JSON text
  response_jmespath: string;
  timeout_seconds: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  http_method: "GET",
  url_template: "",
  headers: "",
  query_params_schema: "",
  body_schema: "",
  response_jmespath: "",
  timeout_seconds: "10",
};

function toolToForm(t: ApiTool): FormState {
  return {
    name: t.name,
    description: t.description,
    http_method: t.http_method,
    url_template: t.url_template,
    headers: t.headers_masked ? JSON.stringify(t.headers_masked, null, 2) : "",
    query_params_schema: t.query_params_schema
      ? JSON.stringify(t.query_params_schema, null, 2)
      : "",
    body_schema: t.body_schema ? JSON.stringify(t.body_schema, null, 2) : "",
    response_jmespath: t.response_jmespath ?? "",
    timeout_seconds: String(t.timeout_seconds),
  };
}

function tryParseJson(text: string): { value: Record<string, unknown> | null; error: string | null } {
  if (!text.trim()) return { value: null, error: null };
  try {
    return { value: JSON.parse(text), error: null };
  } catch {
    return { value: null, error: "유효한 JSON이 아닙니다." };
  }
}

// ─── Method badge ─────────────────────────────────────────────────────────────

function MethodBadge({ method }: { method: string }) {
  const cls = `${styles.methodBadge} ${styles[method.toLowerCase()] ?? ""}`;
  return <span className={cls}>{method}</span>;
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ApiToolsPanel({ tenant }: Props) {
  const [tools, setTools] = useState<ApiTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null); // null = new
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const maxTools = tenant.max_api_tools ?? DEFAULT_MAX_TOOLS;
  const atLimit = tools.length >= maxTools;

  // JSON validation errors per field
  const headersJson = tryParseJson(form.headers);
  const querySchemaJson = tryParseJson(form.query_params_schema);
  const bodySchemaJson = tryParseJson(form.body_schema);

  const hasSchemaParams = ["POST", "PUT", "PATCH"].includes(form.http_method);

  async function load() {
    setLoading(true);
    try {
      const data = await adminFetch<ApiTool[]>(`/tenants/${tenant.id}/api-tools/`);
      setTools(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [tenant.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function openNew() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setSubmitError(null);
    setShowForm(true);
  }

  function openEdit(tool: ApiTool) {
    setForm(toolToForm(tool));
    setEditingId(tool.id);
    setSubmitError(null);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setSubmitError(null);
  }

  function setField(key: keyof FormState, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (headersJson.error || querySchemaJson.error || bodySchemaJson.error) return;

    setSaving(true);
    setSubmitError(null);
    try {
      const payload: Record<string, unknown> = {
        description: form.description,
        http_method: form.http_method,
        url_template: form.url_template,
        response_jmespath: form.response_jmespath.trim() || null,
        timeout_seconds: Number(form.timeout_seconds),
        headers: headersJson.value,
        query_params_schema: querySchemaJson.value,
        body_schema: bodySchemaJson.value,
      };

      if (editingId === null) {
        payload.name = form.name;
        const created = await adminFetch<ApiTool>(`/tenants/${tenant.id}/api-tools/`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setTools((prev) => [...prev, created]);
      } else {
        const updated = await adminFetch<ApiTool>(
          `/tenants/${tenant.id}/api-tools/${editingId}`,
          { method: "PATCH", body: JSON.stringify(payload) }
        );
        setTools((prev) => prev.map((t) => (t.id === editingId ? updated : t)));
      }
      closeForm();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTool(tool: ApiTool) {
    if (!confirm(`"${tool.name}" 도구를 삭제하시겠습니까?`)) return;
    setDeletingId(tool.id);
    try {
      await adminFetch(`/tenants/${tenant.id}/api-tools/${tool.id}`, { method: "DELETE" });
      setTools((prev) => prev.filter((t) => t.id !== tool.id));
      if (editingId === tool.id) closeForm();
    } finally {
      setDeletingId(null);
    }
  }

  async function toggleActive(tool: ApiTool) {
    setTogglingId(tool.id);
    try {
      const updated = await adminFetch<ApiTool>(
        `/tenants/${tenant.id}/api-tools/${tool.id}`,
        { method: "PATCH", body: JSON.stringify({ is_active: !tool.is_active }) }
      );
      setTools((prev) => prev.map((t) => (t.id === tool.id ? updated : t)));
    } finally {
      setTogglingId(null);
    }
  }

  if (loading) {
    return <p style={{ color: "var(--color-text-muted)", fontSize: 14 }}>불러오는 중…</p>;
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.heading}>Web API 도구</h2>
        <button
          className={styles.btnPrimary}
          onClick={openNew}
          disabled={atLimit || showForm}
        >
          + 새 도구 추가 ({tools.length}/{maxTools})
        </button>
      </div>

      <p style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 20 }}>
        LLM이 채팅 중 외부 API를 직접 호출할 수 있는 도구를 등록합니다.
        등록된 도구는 RAG 응답 생성 시 OpenAI function calling으로 제공됩니다.
      </p>

      {atLimit && !showForm && (
        <div className={styles.limitBanner} role="alert">
          도구 등록 한도({maxTools}개)에 도달했습니다. 기존 도구를 삭제한 후 추가할 수 있습니다.
        </div>
      )}

      {/* ── New / Edit form ── */}
      {showForm && (
        <form className={styles.formBox} onSubmit={submit}>
          <p className={styles.formTitle}>
            {editingId === null ? "새 도구 추가" : "도구 수정"}
          </p>

          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>기본 정보</legend>

            <div className={styles.row2}>
              <div className={styles.field}>
                <label className={styles.label}>이름 *</label>
                <input
                  className={styles.input}
                  value={form.name}
                  onChange={(e) => setField("name", e.target.value)}
                  placeholder="get_weather"
                  pattern="^[a-z][a-z0-9_]{0,63}$"
                  title="소문자 영문으로 시작, 소문자/숫자/언더스코어만 허용"
                  required
                  disabled={editingId !== null}
                />
                <p className={styles.hint}>소문자 영문 시작, 언더스코어 허용 (편집 불가)</p>
              </div>

              <div className={styles.field}>
                <label className={styles.label}>HTTP 메서드 *</label>
                <select
                  className={styles.select}
                  value={form.http_method}
                  onChange={(e) => setField("http_method", e.target.value)}
                >
                  {HTTP_METHODS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>설명 *</label>
              <input
                className={styles.input}
                value={form.description}
                onChange={(e) => setField("description", e.target.value)}
                placeholder="현재 날씨 정보를 가져옵니다."
                required
                maxLength={500}
              />
              <p className={styles.hint}>LLM이 이 도구를 언제 사용할지 판단하는 근거가 됩니다.</p>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>URL 템플릿 *</label>
              <input
                className={styles.input}
                value={form.url_template}
                onChange={(e) => setField("url_template", e.target.value)}
                placeholder="https://api.example.com/weather"
                required
                maxLength={2000}
              />
            </div>
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>파라미터 스키마</legend>

            {!hasSchemaParams ? (
              <div className={styles.field}>
                <label className={styles.label}>쿼리 파라미터 스키마 (JSON Schema)</label>
                <textarea
                  className={`${styles.textarea} ${querySchemaJson.error ? styles.error : ""}`}
                  rows={5}
                  value={form.query_params_schema}
                  onChange={(e) => setField("query_params_schema", e.target.value)}
                  placeholder={'{\n  "type": "object",\n  "properties": {\n    "city": { "type": "string" }\n  },\n  "required": ["city"]\n}'}
                />
                {querySchemaJson.error && (
                  <p className={styles.jsonError}>{querySchemaJson.error}</p>
                )}
                <p className={styles.hint}>LLM이 채울 GET 쿼리 파라미터를 JSON Schema로 정의합니다.</p>
              </div>
            ) : (
              <div className={styles.field}>
                <label className={styles.label}>바디 스키마 (JSON Schema)</label>
                <textarea
                  className={`${styles.textarea} ${bodySchemaJson.error ? styles.error : ""}`}
                  rows={5}
                  value={form.body_schema}
                  onChange={(e) => setField("body_schema", e.target.value)}
                  placeholder={'{\n  "type": "object",\n  "properties": {\n    "query": { "type": "string" }\n  }\n}'}
                />
                {bodySchemaJson.error && (
                  <p className={styles.jsonError}>{bodySchemaJson.error}</p>
                )}
                <p className={styles.hint}>LLM이 채울 요청 바디를 JSON Schema로 정의합니다.</p>
              </div>
            )}
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>고급 설정</legend>

            <div className={styles.field}>
              <label className={styles.label}>요청 헤더 (JSON)</label>
              <textarea
                className={`${styles.textarea} ${headersJson.error ? styles.error : ""}`}
                rows={3}
                value={form.headers}
                onChange={(e) => setField("headers", e.target.value)}
                placeholder={'{"Authorization": "Bearer YOUR_TOKEN"}'}
              />
              {headersJson.error && (
                <p className={styles.jsonError}>{headersJson.error}</p>
              )}
              <p className={styles.hint}>
                API 키 등 민감 정보 포함 가능 — 저장 시 암호화됩니다.
                기존 헤더를 수정하려면 다시 입력하세요 (현재 값은 마스킹되어 표시).
              </p>
            </div>

            <div className={styles.row2}>
              <div className={styles.field}>
                <label className={styles.label}>응답 JMESPath (옵션)</label>
                <input
                  className={styles.input}
                  value={form.response_jmespath}
                  onChange={(e) => setField("response_jmespath", e.target.value)}
                  placeholder="data.result"
                  maxLength={500}
                />
                <p className={styles.hint}>응답 JSON에서 추출할 경로 (예: data.items[0].name)</p>
              </div>

              <div className={styles.field}>
                <label className={styles.label}>타임아웃 (초)</label>
                <input
                  className={styles.input}
                  type="number"
                  min={1}
                  max={30}
                  value={form.timeout_seconds}
                  onChange={(e) => setField("timeout_seconds", e.target.value)}
                />
              </div>
            </div>
          </fieldset>

          <div className={styles.formFooter}>
            <button
              type="submit"
              className={styles.btnPrimary}
              disabled={saving || !!headersJson.error || !!querySchemaJson.error || !!bodySchemaJson.error}
            >
              {saving ? "저장 중…" : editingId === null ? "추가" : "저장"}
            </button>
            <button type="button" className={styles.btnSecondary} onClick={closeForm} disabled={saving}>
              취소
            </button>
            {submitError && <span className={styles.errorMsg}>{submitError}</span>}
          </div>
        </form>
      )}

      {/* ── Tool list ── */}
      {tools.length === 0 && !showForm ? (
        <div className={styles.empty}>
          등록된 도구가 없습니다.<br />
          <span style={{ fontSize: 12, marginTop: 4, display: "block" }}>
            LLM이 호출할 외부 API 도구를 추가하세요.
          </span>
        </div>
      ) : (
        <div className={styles.toolList}>
          {tools.map((tool) => (
            <div
              key={tool.id}
              className={`${styles.toolCard} ${!tool.is_active ? styles.inactive : ""}`}
            >
              <div className={styles.toolMain}>
                <div className={styles.toolNameRow}>
                  <span className={styles.toolName}>{tool.name}</span>
                  <MethodBadge method={tool.http_method} />
                  {!tool.is_active && <span className={styles.inactiveBadge}>비활성</span>}
                </div>
                <p className={styles.toolDesc}>{tool.description}</p>
                <p className={styles.toolUrl}>{tool.url_template}</p>
              </div>
              <div className={styles.toolActions}>
                <button
                  className={styles.btnSecondary}
                  onClick={() => toggleActive(tool)}
                  disabled={togglingId === tool.id}
                >
                  {togglingId === tool.id ? "…" : tool.is_active ? "비활성화" : "활성화"}
                </button>
                <button
                  className={styles.btnSecondary}
                  onClick={() => openEdit(tool)}
                  disabled={showForm}
                >
                  편집
                </button>
                <button
                  className={styles.btnDanger}
                  onClick={() => deleteTool(tool)}
                  disabled={deletingId === tool.id}
                >
                  {deletingId === tool.id ? "…" : "삭제"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
