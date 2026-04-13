"use client";

import { useEffect, useRef, useState } from "react";
import { type Tenant } from "@/lib/api";
import styles from "./ChatTestPanel.module.css";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ title: string; url: string }>;
  streaming?: boolean;
}

interface Props {
  tenant: Tenant;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/rag/api/v1";

export default function ChatTestPanel({ tenant }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function resetSession() {
    setMessages([]);
    setSessionId(null);
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    setInput("");
    setBusy(true);

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      const res = await fetch(
        `${API_BASE}/tenants/${tenant.id}/chat-test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, session_id: sessionId }),
        }
      );

      if (!res.ok) {
        const err = await res.text();
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: `오류: ${err || res.statusText}`,
          };
          return next;
        });
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let newSessionId = sessionId;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "session") {
              newSessionId = event.session_id;
              setSessionId(event.session_id);
            } else if (event.type === "token") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...last,
                  content: last.content + event.content,
                };
                return next;
              });
            } else if (event.type === "sources") {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  sources: event.sources,
                };
                return next;
              });
            } else if (event.type === "done") {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  streaming: false,
                };
                return next;
              });
            }
          } catch {
            // malformed JSON — skip
          }
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `연결 오류: ${e instanceof Error ? e.message : String(e)}`,
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <span className={styles.hint}>
          {sessionId ? `세션: ${sessionId.slice(0, 8)}…` : "새 대화"}
        </span>
        <button className={styles.resetBtn} onClick={resetSession} disabled={busy}>
          대화 초기화
        </button>
      </div>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <p className={styles.empty}>
            메시지를 입력하면 이 테넌트의 RAG 채팅을 바로 테스트합니다.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.bubble} ${msg.role === "user" ? styles.user : styles.assistant}`}
          >
            <div className={styles.bubbleContent}>
              {msg.content}
              {msg.streaming && <span className={styles.cursor} />}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className={styles.sources}>
                {msg.sources.map((s, j) => (
                  <a
                    key={j}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.source}
                    title={s.url}
                  >
                    {s.title || s.url}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className={styles.inputRow}>
        <textarea
          className={styles.textarea}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="메시지 입력 (Enter 전송, Shift+Enter 줄바꿈)"
          rows={2}
          disabled={busy}
        />
        <button
          className={styles.sendBtn}
          onClick={send}
          disabled={busy || !input.trim()}
        >
          {busy ? "…" : "전송"}
        </button>
      </div>
    </div>
  );
}
