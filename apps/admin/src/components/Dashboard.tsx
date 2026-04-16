"use client";

import { useState } from "react";
import { type Tenant } from "@/lib/api";
import StatsPanel from "./StatsPanel";
import DocumentsPanel from "./DocumentsPanel";
import SettingsPanel from "./SettingsPanel";
import WidgetPanel from "./WidgetPanel";
import ConversationHistoryPanel from "./ConversationHistoryPanel";
import ChatTestPanel from "./ChatTestPanel";
import ApiToolsPanel from "./ApiToolsPanel";
import LogoutButton from "./LogoutButton";
import styles from "./Dashboard.module.css";

type Tab = "stats" | "documents" | "settings" | "widget" | "history" | "chat" | "tools";

const TABS: { id: Tab; label: string }[] = [
  { id: "stats", label: "통계" },
  { id: "documents", label: "문서 관리" },
  { id: "settings", label: "설정" },
  { id: "widget", label: "위젯 코드" },
  { id: "history", label: "대화이력" },
  { id: "chat", label: "채팅 테스트" },
  { id: "tools", label: "API 도구" },
];

interface Props {
  tenant: Tenant;
  apiKey: string;
  onBack: () => void;
  onTenantUpdate: (t: Tenant) => void;
}

export default function Dashboard({ tenant, apiKey, onBack, onTenantUpdate }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("stats");

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <button className={styles.back} onClick={onBack}>
          ← 목록
        </button>
        <div className={styles.headerInfo}>
          <span className={styles.tenantName}>{tenant.name}</span>
          <code className={styles.apiKey}>{apiKey}</code>
        </div>
        <LogoutButton className={styles.logout} />
      </header>
      <nav className={styles.tabs}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <main className={styles.content}>
        {activeTab === "stats" && <StatsPanel apiKey={apiKey} />}
        {activeTab === "documents" && <DocumentsPanel apiKey={apiKey} />}
        {activeTab === "settings" && (
          <SettingsPanel tenant={tenant} onUpdated={onTenantUpdate} />
        )}
        {activeTab === "widget" && <WidgetPanel tenant={tenant} />}
        {activeTab === "history" && <ConversationHistoryPanel apiKey={apiKey} />}
        {activeTab === "chat" && <ChatTestPanel tenant={tenant} />}
        {activeTab === "tools" && <ApiToolsPanel tenant={tenant} />}
      </main>
    </div>
  );
}
