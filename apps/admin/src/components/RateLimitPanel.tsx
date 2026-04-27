"use client";

import { useState } from "react";
import { adminFetch, type Tenant } from "@/lib/api";
import styles from "./RateLimitPanel.module.css";

interface Props {
  tenant: Tenant;
  onUpdated: (t: Tenant) => void;
}

interface FormState {
  rate_limit_requests: string;
  rate_limit_window: string;
  max_documents: string;
  max_api_tools: string;
}

function toField(val: number | null | undefined): string {
  return val == null ? "" : String(val);
}

function toPayload(val: string): number | null {
  if (val.trim() === "") return null;
  const n = parseInt(val, 10);
  return isNaN(n) ? null : n;
}

export default function RateLimitPanel({ tenant, onUpdated }: Props) {
  const [form, setForm] = useState<FormState>({
    rate_limit_requests: toField(tenant.rate_limit_requests),
    rate_limit_window: toField(tenant.rate_limit_window),
    max_documents: toField(tenant.max_documents),
    max_api_tools: toField(tenant.max_api_tools),
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function handleChange(field: keyof FormState, value: string) {
    if (value !== "" && !/^\d*$/.test(value)) return;
    setForm((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const updated = await adminFetch<Tenant>(`/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          rate_limit_requests: toPayload(form.rate_limit_requests),
          rate_limit_window: toPayload(form.rate_limit_window),
          max_documents: toPayload(form.max_documents),
          max_api_tools: toPayload(form.max_api_tools),
        }),
      });
      onUpdated(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.root}>
      <h2 className={styles.heading}>제한 설정</h2>
      <p className={styles.intro}>
        빈 칸 = 전역 설정 상속 &nbsp;·&nbsp; <strong>0</strong> = 무제한 &nbsp;·&nbsp; 양수 = 해당 값으로 제한
      </p>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>요청 빈도 제한 (Rate Limit)</h3>
        <div className={styles.helpBox}>
          <p>
            <strong>요청 수 (RATE_LIMIT_REQUESTS)</strong> — 슬라이딩 윈도우 기간 내 허용되는 최대 요청 횟수.
            <br />
            예) <code>60</code> = 윈도우 기간 동안 최대 60회 요청 허용.
          </p>
          <p>
            <strong>윈도우 (RATE_LIMIT_WINDOW, 초)</strong> — 슬라이딩 윈도우 크기. 항상 최근 N초 내 요청 수를 추적하며, 시간이 흐르면서 오래된 요청은 자동으로 제외됨.
            <br />
            예) <code>60</code> = 최근 60초 기준 &nbsp;/&nbsp; <code>3600</code> = 최근 1시간 기준.
          </p>
          <p className={styles.helpNote}>
            한도 초과 시: &quot;현재 사용 가능한 limit에 도달하였습니다. N분 후 재개됩니다.&quot; 메시지가 반환됩니다.
          </p>
        </div>
        <div className={styles.fields}>
          <label className={styles.field}>
            <span className={styles.label}>
              요청 수 <span className={styles.zero}>0 = 무제한</span>
            </span>
            <input
              type="text"
              inputMode="numeric"
              className={styles.input}
              placeholder="예: 60 (비워두면 전역 설정 사용)"
              value={form.rate_limit_requests}
              onChange={(e) => handleChange("rate_limit_requests", e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>
              윈도우 (초) <span className={styles.zero}>0 = 무제한</span>
            </span>
            <input
              type="text"
              inputMode="numeric"
              className={styles.input}
              placeholder="예: 60 (비워두면 전역 설정 사용)"
              value={form.rate_limit_window}
              onChange={(e) => handleChange("rate_limit_window", e.target.value)}
            />
          </label>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>리소스 제한</h3>
        <div className={styles.fields}>
          <label className={styles.field}>
            <span className={styles.label}>
              최대 문서 수 <span className={styles.zero}>0 = 무제한</span>
            </span>
            <input
              type="text"
              inputMode="numeric"
              className={styles.input}
              placeholder="예: 100 (비워두면 전역 설정 사용)"
              value={form.max_documents}
              onChange={(e) => handleChange("max_documents", e.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>
              최대 API Tool 수 <span className={styles.zero}>0 = 무제한</span>
            </span>
            <input
              type="text"
              inputMode="numeric"
              className={styles.input}
              placeholder="예: 10 (비워두면 전역 설정 사용)"
              value={form.max_api_tools}
              onChange={(e) => handleChange("max_api_tools", e.target.value)}
            />
          </label>
        </div>
      </section>

      {error && <p className={styles.error}>{error}</p>}
      {saved && <p className={styles.success}>저장되었습니다.</p>}

      <button className={styles.saveBtn} onClick={handleSave} disabled={saving}>
        {saving ? "저장 중…" : "저장"}
      </button>
    </div>
  );
}
