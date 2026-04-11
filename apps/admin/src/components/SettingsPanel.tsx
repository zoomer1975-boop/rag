"use client";

import { useState } from "react";
import { adminFetch, type Tenant } from "@/lib/api";
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
    widget_primary_color: tenant.widget_config.primary_color,
    widget_greeting: tenant.widget_config.greeting,
    widget_title: tenant.widget_config.title,
    widget_placeholder: tenant.widget_config.placeholder,
    widget_position: tenant.widget_config.position,
  });
  const [saving, setSaving] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [saved, setSaved] = useState(false);
  const [newDomain, setNewDomain] = useState("");
  const [domainSaving, setDomainSaving] = useState(false);

  function set(key: keyof typeof form, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name,
          system_prompt: form.system_prompt || null,
          lang_policy: form.lang_policy,
          default_lang: form.default_lang,
          allowed_langs: form.allowed_langs,
          is_active: form.is_active,
          widget_config: {
            primary_color: form.widget_primary_color,
            greeting: form.widget_greeting,
            title: form.widget_title,
            placeholder: form.widget_placeholder,
            position: form.widget_position,
          },
        }),
      });
      onUpdated(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  async function addDomain(e: React.FormEvent) {
    e.preventDefault();
    const domain = newDomain.trim().toLowerCase();
    if (!domain) return;
    setDomainSaving(true);
    try {
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}/domains`, {
        method: "POST",
        body: JSON.stringify({ domain }),
      });
      onUpdated(updated);
      setNewDomain("");
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
        <form onSubmit={addDomain} className={styles.domainAdd}>
          <input
            className={styles.input}
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            placeholder="example.com"
            style={{ flex: 1 }}
          />
          <button type="submit" className={styles.btnPrimary} disabled={domainSaving || !newDomain.trim()}>
            추가
          </button>
        </form>
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
