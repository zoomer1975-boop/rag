"use client";

import { useEffect, useState } from "react";
import { apiFetch, type Stats } from "@/lib/api";
import styles from "./StatsPanel.module.css";

const STAT_LABELS: { key: keyof Stats; label: string; unit: string }[] = [
  { key: "document_count", label: "문서", unit: "개" },
  { key: "chunk_count", label: "청크", unit: "개" },
  { key: "conversation_count", label: "대화", unit: "건" },
  { key: "message_count", label: "메시지", unit: "개" },
];

export default function StatsPanel({ apiKey }: { apiKey: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Stats>("/analytics/stats", apiKey)
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [apiKey]);

  if (loading) return <p className={styles.loading}>불러오는 중…</p>;
  if (error) return <p className={styles.error}>{error}</p>;
  if (!stats) return null;

  return (
    <div>
      <h2 className={styles.heading}>현황 통계</h2>
      <div className={styles.grid}>
        {STAT_LABELS.map(({ key, label, unit }) => (
          <div key={key} className={styles.card}>
            <span className={styles.value}>{stats[key].toLocaleString()}</span>
            <span className={styles.unit}>{unit}</span>
            <span className={styles.label}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
