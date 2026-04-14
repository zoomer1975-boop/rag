"use client";

import { useEffect, useState } from "react";
import { adminFetch, type Tenant, type SubAdmin } from "@/lib/api";
import Dashboard from "@/components/Dashboard";
import LogoutButton from "@/components/LogoutButton";
import CreateTenantForm from "@/components/CreateTenantForm";
import SubAdminManager from "@/components/SubAdminManager";
import styles from "./page.module.css";

interface SessionPayload {
  username: string;
  is_superadmin?: boolean;
  sub_admin_id?: number;
  tenant_ids?: number[];
  exp: number;
}

export default function Home() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [view, setView] = useState<"login" | "tenants" | "dashboard" | "sub-admins">("tenants");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // 세션 로드
  useEffect(() => {
    const loadSession = async () => {
      const res = await fetch("/rag/admin/api/auth/me");
      if (res.ok) {
        const payload = await res.json();
        setSession(payload);
      }
    };

    loadSession();
  }, []);

  async function loadTenants() {
    setLoading(true);
    setError("");
    try {
      const data = await adminFetch<Tenant[]>("/tenants/");

      // 부관리자면 할당된 테넌트만 필터링
      if (session && !session.is_superadmin && session.tenant_ids) {
        const filtered = data.filter((t) => session.tenant_ids?.includes(t.id));
        setTenants(filtered);
      } else {
        setTenants(data);
      }

      setView("tenants");
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteTenant(t: Tenant) {
    if (!confirm(`테넌트 "${t.name}"을(를) 삭제하시겠습니까?\n\n모든 문서, 청크, 대화 데이터가 함께 삭제됩니다.`)) return;
    setDeletingId(t.id);
    try {
      await adminFetch<void>(`/tenants/${t.id}`, { method: "DELETE" });
      setTenants((prev) => prev.filter((x) => x.id !== t.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제 중 오류가 발생했습니다.");
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => { loadTenants(); }, []);

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

  if (view === "sub-admins" && session?.is_superadmin) {
    return (
      <SubAdminManager
        onBack={() => setView("tenants")}
        onSubAdminsUpdated={() => {}}
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
            {/* 최고관리자만 테넌트 생성 가능 */}
            {session?.is_superadmin && (
              <CreateTenantForm onCreated={(t) => { setTenants((prev) => [t, ...prev]); }} />
            )}
            {/* 최고관리자만 부관리자 관리 버튼 표시 */}
            {session?.is_superadmin && (
              <button className={styles.btnSecondary} onClick={() => setView("sub-admins")}>
                부관리자 관리
              </button>
            )}
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
                {/* 최고관리자만 테넌트 삭제 가능 */}
                {session?.is_superadmin && (
                  <button
                    className={styles.btnDanger}
                    onClick={() => deleteTenant(t)}
                    disabled={deletingId === t.id}
                  >
                    {deletingId === t.id ? "삭제 중…" : "삭제"}
                  </button>
                )}
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
