"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, type Document } from "@/lib/api";
import DocumentChunksModal from "./DocumentChunksModal";
import styles from "./DocumentsPanel.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/rag/api/v1";

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "대기", color: "#f59e0b" },
  processing: { label: "처리 중", color: "#6366f1" },
  completed: { label: "완료", color: "#22c55e" },
  failed: { label: "실패", color: "#ef4444" },
};

const SOURCE_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  url: { label: "URL", color: "#6366f1" },
  pdf: { label: "PDF", color: "#ef4444" },
  docx: { label: "DOCX", color: "#3b82f6" },
  txt: { label: "TXT", color: "#6b7280" },
  md: { label: "MD", color: "#6b7280" },
};


function formatDatetime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DocumentsPanel({ apiKey }: { apiKey: string }) {
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [urlInput, setUrlInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [refreshingId, setRefreshingId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewingDoc, setViewingDoc] = useState<Document | null>(null);
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

  const filteredDocs = searchQuery.trim()
    ? docs.filter((doc) => {
        const q = searchQuery.trim().toLowerCase();
        return (
          doc.title.toLowerCase().includes(q) ||
          (doc.source_url ?? "").toLowerCase().includes(q)
        );
      })
    : docs;

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

  async function refreshDoc(id: number) {
    setRefreshingId(id);
    try {
      const updated = await apiFetch<Document>(`/ingest/documents/${id}/refresh`, apiKey, {
        method: "POST",
      });
      setDocs((prev) => prev.map((d) => (d.id === id ? updated : d)));
    } finally {
      setRefreshingId(null);
    }
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
          <div className={styles.searchWrapper}>
            <span className={styles.searchIcon}>🔍</span>
            <input
              className={styles.searchInput}
              type="search"
              placeholder="문서명 또는 URL 검색…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {searchQuery.trim() && (
              <span className={styles.searchCount}>
                {filteredDocs.length} / {docs.length}건
              </span>
            )}
            <button className={styles.btnGhost} onClick={load}>새로고침</button>
          </div>
        </div>
        {loading ? (
          <p className={styles.muted}>불러오는 중…</p>
        ) : filteredDocs.length === 0 && searchQuery.trim() ? (
          <p className={styles.muted}>"{searchQuery.trim()}"에 해당하는 문서가 없습니다.</p>
        ) : docs.length === 0 ? (
          <p className={styles.muted}>문서가 없습니다.</p>
        ) : (
          <ul className={styles.docList}>
            {filteredDocs.map((doc) => {
              const st = STATUS_LABELS[doc.status] ?? { label: doc.status, color: "#ccc" };
              const typeBadge = SOURCE_TYPE_LABELS[doc.source_type] ?? { label: doc.source_type.toUpperCase(), color: "#6b7280" };
              const isUrl = doc.source_type === "url";
              const isRefreshing = refreshingId === doc.id;
              return (
                <li key={doc.id} className={styles.docItem}>
                  <div className={styles.docMain}>
                    <div className={styles.docTitleRow}>
                      <span
                        className={styles.typeBadge}
                        style={{ background: typeBadge.color + "22", color: typeBadge.color }}
                      >
                        {typeBadge.label}
                      </span>
                      <span className={styles.docTitle}>{doc.title}</span>
                    </div>
                    <span className={styles.docMeta}>
                      {doc.chunk_count}개 청크
                      {isUrl && doc.last_refreshed_at && (
                        <> · 마지막 갱신: {formatDatetime(doc.last_refreshed_at)}</>
                      )}
                      {isUrl && doc.next_refresh_at && (
                        <> · 다음 갱신: {formatDatetime(doc.next_refresh_at)}</>
                      )}
                    </span>
                    {doc.error_message && (
                      <span className={styles.docError}>{doc.error_message}</span>
                    )}
                  </div>
                  <div className={styles.docActions}>
                    {isUrl && (
                      <button
                        className={styles.refreshBtn}
                        onClick={() => refreshDoc(doc.id)}
                        disabled={isRefreshing || doc.status === "processing"}
                        title="즉시 갱신"
                      >
                        {isRefreshing ? "…" : "↻"}
                      </button>
                    )}
                    <button
                      className={styles.viewBtn}
                      onClick={() => setViewingDoc(doc)}
                      disabled={doc.status !== "completed"}
                      title="내용 보기"
                    >
                      내용
                    </button>
                    <span className={styles.statusBadge} style={{ color: st.color }}>
                      {st.label}
                    </span>
                    <button className={styles.deleteBtn} onClick={() => deleteDoc(doc.id)} aria-label="삭제">
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {viewingDoc && (
        <DocumentChunksModal
          apiKey={apiKey}
          doc={viewingDoc}
          onClose={() => setViewingDoc(null)}
        />
      )}
    </div>
  );
}
