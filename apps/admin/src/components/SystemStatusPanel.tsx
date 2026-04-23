"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchSystemHealth, type ServiceStatus, type SystemHealth } from "@/lib/api";
import styles from "./SystemStatusPanel.module.css";

const SERVICE_LABELS: { key: keyof Omit<SystemHealth, "checked_at">; label: string }[] = [
  { key: "postgresql", label: "PostgreSQL" },
  { key: "redis", label: "Redis" },
  { key: "llm", label: "LLM" },
  { key: "embedding", label: "Embedding" },
  { key: "safeguard", label: "Safeguard" },
  { key: "ner", label: "NER / PII" },
];

function StatusBadge({ status }: { status: ServiceStatus["status"] }) {
  return (
    <span className={`${styles.badge} ${styles[`badge_${status}`]}`}>
      {status === "ok" ? "정상" : status === "degraded" ? "저하" : "오류"}
    </span>
  );
}

export default function SystemStatusPanel() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchSystemHealth();
      setHealth(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "상태 조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const checkedAt = health?.checked_at
    ? new Date(health.checked_at).toLocaleTimeString("ko-KR")
    : null;

  return (
    <div className={styles.root}>
      <div className={styles.titleRow}>
        <h2 className={styles.title}>서비스 상태</h2>
        <div className={styles.meta}>
          {checkedAt && <span className={styles.time}>갱신 {checkedAt}</span>}
          <button className={styles.refresh} onClick={refresh} disabled={loading}>
            {loading ? "…" : "↻"}
          </button>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.grid}>
        {SERVICE_LABELS.map(({ key, label }) => {
          const svc = health?.[key] as ServiceStatus | undefined;
          return (
            <div key={key} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={styles.name}>{label}</span>
                {svc ? <StatusBadge status={svc.status} /> : <span className={styles.loading}>—</span>}
              </div>
              {svc?.latency_ms != null && (
                <span className={styles.latency}>{svc.latency_ms} ms</span>
              )}
              {svc?.message && (
                <span className={styles.message}>{svc.message}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
