"use client";

import { useEffect, useRef, useState } from "react";
import { adminFetch, deleteTenantIcon, uploadTenantIcon, type Tenant } from "@/lib/api";
import styles from "./SettingsPanel.module.css";

// ─── Domain Whitelist helpers ────────────────────────────────────────────────

function parseDomains(raw: string): string[] {
  return raw.split(",").map((d) => d.trim()).filter(Boolean);
}

const LANG_OPTIONS = [
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "zh", label: "中文" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "pt", label: "Português" },
  { value: "vi", label: "Tiếng Việt" },
  { value: "th", label: "ภาษาไทย" },
];

interface Props {
  tenant: Tenant;
  onUpdated: (t: Tenant) => void;
}

export default function SettingsPanel({ tenant, onUpdated }: Props) {
  const [form, setForm] = useState({
    name: tenant.name,
    system_prompt: tenant.system_prompt ?? "",
    lang_policy: tenant.lang_policy,
    default_lang: tenant.default_lang,
    allowed_langs: tenant.allowed_langs,
    is_active: tenant.is_active,
    default_url_refresh_hours: tenant.default_url_refresh_hours,
    widget_primary_color: tenant.widget_config.primary_color,
    widget_greeting: tenant.widget_config.greeting,
    widget_title: tenant.widget_config.title,
    widget_placeholder: tenant.widget_config.placeholder,
    widget_position: tenant.widget_config.position,
    quick_replies: (tenant.widget_config.quick_replies ?? []) as string[],
  });
  const [langsmithKey, setLangsmithKey] = useState("");
  const [langsmithKeyTouched, setLangsmithKeyTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [saved, setSaved] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [domainSaving, setDomainSaving] = useState(false);
  const [domainError, setDomainError] = useState<string | null>(null);
  const [newQuickReply, setNewQuickReply] = useState("");

  // 아이콘 관련 상태
  const [iconMode, setIconMode] = useState<"default" | "custom">(
    tenant.widget_config.button_icon_url ? "custom" : "default"
  );
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreviewUrl, setIconPreviewUrl] = useState<string | null>(
    tenant.widget_config.button_icon_url ?? null
  );

  // tenant prop이 외부에서 갱신될 때 아이콘 상태 동기화
  useEffect(() => {
    const url = tenant.widget_config.button_icon_url ?? null;
    setIconPreviewUrl(url);
    if (url) setIconMode("custom");
  }, [tenant.widget_config.button_icon_url]);
  const [iconUploading, setIconUploading] = useState(false);
  const [iconError, setIconError] = useState<string | null>(null);
  const iconInputRef = useRef<HTMLInputElement>(null);
  const prevObjectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (prevObjectUrlRef.current) URL.revokeObjectURL(prevObjectUrlRef.current);
    };
  }, []);

  function set(key: keyof typeof form, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        system_prompt: form.system_prompt || null,
        lang_policy: form.lang_policy,
        default_lang: form.default_lang,
        allowed_langs: form.allowed_langs,
        is_active: form.is_active,
        default_url_refresh_hours: form.default_url_refresh_hours,
        widget_config: {
          primary_color: form.widget_primary_color,
          greeting: form.widget_greeting,
          title: form.widget_title,
          placeholder: form.widget_placeholder,
          position: form.widget_position,
          quick_replies: form.quick_replies,
          ...(tenant.widget_config.button_icon_url
            ? { button_icon_url: tenant.widget_config.button_icon_url }
            : {}),
        },
      };
      if (langsmithKeyTouched) {
        payload.langsmith_api_key = langsmithKey.trim() || null;
      }
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      onUpdated(updated);
      setSaved(true);
      setLangsmithKey("");
      setLangsmithKeyTouched(false);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  async function addDomain() {
    // 스킴(http://, https://)과 포트(:8080) 자동 제거
    const domain = newDomain.trim().toLowerCase()
      .replace(/^https?:\/\//, "")
      .replace(/\/.*$/, "")
      .replace(/:\d+$/, "");
    if (!domain) return;
    setDomainError(null);
    setDomainSaving(true);
    try {
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}/domains`, {
        method: "POST",
        body: JSON.stringify({ domain }),
      });
      onUpdated(updated);
      setNewDomain("");
    } catch (e) {
      setDomainError(e instanceof Error ? e.message : "도메인 추가 실패");
    } finally {
      setDomainSaving(false);
    }
  }

  async function removeDomain(index: number) {
    setDomainSaving(true);
    try {
      const updated = await adminFetch<Tenant>(
        `/tenants/${tenant.id}/domains/${index}`,
        { method: "DELETE" }
      );
      onUpdated(updated);
    } finally {
      setDomainSaving(false);
    }
  }

  function handleIconFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setIconError(null);

    // 이전 ObjectURL 해제
    if (prevObjectUrlRef.current) {
      URL.revokeObjectURL(prevObjectUrlRef.current);
    }
    const objectUrl = URL.createObjectURL(file);
    prevObjectUrlRef.current = objectUrl;
    setIconFile(file);
    setIconPreviewUrl(objectUrl);
  }

  async function uploadIcon() {
    if (!iconFile) return;
    setIconUploading(true);
    setIconError(null);
    try {
      const updated = await uploadTenantIcon(tenant.id, iconFile);
      onUpdated(updated);
      // ObjectURL → 실제 서버 URL로 교체
      if (prevObjectUrlRef.current) {
        URL.revokeObjectURL(prevObjectUrlRef.current);
        prevObjectUrlRef.current = null;
      }
      setIconFile(null);
      setIconPreviewUrl(updated.widget_config.button_icon_url ?? null);
      if (iconInputRef.current) iconInputRef.current.value = "";
    } catch (e) {
      setIconError(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setIconUploading(false);
    }
  }

  async function resetIcon() {
    if (!confirm("기본 아이콘으로 리셋하시겠습니까?")) return;
    setIconUploading(true);
    setIconError(null);
    try {
      const updated = await deleteTenantIcon(tenant.id);
      onUpdated(updated);
      setIconMode("default");
      setIconFile(null);
      setIconPreviewUrl(null);
      if (prevObjectUrlRef.current) {
        URL.revokeObjectURL(prevObjectUrlRef.current);
        prevObjectUrlRef.current = null;
      }
      if (iconInputRef.current) iconInputRef.current.value = "";
    } catch (e) {
      setIconError(e instanceof Error ? e.message : "리셋 실패");
    } finally {
      setIconUploading(false);
    }
  }

  async function rotateKey() {
    if (!confirm("API 키를 교체하시겠습니까? 기존 키는 즉시 만료됩니다.")) return;
    setRotating(true);
    try {
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}/rotate-key`, {
        method: "POST",
      });
      onUpdated(updated);
    } finally {
      setRotating(false);
    }
  }

  return (
    <form className={styles.root} onSubmit={save}>
      <h2 className={styles.heading}>설정</h2>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>기본 정보</legend>
        <Field label="테넌트 이름">
          <input className={styles.input} value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="시스템 프롬프트">
          <textarea
            className={styles.textarea}
            rows={5}
            value={form.system_prompt}
            onChange={(e) => set("system_prompt", e.target.value)}
            placeholder="없으면 기본 프롬프트를 사용합니다."
          />
        </Field>
        <Field label="활성 상태">
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => set("is_active", e.target.checked)}
            />
            <span>{form.is_active ? "활성" : "비활성"}</span>
          </label>
        </Field>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>언어 설정</legend>
        <Field label="언어 정책">
          <select className={styles.select} value={form.lang_policy} onChange={(e) => set("lang_policy", e.target.value)}>
            <option value="auto">auto — 브라우저 언어 자동 감지</option>
            <option value="fixed">fixed — 기본 언어 고정</option>
            <option value="whitelist">whitelist — 허용 언어 목록</option>
          </select>
        </Field>
        <Field label="기본 언어">
          <select className={styles.select} value={form.default_lang} onChange={(e) => set("default_lang", e.target.value)}>
            {LANG_OPTIONS.map((l) => (
              <option key={l.value} value={l.value}>{l.label} ({l.value})</option>
            ))}
          </select>
        </Field>
        {form.lang_policy === "whitelist" && (
          <Field label="허용 언어 (쉼표 구분)" hint="예: ko,en,ja">
            <input
              className={styles.input}
              value={form.allowed_langs}
              onChange={(e) => set("allowed_langs", e.target.value)}
            />
          </Field>
        )}
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>URL 자동 갱신</legend>
        <Field label="기본 갱신 주기" hint="새 URL 문서 등록 시 기본으로 적용됩니다. 문서별로 개별 변경도 가능합니다.">
          <select
            className={styles.select}
            value={form.default_url_refresh_hours}
            onChange={(e) => setForm((prev) => ({ ...prev, default_url_refresh_hours: Number(e.target.value) }))}
          >
            <option value={0}>자동 갱신 안 함</option>
            <option value={1}>1시간마다</option>
            <option value={6}>6시간마다</option>
            <option value={12}>12시간마다</option>
            <option value={24}>24시간마다 (1일)</option>
            <option value={48}>48시간마다 (2일)</option>
            <option value={72}>72시간마다 (3일)</option>
            <option value={168}>168시간마다 (1주)</option>
          </select>
        </Field>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>위젯 설정</legend>
        <Field label="타이틀">
          <input className={styles.input} value={form.widget_title} onChange={(e) => set("widget_title", e.target.value)} />
        </Field>
        <Field label="인사말">
          <input className={styles.input} value={form.widget_greeting} onChange={(e) => set("widget_greeting", e.target.value)} />
        </Field>
        <Field label="입력창 placeholder">
          <input className={styles.input} value={form.widget_placeholder} onChange={(e) => set("widget_placeholder", e.target.value)} />
        </Field>
        <Field label="기본 색상">
          <div className={styles.colorRow}>
            <input
              type="color"
              className={styles.colorInput}
              value={form.widget_primary_color}
              onChange={(e) => set("widget_primary_color", e.target.value)}
            />
            <input
              className={styles.input}
              value={form.widget_primary_color}
              onChange={(e) => set("widget_primary_color", e.target.value)}
              style={{ width: 100 }}
            />
          </div>
        </Field>
        <Field label="위치">
          <select className={styles.select} value={form.widget_position} onChange={(e) => set("widget_position", e.target.value)}>
            <option value="bottom-right">우하단</option>
            <option value="bottom-left">좌하단</option>
          </select>
        </Field>

        <Field label="버튼 아이콘" hint="위젯 열기/닫기 버튼에 표시되는 아이콘입니다.">
          <div className={styles.iconModeRow}>
            <label className={styles.radioLabel}>
              <input
                type="radio"
                name="iconMode"
                value="default"
                checked={iconMode === "default"}
                onChange={() => setIconMode("default")}
              />
              기본 아이콘 (SVG)
            </label>
            <label className={styles.radioLabel}>
              <input
                type="radio"
                name="iconMode"
                value="custom"
                checked={iconMode === "custom"}
                onChange={() => setIconMode("custom")}
              />
              사용자 이미지
            </label>
          </div>

          <div className={styles.iconPreviewRow}>
            <div className={styles.iconPreviewBox} style={{ background: form.widget_primary_color }}>
              {iconMode === "custom" && iconPreviewUrl ? (
                <img
                  src={iconPreviewUrl}
                  alt="아이콘 미리보기"
                  style={{ width: 56, height: 56, borderRadius: "50%", objectFit: "cover", display: "block" }}
                />
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff">
                  <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
                </svg>
              )}
            </div>
            <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>56×56px 미리보기</span>
          </div>

          {iconMode === "custom" && (
            <div className={styles.iconUploadArea}>
              <input
                ref={iconInputRef}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                className={styles.fileInput}
                onChange={handleIconFileChange}
              />
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 4 }}>
                PNG/JPG/GIF/WebP · 권장 56×56px · 최대 2MB
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                  type="button"
                  className={styles.btnPrimary}
                  style={{ background: "var(--color-surface-2)", color: "var(--color-text)", border: "1px solid var(--color-border)" }}
                  onClick={() => iconInputRef.current?.click()}
                  disabled={iconUploading}
                >
                  파일 선택{iconFile ? ` (${iconFile.name})` : ""}
                </button>
                <button
                  type="button"
                  className={styles.btnPrimary}
                  disabled={!iconFile || iconUploading}
                  onClick={uploadIcon}
                >
                  {iconUploading ? "업로드 중…" : "업로드"}
                </button>
                {tenant.widget_config.button_icon_url && (
                  <button
                    type="button"
                    className={styles.btnDanger}
                    disabled={iconUploading}
                    onClick={resetIcon}
                    style={{ fontSize: 13 }}
                  >
                    기본으로 리셋
                  </button>
                )}
              </div>
              {iconError && (
                <p style={{ fontSize: 12, color: "var(--color-danger, #e53e3e)", marginTop: 6 }}>
                  {iconError}
                </p>
              )}
            </div>
          )}
        </Field>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>허용 도메인 (위젯 화이트리스트)</legend>
        <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 12 }}>
          비어 있으면 모든 도메인에서 위젯 사용 가능. 등록된 도메인 외에는 403 응답.
        </p>
        <div className={styles.domainList}>
          {parseDomains(tenant.allowed_domains).map((domain, idx) => (
            <span key={domain} className={styles.domainChip}>
              {domain}
              <button
                type="button"
                className={styles.domainRemove}
                onClick={() => removeDomain(idx)}
                disabled={domainSaving}
                aria-label={`${domain} 삭제`}
              >
                ×
              </button>
            </span>
          ))}
          {parseDomains(tenant.allowed_domains).length === 0 && (
            <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>등록된 도메인 없음</span>
          )}
        </div>
        <div className={styles.domainAdd}>
          <input
            className={styles.input}
            value={newDomain}
            onChange={(e) => { setNewDomain(e.target.value); setDomainError(null); }}
            placeholder="example.com"
            style={{ flex: 1 }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addDomain(); } }}
          />
          <button type="button" className={styles.btnPrimary} disabled={domainSaving || !newDomain.trim()} onClick={addDomain}>
            추가
          </button>
        </div>
        {domainError && (
          <p style={{ fontSize: 12, color: "var(--color-danger, #e53e3e)", marginTop: 6 }}>
            {domainError}
          </p>
        )}
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>즐겨찾기 질문 (Quick Replies)</legend>
        <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 12 }}>
          위젯 채팅창 하단에 빠른 질문 버튼으로 표시됩니다. 최대 10개.
        </p>
        <div className={styles.domainList}>
          {form.quick_replies.map((reply, idx) => (
            <span key={idx} className={styles.domainChip}>
              {reply}
              <button
                type="button"
                className={styles.domainRemove}
                onClick={() => setForm((prev) => ({
                  ...prev,
                  quick_replies: prev.quick_replies.filter((_, i) => i !== idx),
                }))}
                aria-label={`${reply} 삭제`}
              >
                ×
              </button>
            </span>
          ))}
          {form.quick_replies.length === 0 && (
            <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>등록된 즐겨찾기 없음</span>
          )}
        </div>
        <div className={styles.domainAdd}>
          <input
            className={styles.input}
            value={newQuickReply}
            onChange={(e) => setNewQuickReply(e.target.value)}
            placeholder="자주 묻는 질문을 입력하세요"
            style={{ flex: 1 }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const text = newQuickReply.trim();
                if (text && form.quick_replies.length < 10) {
                  setForm((prev) => ({ ...prev, quick_replies: [...prev.quick_replies, text] }));
                  setNewQuickReply("");
                }
              }
            }}
          />
          <button
            type="button"
            className={styles.btnPrimary}
            disabled={!newQuickReply.trim() || form.quick_replies.length >= 10}
            onClick={() => {
              const text = newQuickReply.trim();
              if (text && form.quick_replies.length < 10) {
                setForm((prev) => ({ ...prev, quick_replies: [...prev.quick_replies, text] }));
                setNewQuickReply("");
              }
            }}
          >
            추가
          </button>
        </div>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>옵저버빌리티</legend>
        <Field
          label="LangSmith API 키"
          hint="설정하면 RAG 검색 및 LLM 호출이 LangSmith에 기록됩니다. 비워두고 저장하면 키가 삭제됩니다."
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <span style={{ fontSize: 12 }}>
              현재 상태:{" "}
              <strong style={{ color: tenant.has_langsmith ? "var(--color-primary, #0066ff)" : "var(--color-text-muted)" }}>
                {tenant.has_langsmith ? "연결됨 ✓" : "미설정"}
              </strong>
            </span>
          </div>
          <input
            className={styles.input}
            type="password"
            value={langsmithKey}
            onChange={(e) => { setLangsmithKey(e.target.value); setLangsmithKeyTouched(true); }}
            placeholder={tenant.has_langsmith ? "새 키 입력 (비워두면 기존 키 유지, 저장 시 삭제)" : "ls-..."}
            autoComplete="new-password"
          />
        </Field>
      </fieldset>

      <div className={styles.footer}>
        <button className={styles.btnPrimary} type="submit" disabled={saving}>
          {saved ? "저장됨 ✓" : saving ? "저장 중…" : "저장"}
        </button>
        <button className={styles.btnDanger} type="button" onClick={rotateKey} disabled={rotating}>
          {rotating ? "교체 중…" : "API 키 교체"}
        </button>
      </div>
    </form>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--color-text)" }}>
        {label}
      </label>
      {children}
      {hint && <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 4 }}>{hint}</p>}
    </div>
  );
}
