/**
 * RAG Chatbot Widget — Vanilla JS with Shadow DOM
 * Usage:
 *   <script>
 *     window.RagChatConfig = {
 *       apiKey: "tenant_xxxxx",
 *       apiUrl: "https://your-domain.com/rag/api/v1/chat"
 *     };
 *   </script>
 *   <script src="/rag/widget/chatbot.js" defer></script>
 */
(function () {
  "use strict";

  const cfg = window.RagChatConfig || {};
  const API_KEY = cfg.apiKey || "";
  const API_URL = cfg.apiUrl || "/rag/api/v1/chat";

  if (!API_KEY) {
    console.warn("[RagChat] apiKey가 설정되지 않았습니다.");
    return;
  }

  // ─── State ───────────────────────────────────────────────────────────────

  let sessionId = null;
  let isOpen = false;
  let isStreaming = false;
  let abortController = null;

  // ─── Shadow DOM mount ─────────────────────────────────────────────────────

  const host = document.createElement("div");
  host.id = "rag-chatbot-host";
  host.style.cssText = "position:fixed;z-index:2147483647;";
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: "closed" });

  // ─── Styles ───────────────────────────────────────────────────────────────

  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    .widget-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      border: none;
      background: var(--accent, #6366f1);
      color: #fff;
      font-size: 24px;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0,0,0,0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
      z-index: 1;
    }
    .widget-btn:hover { transform: scale(1.07); box-shadow: 0 6px 24px rgba(0,0,0,0.4); }

    .window {
      position: fixed;
      bottom: 92px;
      right: 24px;
      width: 360px;
      max-width: calc(100vw - 32px);
      height: 540px;
      max-height: calc(100vh - 120px);
      background: #1a1d27;
      border: 1px solid #2e3147;
      border-radius: 16px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.6);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transform-origin: bottom right;
      transition: transform 0.2s cubic-bezier(0.16,1,0.3,1), opacity 0.2s;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      font-size: 14px;
      color: #e8eaf0;
    }
    .window.hidden { transform: scale(0.92); opacity: 0; pointer-events: none; }

    .window-header {
      background: var(--accent, #6366f1);
      padding: 14px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .window-title {
      font-size: 15px;
      font-weight: 700;
      color: #fff;
    }
    .close-btn {
      background: transparent;
      border: none;
      color: rgba(255,255,255,0.8);
      font-size: 20px;
      cursor: pointer;
      line-height: 1;
      padding: 4px;
      border-radius: 6px;
      transition: background 0.15s;
    }
    .close-btn:hover { background: rgba(255,255,255,0.15); }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      scroll-behavior: smooth;
    }
    .messages::-webkit-scrollbar { width: 4px; }
    .messages::-webkit-scrollbar-track { background: transparent; }
    .messages::-webkit-scrollbar-thumb { background: #2e3147; border-radius: 4px; }

    .msg {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-width: 86%;
    }
    .msg.user { align-self: flex-end; align-items: flex-end; }
    .msg.assistant { align-self: flex-start; align-items: flex-start; }

    .bubble {
      padding: 10px 14px;
      border-radius: 16px;
      line-height: 1.6;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .msg.user .bubble {
      background: var(--accent, #6366f1);
      color: #fff;
      border-radius: 16px 16px 4px 16px;
    }
    .msg.assistant .bubble {
      background: #252836;
      color: #e8eaf0;
      border-radius: 16px 16px 16px 4px;
    }

    .sources {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 4px;
    }
    .source-chip {
      font-size: 11px;
      color: #7c8099;
      background: #1a1d27;
      border: 1px solid #2e3147;
      border-radius: 20px;
      padding: 3px 10px;
      text-decoration: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 200px;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .source-chip:hover { border-color: var(--accent, #6366f1); color: #e8eaf0; }

    .typing {
      display: flex;
      gap: 5px;
      align-items: center;
      padding: 12px 14px;
      background: #252836;
      border-radius: 16px 16px 16px 4px;
      align-self: flex-start;
    }
    .dot {
      width: 7px;
      height: 7px;
      background: #7c8099;
      border-radius: 50%;
      animation: bounce 1.2s ease-in-out infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.2s; }
    .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-6px); }
    }

    .greeting {
      color: #7c8099;
      font-size: 13px;
      text-align: center;
      padding: 8px 0;
    }

    .input-area {
      padding: 12px;
      border-top: 1px solid #2e3147;
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }
    .input-area input {
      flex: 1;
      background: #252836;
      border: 1px solid #2e3147;
      border-radius: 22px;
      color: #e8eaf0;
      padding: 10px 16px;
      outline: none;
      font-family: inherit;
      font-size: 14px;
      transition: border-color 0.15s;
    }
    .input-area input:focus { border-color: var(--accent, #6366f1); }
    .input-area input::placeholder { color: #4d5175; }
    .send-btn {
      width: 40px;
      height: 40px;
      border: none;
      border-radius: 50%;
      background: var(--accent, #6366f1);
      color: #fff;
      font-size: 16px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: opacity 0.15s;
    }
    .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .send-btn:not(:disabled):hover { opacity: 0.85; }

    .error-msg {
      color: #f87171;
      font-size: 12px;
      text-align: center;
      padding: 4px 0;
    }

    .quick-replies {
      padding: 8px 12px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      flex-shrink: 0;
    }
    .quick-replies.hidden { display: none; }
    .qr-chip {
      font-size: 12px;
      color: var(--accent, #6366f1);
      background: transparent;
      border: 1px solid var(--accent, #6366f1);
      border-radius: 20px;
      padding: 4px 12px;
      cursor: pointer;
      font-family: inherit;
      transition: background 0.15s, color 0.15s;
      white-space: nowrap;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .qr-chip:hover { background: var(--accent, #6366f1); color: #fff; }
    .qr-chip:disabled { opacity: 0.4; cursor: not-allowed; }
  `;

  // ─── HTML Structure ───────────────────────────────────────────────────────

  const container = document.createElement("div");
  container.innerHTML = `
    <button class="widget-btn" id="toggle-btn" aria-label="챗봇 열기/닫기">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
    </button>
    <div class="window hidden" id="chat-window" role="dialog" aria-label="챗봇">
      <div class="window-header">
        <span class="window-title" id="window-title">챗봇</span>
        <button class="close-btn" id="close-btn" aria-label="닫기">×</button>
      </div>
      <div class="messages" id="messages" aria-live="polite"></div>
      <div class="quick-replies hidden" id="quick-replies"></div>
      <div class="input-area">
        <input type="text" id="msg-input" placeholder="메시지를 입력하세요..." autocomplete="off" />
        <button class="send-btn" id="send-btn" disabled aria-label="전송">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  shadow.appendChild(style);
  shadow.appendChild(container);

  // ─── Element refs ─────────────────────────────────────────────────────────

  const toggleBtn = shadow.getElementById("toggle-btn");
  const closeBtn = shadow.getElementById("close-btn");
  const chatWindow = shadow.getElementById("chat-window");
  const messages = shadow.getElementById("messages");
  const msgInput = shadow.getElementById("msg-input");
  const sendBtn = shadow.getElementById("send-btn");
  const windowTitle = shadow.getElementById("window-title");
  const quickRepliesEl = shadow.getElementById("quick-replies");

  // ─── Widget config applied at runtime ─────────────────────────────────────

  function applyConfig(config) {
    if (!config) return;
    const accent = config.primary_color || config.primaryColor;
    if (accent) container.style.setProperty("--accent", accent);
    if (config.title) windowTitle.textContent = config.title;
    const pos = config.position;
    if (pos === "bottom-left") {
      toggleBtn.style.right = "auto";
      toggleBtn.style.left = "24px";
      chatWindow.style.right = "auto";
      chatWindow.style.left = "24px";
      chatWindow.style.transformOrigin = "bottom left";
    }
    if (config.placeholder) msgInput.placeholder = config.placeholder;
    if (config.greeting && messages.querySelector(".greeting") === null) {
      const greet = document.createElement("p");
      greet.className = "greeting";
      greet.textContent = config.greeting;
      messages.appendChild(greet);
    }
    const replies = config.quick_replies;
    if (Array.isArray(replies) && replies.length > 0) {
      quickRepliesEl.innerHTML = "";
      replies.forEach((text) => {
        const btn = document.createElement("button");
        btn.className = "qr-chip";
        btn.textContent = text;
        btn.type = "button";
        btn.addEventListener("click", () => {
          if (isStreaming) return;
          msgInput.value = text;
          sendBtn.disabled = false;
          msgInput.focus();
        });
        quickRepliesEl.appendChild(btn);
      });
      quickRepliesEl.classList.remove("hidden");
    }
  }

  // Fetch widget config from API on init
  const configUrl = API_URL.replace(/\/chat$/, "/chat/widget-config");
  fetch(configUrl, {
    headers: { "X-API-Key": API_KEY },
  })
    .then((r) => r.ok ? r.json() : null)
    .then((data) => applyConfig(data))
    .catch(() => {});

  // Apply script-level overrides immediately for fast first paint
  if (cfg.primaryColor) container.style.setProperty("--accent", cfg.primaryColor);
  if (cfg.title) windowTitle.textContent = cfg.title;
  if (cfg.position === "bottom-left") {
    toggleBtn.style.right = "auto";
    toggleBtn.style.left = "24px";
    chatWindow.style.right = "auto";
    chatWindow.style.left = "24px";
    chatWindow.style.transformOrigin = "bottom left";
  }
  if (cfg.greeting) {
    const greet = document.createElement("p");
    greet.className = "greeting";
    greet.textContent = cfg.greeting;
    messages.appendChild(greet);
  }

  // ─── UI helpers ───────────────────────────────────────────────────────────

  function openWidget() {
    isOpen = true;
    chatWindow.classList.remove("hidden");
    toggleBtn.setAttribute("aria-label", "챗봇 닫기");
    msgInput.focus();
  }

  function closeWidget() {
    isOpen = false;
    chatWindow.classList.add("hidden");
    toggleBtn.setAttribute("aria-label", "챗봇 열기");
  }

  function appendMessage(role, text) {
    const msgEl = document.createElement("div");
    msgEl.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    msgEl.appendChild(bubble);
    messages.appendChild(msgEl);
    scrollToBottom();
    return bubble;
  }

  function appendTypingIndicator() {
    const el = document.createElement("div");
    el.className = "typing";
    el.id = "typing-indicator";
    el.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    messages.appendChild(el);
    scrollToBottom();
    return el;
  }

  function appendSources(sourcesData) {
    if (!sourcesData || sourcesData.length === 0) return;
    const lastMsg = messages.querySelector(".msg.assistant:last-child");
    if (!lastMsg) return;
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "sources";
    sourcesData.slice(0, 5).forEach((src) => {
      const chip = document.createElement("a");
      chip.className = "source-chip";
      chip.textContent = src.title || src.source_url || "출처";
      if (src.source_url) {
        chip.href = src.source_url;
        chip.target = "_blank";
        chip.rel = "noopener noreferrer";
      }
      sourcesEl.appendChild(chip);
    });
    lastMsg.appendChild(sourcesEl);
  }

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function showError(text) {
    const el = document.createElement("p");
    el.className = "error-msg";
    el.textContent = text;
    messages.appendChild(el);
    scrollToBottom();
    setTimeout(() => el.remove(), 5000);
  }

  function setInputEnabled(enabled) {
    msgInput.disabled = !enabled;
    sendBtn.disabled = !enabled;
    isStreaming = !enabled;
    quickRepliesEl.querySelectorAll(".qr-chip").forEach((btn) => {
      btn.disabled = !enabled;
    });
  }

  // ─── Chat ─────────────────────────────────────────────────────────────────

  async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text || isStreaming) return;

    msgInput.value = "";
    setInputEnabled(false);
    appendMessage("user", text);

    const typing = appendTypingIndicator();
    let assistantBubble = null;

    abortController = new AbortController();

    try {
      const body = JSON.stringify({ message: text, session_id: sessionId });
      const lang = navigator.language || navigator.languages?.[0] || "ko";

      const res = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": API_KEY,
          "Accept-Language": lang,
        },
        body,
        signal: abortController.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let event;
          try {
            event = JSON.parse(raw);
          } catch {
            continue;
          }

          if (event.type === "session") {
            sessionId = event.session_id;
          } else if (event.type === "sources") {
            // Sources come after the assistant bubble is rendered
            requestAnimationFrame(() => appendSources(event.sources));
          } else if (event.type === "token") {
            if (!assistantBubble) {
              typing.remove();
              const msgEl = document.createElement("div");
              msgEl.className = "msg assistant";
              assistantBubble = document.createElement("div");
              assistantBubble.className = "bubble";
              msgEl.appendChild(assistantBubble);
              messages.appendChild(msgEl);
            }
            assistantBubble.textContent += event.content;
            scrollToBottom();
          } else if (event.type === "done") {
            // Stream complete
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        typing.remove();
        showError("메시지 전송에 실패했습니다. 다시 시도해 주세요.");
      }
    } finally {
      const remainingTyping = shadow.getElementById("typing-indicator");
      if (remainingTyping) remainingTyping.remove();
      setInputEnabled(true);
      msgInput.focus();
      abortController = null;
    }
  }

  // ─── Event listeners ─────────────────────────────────────────────────────

  toggleBtn.addEventListener("click", () => (isOpen ? closeWidget() : openWidget()));
  closeBtn.addEventListener("click", closeWidget);

  msgInput.addEventListener("input", () => {
    sendBtn.disabled = msgInput.value.trim() === "" || isStreaming;
  });

  msgInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener("click", sendMessage);

  // Close on outside click
  document.addEventListener("click", (e) => {
    if (isOpen && !host.contains(e.target)) closeWidget();
  });

  // Keyboard shortcut: Escape to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) closeWidget();
  });
})();
