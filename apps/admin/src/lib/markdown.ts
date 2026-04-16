import type { Conversation, Message } from "./api";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatConversationAsMarkdown(
  conversation: Conversation,
  messages: Message[]
): string {
  const lines: string[] = [];

  lines.push(`# 대화: ${conversation.session_id}`);
  lines.push("");
  lines.push(`- **날짜:** ${formatDate(conversation.created_at)}`);
  lines.push(`- **언어:** ${conversation.lang_code.toUpperCase()}`);
  lines.push(`- **메시지 수:** ${messages.length}`);
  lines.push("");
  lines.push("---");
  lines.push("");

  for (const msg of messages) {
    if (msg.role === "user") {
      lines.push("## 사용자");
      lines.push("");
      // 멀티라인 content도 blockquote로 유지
      lines.push(msg.content.split("\n").map((l) => `> ${l}`).join("\n"));
    } else {
      lines.push("## 어시스턴트");
      lines.push("");
      lines.push(msg.content);
      if (msg.sources && msg.sources.length > 0) {
        lines.push("");
        lines.push("**참고 문서:**");
        for (const s of msg.sources) {
          lines.push(`- [${s.title}](${s.url})`);
        }
      }
    }
    lines.push("");
    lines.push(`*${formatDate(msg.created_at)}*`);
    lines.push("");
    lines.push("---");
    lines.push("");
  }

  return lines.join("\n");
}

export function formatMultipleConversationsAsMarkdown(
  items: Array<{ conversation: Conversation; messages: Message[] }>
): string {
  const header: string[] = [];

  header.push("# 대화 이력 내보내기");
  header.push("");
  header.push(`- **내보낸 날짜:** ${new Date().toLocaleString("ko-KR")}`);
  header.push(`- **총 대화 수:** ${items.length}개`);
  header.push("");
  header.push("## 목차");
  header.push("");

  for (let i = 0; i < items.length; i++) {
    const { conversation } = items[i];
    header.push(
      `${i + 1}. ${conversation.session_id.slice(0, 8)}… · ${formatDate(conversation.created_at)} · ${conversation.lang_code.toUpperCase()} (${conversation.message_count}개 메시지)`
    );
  }

  header.push("");
  header.push("---");
  header.push("");

  const sections = items.map(({ conversation, messages }) =>
    formatConversationAsMarkdown(conversation, messages)
  );

  return header.join("\n") + "\n" + sections.join("\n");
}
