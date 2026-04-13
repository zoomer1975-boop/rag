"use client";

import { useState } from "react";
import { adminFetch, type Tenant } from "@/lib/api";
import Dashboard from "@/components/Dashboard";
import LogoutButton from "@/components/LogoutButton";
import styles from "./page.module.css";

export default function Home() {
  const [apiKey, setApiKey] = useState("");
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [view, setView] = useState<"login" | "tenants" | "dashboard">("tenants");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadTenants() {
    setLoading(true);
    setError("");
    try {
      const data = await adminFetch<Tenant[]>("/tenants/");
      setTenants(data);
      setView("tenants");
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  function selectTenant(t: Tenant) {
    setTenant(t);
    setApiKey(t.api_key);
    setView("dashboard");
  }

  if (view === "dashboard" && tenant) {
    return (
      <Dashboard
        tenant={tenant}
        apiKey={apiKey}
        onBack={() => setView("tenants")}
        onTenantUpdate={(updated) => setTenant(updated)}
      />
    );
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <span className={styles.logo}>RAG Admin</span>
        <LogoutButton className={styles.btnGhost} />
      </header>
      <main className={styles.main}>
        <div className={styles.panel}>
          <h1 className={styles.title}>테넌트 목록</h1>
          <div className={styles.actions}>
            <button className={styles.btnPrimary} onClick={loadTenants} disabled={loading}>
              {loading ? "불러오는 중…" : "새로고침"}
            </button>
            <CreateTenantInline onCreated={(t) => { setTenants((prev) => [t, ...prev]); }} />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          {tenants.length === 0 && !loading && (
            <p className={styles.empty}>테넌트가 없습니다. 새로고침 버튼을 눌러 불러오세요.</p>
          )}
          <ul className={styles.tenantList}>
            {tenants.map((t) => (
              <li key={t.id} className={styles.tenantItem}>
                <div className={styles.tenantInfo}>
                  <span className={styles.tenantName}>{t.name}</span>
                  <span className={`${styles.badge} ${t.is_active ? styles.badgeGreen : styles.badgeRed}`}>
                    {t.is_active ? "활성" : "비활성"}
                  </span>
                </div>
                <code className={styles.apiKey}>{t.api_key}</code>
                <button className={styles.btnSecondary} onClick={() => selectTenant(t)}>
                  관리 →
                </button>
              </li>
            ))}
          </ul>
        </div>
      </main>
    </div>
  );
}

function CreateTenantInline({ onCreated }: { onCreated: (t: Tenant) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      const tenant = await adminFetch<Tenant>("/tenants/", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      onCreated(tenant);
      setName("");
      setOpen(false);
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <button className={styles.btnSecondary} onClick={() => setOpen(true)}>
        + 테넌트 추가
      </button>
    );
  }

  return (
    <form className={styles.inlineForm} onSubmit={submit}>
      <input
        className={styles.input}
        placeholder="테넌트 이름"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <button className={styles.btnPrimary} type="submit" disabled={loading}>
        {loading ? "생성 중…" : "생성"}
      </button>
      <button className={styles.btnGhost} type="button" onClick={() => setOpen(false)}>
        취소
      </button>
    </form>
  );
}
