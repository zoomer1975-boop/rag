export function downloadAsFile(
  content: string,
  filename: string,
  mimeType = "text/markdown"
): void {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function makeConversationFilename(sessionId: string): string {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  return `conversation_${sessionId.slice(0, 8)}_${date}.md`;
}

export function makeBulkFilename(): string {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  return `conversations_${date}.md`;
}
