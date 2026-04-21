"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { listDocumentChunks, type Chunk, type Document } from "@/lib/api";
import styles from "./DocumentChunksModal.module.css";

interface Props {
  apiKey: string;
  doc: Document;
  onClose: () => void;
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightText(text: string, query: string): React.ReactNode[] {
  if (!query.trim()) return [text];
  const regex = new RegExp(`(${escapeRegex(query.trim())})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i} className={styles.mark}>
        {part}
      </mark>
    ) : (
      part
    )
  );
}

export default function DocumentChunksModal({ apiKey, doc, onClose }: Props) {
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  const LIMIT = 50;

  async function fetchChunks(offset: number, append: boolean) {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await listDocumentChunks(apiKey, doc.id, { limit: LIMIT, offset });
      setTotal(res.total);
      setChunks((prev) => (append ? [...prev, ...res.items] : res.items));
    } catch (e) {
      setError(e instanceof Error ? e.message : "청크를 불러오지 못했습니다.");
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  }

  useEffect(() => {
    fetchChunks(0, false);
    setTimeout(() => searchRef.current?.focus(), 50);
  }, [doc.id]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const filteredChunks = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return chunks;
    return chunks.filter((c) => c.content.toLowerCase().includes(q));
  }, [chunks, searchQuery]);

  const hasMore = chunks.length < total;

  return (
    <div className={styles.overlay} onClick={onClose} role="presentation">
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="chunk-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <h2 id="chunk-modal-title" className={styles.title}>
            {doc.title}
          </h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>

        <div className={styles.searchBar}>
          <div className={styles.searchInputWrapper}>
            <span className={styles.searchIcon}>🔍</span>
            <input
              ref={searchRef}
              className={styles.searchInput}
              type="search"
              placeholder="청크 내용 검색…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                className={styles.clearBtn}
                onClick={() => setSearchQuery("")}
                aria-label="검색어 지우기"
              >
                ×
              </button>
            )}
          </div>
          {searchQuery.trim() && (
            <span className={styles.resultCount}>
              {filteredChunks.length} / {chunks.length} 청크
              {chunks.length < total && (
                <span className={styles.loadNote}> (전체 {total}중 {chunks.length} 로드됨)</span>
              )}
            </span>
          )}
        </div>

        <div className={styles.body}>
          {loading && chunks.length === 0 ? (
            <div className={styles.stateMsg}>불러오는 중…</div>
          ) : error ? (
            <div className={styles.errorMsg}>
              <span>{error}</span>
              <button className={styles.retryBtn} onClick={() => fetchChunks(0, false)}>
                다시 시도
              </button>
            </div>
          ) : chunks.length === 0 ? (
            <div className={styles.stateMsg}>청크가 없습니다.</div>
          ) : filteredChunks.length === 0 ? (
            <div className={styles.stateMsg}>일치하는 청크가 없습니다. 다른 검색어를 시도해보세요.</div>
          ) : (
            <ol className={styles.chunkList}>
              {filteredChunks.map((chunk) => (
                <li key={chunk.id} className={styles.chunkItem}>
                  <span className={styles.chunkBadge}>#{chunk.chunk_index + 1}</span>
                  <p className={styles.chunkText}>
                    {highlightText(chunk.content, searchQuery)}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>

        {hasMore && !loading && (
          <div className={styles.footer}>
            <button
              className={styles.loadMoreBtn}
              onClick={() => fetchChunks(chunks.length, true)}
              disabled={loadingMore}
            >
              {loadingMore ? "로딩 중…" : `더 보기 (${chunks.length} / ${total})`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
