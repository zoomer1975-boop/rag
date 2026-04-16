"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch, type Conversation, type Message } from "@/lib/api";
import { formatConversationAsMarkdown, formatMultipleConversationsAsMarkdown } from "@/lib/markdown";
import { downloadAsFile, makeConversationFilename, makeBulkFilename } from "@/lib/download";
import styles from "./ConversationHistoryPanel.module.css";

interface Props {
  apiKey: string;
}

const PAGE_SIZE = 20;
const BATCH_SIZE = 5;

export default function ConversationHistoryPanel({ apiKey }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const [selected, setSelected] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msgError, setMsgError] = useState<string | null>(null);

  // ── 선택/일괄 다운로드 상태 ──────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ current: number; total: number } | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const loadConversations = useCallback(
    async (newOffset: number) => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<Conversation[]>(
          `/analytics/conversations?limit=${PAGE_SIZE}&offset=${newOffset}`,
          apiKey
        );
        if (newOffset === 0) {
          setConversations(data);
        } else {
          setConversations((prev) => [...prev, ...data]);
        }
        setHasMore(data.length === PAGE_SIZE);
        setOffset((prev) => prev + data.length);
      } catch (err) {
        setError(err instanceof Error ? err.message : "대화 목록을 불러오지 못했습니다.");
      } finally {
        setLoading(false);
      }
    },
    [apiKey]
  );

  useEffect(() => {
    loadConversations(0);
  }, [loadConversations]);

  async function openConversation(conv: Conversation) {
    setSelected(conv);
    setMessages([]);
    setMsgError(null);
    setMsgLoading(true);
    try {
      const data = await apiFetch<Message[]>(
        `/analytics/conversations/${conv.session_id}/messages`,
        apiKey
      );
      setMessages(data);
    } catch (err) {
      setMsgError(err instanceof Error ? err.message : "메시지를 불러오지 못했습니다.");
    } finally {
      setMsgLoading(false);
    }
  }

  function handleSingleDownload() {
    if (!selected || messages.length === 0) return;
    const md = formatConversationAsMarkdown(selected, messages);
    downloadAsFile(md, makeConversationFilename(selected.session_id));
  }

  // ── 체크박스 선택 ────────────────────────────────────────
  const allSelected =
    conversations.length > 0 && conversations.every((c) => selectedIds.has(c.id));

  function toggleSelectAll() {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(conversations.map((c) => c.id)));
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ── 일괄 다운로드 ────────────────────────────────────────
  async function handleBulkDownload() {
    const ids = [...selectedIds];
    if (ids.length === 0) return;

    setBulkDownloading(true);
    setBulkError(null);
    setBulkProgress({ current: 0, total: ids.length });

    try {
      const targets = conversations.filter((c) => ids.includes(c.id));
      const results: Array<{ conversation: Conversation; messages: Message[] }> = [];

      for (let i = 0; i < targets.length; i += BATCH_SIZE) {
        const batch = targets.slice(i, i + BATCH_SIZE);
        const batchResults = await Promise.all(
          batch.map((conv) =>
            apiFetch<Message[]>(
              `/analytics/conversations/${conv.session_id}/messages`,
              apiKey
            ).then((msgs) => ({ conversation: conv, messages: msgs }))
          )
        );
        results.push(...batchResults);
        setBulkProgress({ current: results.length, total: ids.length });
      }

      const md = formatMultipleConversationsAsMarkdown(results);
      downloadAsFile(md, makeBulkFilename());
      setSelectedIds(new Set());
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "다운로드 실패");
    } finally {
      setBulkDownloading(false);
      setBulkProgress(null);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  // ── 대화 상세 뷰 ─────────────────────────────────────────
  if (selected) {
    return (
      <div className={styles.root}>
        <div className={styles.detailTopBar}>
          <button className={styles.back} onClick={() => setSelected(null)}>
            ← 목록으로
          </button>
          <button
            className={styles.downloadBtn}
            onClick={handleSingleDownload}
            disabled={msgLoading || messages.length === 0}
          >
            ↓ MD 다운로드
          </button>
        </div>
        <div className={styles.threadHeader}>
          <span className={styles.sessionId}>{selected.session_id}</span>
          <span className={styles.meta}>
            {selected.lang_code.toUpperCase()} · {formatDate(selected.created_at)}
          </span>
        </div>
        {msgLoading ? (
          <p className={styles.empty}>불러오는 중…</p>
        ) : msgError ? (
          <p className={styles.empty}>{msgError}</p>
        ) : messages.length === 0 ? (
          <p className={styles.empty}>메시지가 없습니다.</p>
        ) : (
          <div className={styles.thread}>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`${styles.bubble} ${msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}`}
              >
                <span className={styles.roleLabel}>
                  {msg.role === "user" ? "사용자" : "어시스턴트"}
                </span>
                <p className={styles.bubbleContent}>{msg.content}</p>
                {msg.sources && msg.sources.length > 0 && (
                  <ul className={styles.sources}>
                    {msg.sources.map((s, j) => (
                      <li key={j}>
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
                <time className={styles.time}>{formatDate(msg.created_at)}</time>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── 목록 뷰 ─────────────────────────────────────────────
  return (
    <div className={styles.root}>
      <div className={styles.listTopBar}>
        <h2 className={styles.heading}>대화 이력</h2>
        {selectedIds.size > 0 && (
          <div className={styles.bulkActions}>
            <span className={styles.selectedCount}>{selectedIds.size}개 선택됨</span>
            <button
              className={styles.downloadBtn}
              onClick={handleBulkDownload}
              disabled={bulkDownloading}
            >
              {bulkDownloading && bulkProgress
                ? `다운로드 중… ${bulkProgress.current}/${bulkProgress.total}`
                : `↓ MD 다운로드 (${selectedIds.size}개)`}
            </button>
            <button
              className={styles.cancelBtn}
              onClick={() => setSelectedIds(new Set())}
              disabled={bulkDownloading}
            >
              선택 해제
            </button>
          </div>
        )}
      </div>

      {bulkError && <p className={styles.bulkError}>{bulkError}</p>}
      {error && <p className={styles.empty}>{error}</p>}

      {conversations.length === 0 && !loading && !error ? (
        <p className={styles.empty}>대화 기록이 없습니다.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.checkboxCell}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  aria-label="전체 선택"
                />
              </th>
              <th>세션 ID</th>
              <th>언어</th>
              <th>메시지</th>
              <th>생성일</th>
            </tr>
          </thead>
          <tbody>
            {conversations.map((conv) => (
              <tr
                key={conv.id}
                className={`${styles.row} ${selectedIds.has(conv.id) ? styles.rowSelected : ""}`}
                onClick={() => openConversation(conv)}
              >
                <td
                  className={styles.checkboxCell}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleSelect(conv.id);
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(conv.id)}
                    onChange={() => toggleSelect(conv.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </td>
                <td>
                  <code className={styles.sid}>{conv.session_id.slice(0, 8)}…</code>
                </td>
                <td>{conv.lang_code.toUpperCase()}</td>
                <td>{conv.message_count}</td>
                <td>{formatDate(conv.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {loading && <p className={styles.empty}>불러오는 중…</p>}
      {!loading && hasMore && (
        <button
          className={styles.loadMore}
          onClick={() => loadConversations(offset)}
        >
          더 불러오기
        </button>
      )}
    </div>
  );
}
