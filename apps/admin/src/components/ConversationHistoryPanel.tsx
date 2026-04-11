"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch, type Conversation, type Message } from "@/lib/api";
import styles from "./ConversationHistoryPanel.module.css";

interface Props {
  apiKey: string;
}

const PAGE_SIZE = 20;

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

  function formatDate(iso: string) {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  if (selected) {
    return (
      <div className={styles.root}>
        <button className={styles.back} onClick={() => setSelected(null)}>
          ← 목록으로
        </button>
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

  return (
    <div className={styles.root}>
      <h2 className={styles.heading}>대화 이력</h2>
      {error && <p className={styles.empty}>{error}</p>}
      {conversations.length === 0 && !loading && !error ? (
        <p className={styles.empty}>대화 기록이 없습니다.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
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
                className={styles.row}
                onClick={() => openConversation(conv)}
              >
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
