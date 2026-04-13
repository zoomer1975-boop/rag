"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, type Document } from "@/lib/api";
import styles from "./DocumentsPanel.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/rag/api/v1";

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "대기", color: "#f59e0b" },
  processing: { label: "처리 중", color: "#6366f1" },
  completed: { label: "완료", color: "#22c55e" },
  failed: { label: "실패", color: "#ef4444" },
};

export default function DocumentsPanel({ apiKey }: { apiKey: string }) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [urlInput, setUrlInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await apiFetch<Document[]>("/ingest/documents", apiKey);
      setDocs(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [apiKey]);

  async function ingestUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!urlInput.trim()) return;
    setSubmitting(true);
    try {
      const doc = await apiFetch<Document>("/ingest/url", apiKey, {
        method: "POST",
        body: JSON.stringify({ url: urlInput.trim() }),
      });
      setDocs((prev) => [doc, ...prev]);
      setUrlInput("");
    } finally {
      setSubmitting(false);
    }
  }

  async function ingestFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/ingest/file`, {
        method: "POST",
        headers: { "X-API-Key": apiKey },
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const doc: Document = await res.json();
      setDocs((prev) => [doc, ...prev]);
    } finally {
      setSubmitting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function deleteDoc(id: number) {
    if (!confirm("문서를 삭제하시겠습니까?")) return;
    await apiFetch(`/ingest/documents/${id}`, apiKey, { method: "DELETE" });
    setDocs((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <div>
      <h2 className={styles.heading}>문서 관리</h2>

      <section className={styles.section}>
        <h3 className={styles.subHeading}>URL 인제스트</h3>
        <form className={styles.urlForm} onSubmit={ingestUrl}>
          <input
            className={styles.input}
            type="url"
            placeholder="https://example.com/docs"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
          />
          <button className={styles.btnPrimary} type="submit" disabled={submitting}>
            {submitting ? "처리 중…" : "인제스트"}
          </button>
        </form>
      </section>

      <section className={styles.section}>
        <h3 className={styles.subHeading}>파일 업로드</h3>
        <div className={styles.fileRow}>
          <button className={styles.btnSecondary} onClick={() => fileRef.current?.click()} disabled={submitting}>
            파일 선택 (PDF, DOCX, TXT, MD)
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            style={{ display: "none" }}
            onChange={ingestFile}
          />
          {submitting && <span className={styles.hint}>업로드 중…</span>}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.listHeader}>
          <h3 className={styles.subHeading}>문서 목록</h3>
          <button className={styles.btnGhost} onClick={load}>새로고침</button>
        </div>
        {loading ? (
          <p className={styles.muted}>불러오는 중…</p>
        ) : docs.length === 0 ? (
          <p className={styles.muted}>문서가 없습니다.</p>
        ) : (
          <ul className={styles.docList}>
            {docs.map((doc) => {
              const st = STATUS_LABELS[doc.status] ?? { label: doc.status, color: "#ccc" };
              return (
                <li key={doc.id} className={styles.docItem}>
                  <div className={styles.docMain}>
                    <span className={styles.docTitle}>{doc.title}</span>
                    <span className={styles.docMeta}>
                      {doc.source_type.toUpperCase()} · {doc.chunk_count}개 청크
                    </span>
                    {doc.error_message && (
                      <span className={styles.docError}>{doc.error_message}</span>
                    )}
                  </div>
                  <span className={styles.statusBadge} style={{ color: st.color }}>
                    {st.label}
                  </span>
                  <button className={styles.deleteBtn} onClick={() => deleteDoc(doc.id)} aria-label="삭제">
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
