"use client";

import { useState } from "react";
import { type Tenant } from "@/lib/api";
import styles from "./WidgetPanel.module.css";

interface Props {
  tenant: Tenant;
}

type Tab = "script" | "iframe" | "link";

export default function WidgetPanel({ tenant }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("script");
  const [copiedTab, setCopiedTab] = useState<Tab | null>(null);

  const widgetOrigin = typeof window !== "undefined" ? window.location.origin : "https://your-domain.com";
  const scriptUrl = `${widgetOrigin}/rag/widget/chatbot.js`;
  const chatUrl = `${widgetOrigin}/rag/chat?apiKey=${tenant.api_key}`;

  const snippets: Record<Tab, string> = {
    script: `<script>
  window.RagChatConfig = {
    apiKey: "${tenant.api_key}",
    apiUrl: "${widgetOrigin}/rag/api/v1/chat"
  };
</script>
<script src="${scriptUrl}" defer></script>`,

    iframe: `<style>
  #rc{display:none}
  .rc-btn{position:fixed;bottom:24px;right:24px;width:64px;height:64px;
    border-radius:20px;background:linear-gradient(135deg,#6366f1,#a855f7);
    color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;
    z-index:9999;box-shadow:0 8px 24px rgba(99,102,241,.4);border:none}
  .rc-overlay{display:none;position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,.4)}
  .rc-frame{display:none;position:fixed;bottom:104px;right:24px;width:400px;height:640px;
    max-width:calc(100vw - 48px);max-height:calc(100vh - 140px);
    border:none;border-radius:28px;box-shadow:0 20px 50px rgba(0,0,0,.4);z-index:9999}
  #rc:checked~.rc-overlay,#rc:checked~.rc-frame{display:block}
</style>
<input type="checkbox" id="rc">
<label class="rc-btn" for="rc">
  <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
  </svg>
</label>
<label class="rc-overlay" for="rc"></label>
<iframe class="rc-frame"
  src="${chatUrl}"
  loading="lazy" title="챗봇"></iframe>`,

    link: `<button onclick="window.open('${chatUrl}','ragchat','width=420,height=700,top=100,left=100,resizable=yes')"
  style="position:fixed;bottom:24px;right:24px;width:64px;height:64px;
    border-radius:20px;background:linear-gradient(135deg,#6366f1,#a855f7);
    color:#fff;border:none;cursor:pointer;display:flex;align-items:center;
    justify-content:center;z-index:9999;box-shadow:0 8px 24px rgba(99,102,241,.4)">
  <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
  </svg>
</button>`,
  };

  const tabLabels: Record<Tab, string> = {
    script: "스크립트 삽입",
    iframe: "CSS 오버레이 (권장)",
    link: "새 탭 열기",
  };

  const tabDescs: Record<Tab, { text: string; csp?: string }> = {
    script: {
      text: "아래 코드를 고객 홈페이지의 </body> 태그 바로 앞에 붙여넣으세요.",
      csp: "CSP 요구사항: script-src에 RAG 도메인 추가 필요",
    },
    iframe: {
      text: "JavaScript 없이 동작하는 CSS-only 오버레이입니다. 버튼 클릭 시 iframe 채팅창이 열립니다.",
      csp: "CSP 요구사항: frame-src에 RAG 도메인 추가 필요 (script-src 변경 불필요)",
    },
    link: {
      text: "채팅창을 새 탭으로 여는 방식입니다. CSP 변경이 전혀 필요하지 않습니다.",
    },
  };

  async function copy(tab: Tab) {
    await navigator.clipboard.writeText(snippets[tab]);
    setCopiedTab(tab);
    setTimeout(() => setCopiedTab(null), 2000);
  }

  const desc = tabDescs[activeTab];

  return (
    <div>
      <h2 className={styles.heading}>위젯 삽입 코드</h2>

      <div className={styles.tabs}>
        {(["script", "iframe", "link"] as Tab[]).map((tab) => (
          <button
            key={tab}
            className={`${styles.tabBtn} ${activeTab === tab ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </div>

      <p className={styles.desc}>{desc.text}</p>
      {desc.csp && (
        <p className={styles.cspNote}>{desc.csp}</p>
      )}

      <div className={styles.codeBlock}>
        <pre className={styles.code}>{snippets[activeTab]}</pre>
        <button className={styles.copyBtn} onClick={() => copy(activeTab)}>
          {copiedTab === activeTab ? "복사됨 ✓" : "복사"}
        </button>
      </div>

      <div className={styles.preview}>
        <h3 className={styles.previewHeading}>위젯 미리보기</h3>
        <div
          className={styles.mockWidget}
          style={{ "--accent": tenant.widget_config.primary_color } as React.CSSProperties}
        >
          <div className={styles.mockHeader}>
            <span>{tenant.widget_config.title}</span>
          </div>
          <div className={styles.mockBody}>
            <div className={styles.mockBubble}>{tenant.widget_config.greeting}</div>
          </div>
          <div className={styles.mockFooter}>
            <input
              readOnly
              className={styles.mockInput}
              placeholder={tenant.widget_config.placeholder}
            />
            <button className={styles.mockSend} style={{ background: tenant.widget_config.primary_color }}>
              →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
