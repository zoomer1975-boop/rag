"use client";

import { useState } from "react";
import { adminFetch, type Tenant } from "@/lib/api";
import styles from "@/app/page.module.css";

interface CreateTenantFormProps {
  onCreated: (t: Tenant) => void;
}

export default function CreateTenantForm({ onCreated }: CreateTenantFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError("");
    try {
      const tenant = await adminFetch<Tenant>("/tenants/", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      onCreated(tenant);
      setName("");
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "테넌트 생성에 실패했습니다.");
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
    <div>
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
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
