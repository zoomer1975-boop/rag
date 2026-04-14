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
    :host { all: initial; font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    * { box-sizing: border-box; margin: 0; padding: 0; }

    .widget-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 64px;
      height: 64px;
      border-radius: 20px;
      border: none;
      background: linear-gradient(135deg, var(--accent, #6366f1) 0%, #a855f7 100%);
      color: #fff;
      font-size: 28px;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      z-index: 1;
    }
    .widget-btn:hover { transform: scale(1.1) rotate(5deg); box-shadow: 0 12px 32px rgba(99, 102, 241, 0.5); }
    .widget-btn svg { transition: transform 0.3s; }
    .widget-btn:hover svg { transform: scale(1.1); }

    .window {
      position: fixed;
      bottom: 104px;
      right: 24px;
      width: 400px;
      max-width: calc(100vw - 48px);
      height: 640px;
      max-height: calc(100vh - 140px);
      background: rgba(26, 29, 39, 0.85);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 28px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transform-origin: bottom right;
      transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
      color: #f1f1f1;
      z-index: 2;
    }
    .window.hidden { 
      transform: scale(0.8) translateY(40px); 
      opacity: 0; 
      pointer-events: none; 
      visibility: hidden;
    }

    .window-header {
      background: rgba(255, 255, 255, 0.03);
      padding: 20px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      flex-shrink: 0;
    }
    .window-title {
      font-size: 18px;
      font-weight: 700;
      background: linear-gradient(90deg, #fff, #a855f7);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .close-btn {
      background: rgba(255, 255, 255, 0.05);
      border: none;
      color: #fff;
      width: 32px;
      height: 32px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background 0.2s, transform 0.2s;
    }
    .close-btn:hover { background: rgba(255, 255, 255, 0.15); transform: rotate(90deg); }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      scroll-behavior: smooth;
    }
    .messages::-webkit-scrollbar { width: 6px; }
    .messages::-webkit-scrollbar-track { background: transparent; }
    .messages::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }

    .msg {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 88%;
      animation: fadeInMsg 0.4s ease forwards;
    }
    @keyframes fadeInMsg {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .msg.user { align-self: flex-end; align-items: flex-end; }
    .msg.assistant { align-self: flex-start; align-items: flex-start; }

    .bubble {
      padding: 12px 18px;
      font-size: 15px;
      line-height: 1.5;
      word-break: break-all;
      white-space: pre-wrap;
      position: relative;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .msg.user .bubble {
      background: linear-gradient(135deg, var(--accent, #6366f1) 0%, #8b5cf6 100%);
      color: #fff;
      border-radius: 22px 22px 4px 22px;
    }
    .msg.assistant .bubble {
      background: rgba(255, 255, 255, 0.08);
      color: #e2e8f0;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 22px 22px 22px 4px;
    }

    .typing {
      display: flex;
      gap: 6px;
      padding: 14px 20px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 22px 22px 22px 4px;
      align-self: flex-start;
      margin-top: 4px;
    }
    .dot {
      width: 6px;
      height: 6px;
      background: #a855f7;
      border-radius: 50%;
      animation: dotBounce 1.4s infinite ease-in-out;
    }
    .dot:nth-child(2) { animation-delay: 0.2s; }
    .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes dotBounce {
      0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
      40% { transform: scale(1.2) translateY(-4px); opacity: 1; }
    }

    .greeting {
      color: #94a3b8;
      font-size: 13px;
      text-align: center;
      padding: 12px 0;
      opacity: 0.8;
      font-style: italic;
    }

    .input-area {
      padding: 20px 24px 24px;
      display: flex;
      gap: 12px;
      background: transparent;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      flex-shrink: 0;
    }
    .input-area input {
      flex: 1;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 18px;
      color: #fff;
      padding: 12px 20px;
      outline: none;
      font-size: 15px;
      transition: all 0.3s;
    }
    .input-area input:focus { 
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--accent, #6366f1);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
    }
    .input-area input::placeholder { color: #64748b; }
    .send-btn {
      width: 48px;
      height: 48px;
      border: none;
      border-radius: 16px;
      background: linear-gradient(135deg, var(--accent, #6366f1) 0%, #a855f7 100%);
      color: #fff;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }
    .send-btn:disabled { opacity: 0.3; cursor: not-allowed; filter: grayscale(1); }
    .send-btn:not(:disabled):hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4); }

    .error-msg {
      color: #fb7185;
      font-size: 12px;
      text-align: center;
      background: rgba(251, 113, 133, 0.1);
      padding: 8px;
      border-radius: 10px;
      margin: 8px 0;
    }

    .quick-replies {
      padding: 0 24px 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      flex-shrink: 0;
    }
    .quick-replies.hidden { display: none; }
    .qr-chip {
      font-size: 13px;
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 14px;
      padding: 6px 14px;
      cursor: pointer;
      transition: all 0.3s;
    }
    .qr-chip:hover { 
      background: rgba(99, 102, 241, 0.1); 
      border-color: var(--accent, #6366f1);
      color: var(--accent, #6366f1);
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
    if (config.button_icon_url) {
      const img = document.createElement("img");
      img.src = config.button_icon_url;
      img.width = 56;
      img.height = 56;
      img.alt = "";
      img.style.cssText = "border-radius:50%;object-fit:cover;display:block;width:100%;height:100%;";
      toggleBtn.innerHTML = "";
      toggleBtn.appendChild(img);
      toggleBtn.style.background = "transparent";
      toggleBtn.style.padding = "0";
      toggleBtn.style.overflow = "hidden";
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
    // sources display disabled
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
