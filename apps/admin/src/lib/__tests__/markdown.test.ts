import { describe, it, expect } from "vitest";
import { formatConversationAsMarkdown, formatMultipleConversationsAsMarkdown } from "../markdown";
import type { Conversation, Message } from "../api";

const baseConversation: Conversation = {
  id: 1,
  session_id: "abcdef1234567890",
  lang_code: "ko",
  created_at: "2025-04-16T10:00:00Z",
  message_count: 2,
};

const userMessage: Message = {
  role: "user",
  content: "안녕하세요, 반갑습니다.",
  sources: null,
  created_at: "2025-04-16T10:00:01Z",
};

const assistantMessage: Message = {
  role: "assistant",
  content: "안녕하세요! 무엇을 도와드릴까요?",
  sources: [{ title: "도움말 문서", url: "https://example.com/help" }],
  created_at: "2025-04-16T10:00:02Z",
};

describe("formatConversationAsMarkdown", () => {
  it("contains the session_id in the heading", () => {
    const result = formatConversationAsMarkdown(baseConversation, [userMessage]);
    expect(result).toContain("# 대화: abcdef1234567890");
  });

  it("contains language code in uppercase", () => {
    const result = formatConversationAsMarkdown(baseConversation, [userMessage]);
    expect(result).toContain("**언어:** KO");
  });

  it("contains message count", () => {
    const result = formatConversationAsMarkdown(baseConversation, [userMessage]);
    expect(result).toContain("**메시지 수:** 1");
  });

  it("renders user message as blockquote", () => {
    const result = formatConversationAsMarkdown(baseConversation, [userMessage]);
    expect(result).toContain("## 사용자");
    expect(result).toContain("> 안녕하세요, 반갑습니다.");
  });

  it("renders assistant message as plain text", () => {
    const result = formatConversationAsMarkdown(baseConversation, [assistantMessage]);
    expect(result).toContain("## 어시스턴트");
    expect(result).toContain("안녕하세요! 무엇을 도와드릴까요?");
  });

  it("includes sources when present", () => {
    const result = formatConversationAsMarkdown(baseConversation, [assistantMessage]);
    expect(result).toContain("**참고 문서:**");
    expect(result).toContain("[도움말 문서](https://example.com/help)");
  });

  it("omits sources section when sources is null", () => {
    const result = formatConversationAsMarkdown(baseConversation, [userMessage]);
    expect(result).not.toContain("**참고 문서:**");
  });

  it("omits sources section when sources is empty array", () => {
    const msg: Message = { ...assistantMessage, sources: [] };
    const result = formatConversationAsMarkdown(baseConversation, [msg]);
    expect(result).not.toContain("**참고 문서:**");
  });

  it("handles empty messages array", () => {
    const result = formatConversationAsMarkdown(baseConversation, []);
    expect(result).toContain("**메시지 수:** 0");
    expect(result).toContain("# 대화:");
  });

  it("handles multiline user content as blockquotes", () => {
    const msg: Message = {
      ...userMessage,
      content: "첫 번째 줄\n두 번째 줄",
    };
    const result = formatConversationAsMarkdown(baseConversation, [msg]);
    expect(result).toContain("> 첫 번째 줄\n> 두 번째 줄");
  });

  it("handles multiple messages in order", () => {
    const result = formatConversationAsMarkdown(baseConversation, [
      userMessage,
      assistantMessage,
    ]);
    const userIdx = result.indexOf("## 사용자");
    const assistantIdx = result.indexOf("## 어시스턴트");
    expect(userIdx).toBeLessThan(assistantIdx);
  });
});

describe("formatMultipleConversationsAsMarkdown", () => {
  const items = [
    { conversation: baseConversation, messages: [userMessage, assistantMessage] },
    {
      conversation: { ...baseConversation, id: 2, session_id: "zzzzzzz999999999" },
      messages: [userMessage],
    },
  ];

  it("includes export header with total count", () => {
    const result = formatMultipleConversationsAsMarkdown(items);
    expect(result).toContain("# 대화 이력 내보내기");
    expect(result).toContain("**총 대화 수:** 2개");
  });

  it("includes table of contents with both sessions", () => {
    const result = formatMultipleConversationsAsMarkdown(items);
    expect(result).toContain("abcdef12");
    expect(result).toContain("zzzzzzz9");
  });

  it("includes both conversations in the body", () => {
    const result = formatMultipleConversationsAsMarkdown(items);
    expect(result).toContain("# 대화: abcdef1234567890");
    expect(result).toContain("# 대화: zzzzzzz999999999");
  });

  it("handles a single conversation", () => {
    const result = formatMultipleConversationsAsMarkdown([items[0]]);
    expect(result).toContain("**총 대화 수:** 1개");
    expect(result).toContain("# 대화: abcdef1234567890");
  });
});
