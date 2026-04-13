"use client";

import { useEffect, useRef, useState } from "react";
import { type Tenant } from "@/lib/api";
import styles from "./ChatTestPanel.module.css";

// ─── 경량 Markdown 렌더러 ────────────────────────────────────────────────────
// LLM 출력에서 자주 쓰이는 패턴을 React 엘리먼트로 변환.
// dangerouslySetInnerHTML 미사용 — XSS 안전.

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 코드 블록 (```)
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre key={i} className={styles.mdPre}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      i++;
      continue;
    }

    // 헤딩 (# ## ###)
    const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = inlineSpans(headingMatch[2]);
      const Tag = (`h${level + 2}`) as "h3" | "h4" | "h5";
      nodes.push(<Tag key={i} className={styles.mdHeading}>{content}</Tag>);
      i++;
      continue;
    }

    // 순서 없는 리스트 (- * 항목)
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s/, ""));
        i++;
      }
      nodes.push(
        <ul key={i} className={styles.mdList}>
          {items.map((it, j) => <li key={j}>{inlineSpans(it)}</li>)}
        </ul>
      );
      continue;
    }

    // 순서 있는 리스트 (1. 2.)
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      nodes.push(
        <ol key={i} className={styles.mdList}>
          {items.map((it, j) => <li key={j}>{inlineSpans(it)}</li>)}
        </ol>
      );
      continue;
    }

    // 구분선
    if (/^---+$/.test(line.trim())) {
      nodes.push(<hr key={i} className={styles.mdHr} />);
      i++;
      continue;
    }

    // 빈 줄
    if (line.trim() === "") {
      nodes.push(<br key={i} />);
      i++;
      continue;
    }

    // 일반 단락
    nodes.push(<p key={i} className={styles.mdPara}>{inlineSpans(line)}</p>);
    i++;
  }

  return nodes;
}

// 인라인 요소: [link](url), **bold**, *italic*, `code`
function inlineSpans(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // 패턴: [text](url) | **bold** | *italic* | `code`
  const re = /(\[(.+?)\]\(([^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    if (match[0].startsWith("[")) {
      parts.push(
        <a key={match.index} href={match[3]} target="_blank" rel="noopener noreferrer" className={styles.mdLink}>
          {match[2]}
        </a>
      );
    } else if (match[0].startsWith("**")) {
      parts.push(<strong key={match.index}>{match[4]}</strong>);
    } else if (match[0].startsWith("*")) {
      parts.push(<em key={match.index}>{match[5]}</em>);
    } else {
      parts.push(<code key={match.index} className={styles.mdCode}>{match[6]}</code>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

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
              {msg.role === "assistant"
                ? renderMarkdown(msg.content)
                : msg.content}
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
