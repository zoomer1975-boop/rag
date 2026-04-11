"use client";

import { useState } from "react";
import { type Tenant } from "@/lib/api";
import styles from "./WidgetPanel.module.css";

interface Props {
  tenant: Tenant;
}

export default function WidgetPanel({ tenant }: Props) {
  const [copied, setCopied] = useState(false);
  const widgetOrigin = typeof window !== "undefined" ? window.location.origin : "https://your-domain.com";
  const scriptUrl = `${widgetOrigin}/rag/widget/chatbot.js`;

  const snippet = `<script>
  window.RagChatConfig = {
    apiKey: "${tenant.api_key}",
    apiUrl: "${widgetOrigin}/rag/api/v1/chat"
  };
</script>
<script src="${scriptUrl}" defer></script>`;

  async function copy() {
    await navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div>
      <h2 className={styles.heading}>위젯 삽입 코드</h2>
      <p className={styles.desc}>
        아래 코드를 고객 홈페이지의 <code>&lt;/body&gt;</code> 태그 바로 앞에 붙여넣으세요.
      </p>

      <div className={styles.codeBlock}>
        <pre className={styles.code}>{snippet}</pre>
        <button className={styles.copyBtn} onClick={copy}>
          {copied ? "복사됨 ✓" : "복사"}
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
