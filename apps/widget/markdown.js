"use strict";

/**
 * Minimal Markdown → HTML renderer for the RAG chat widget.
 * Supports: bold, italic, inline code, links, images, line breaks.
 */

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function parseMarkdown(text) {
  let out = escapeHtml(text);
  // Bold: **text** or __text__
  out = out.replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>");
  out = out.replace(/__(.+?)__/gs, "<strong>$1</strong>");
  // Italic: *text* or _text_ (not touching bold markers)
  out = out.replace(/\*([^*\n]+?)\*/g, "<em>$1</em>");
  out = out.replace(/_([^_\n]+?)_/g, "<em>$1</em>");
  // Inline code: `code`
  out = out.replace(/`([^`]+?)`/g, "<code>$1</code>");
  // Images: ![alt](url) — http/https only — must come BEFORE link pattern
  out = out.replace(
    /!\[([^\]]*?)\]\((https?:\/\/[^)]+?)\)/g,
    '<img src="$2" alt="$1" style="max-width:100%;border-radius:8px;margin:4px 0;display:block;">'
  );
  // Links: [text](url) — http/https only
  out = out.replace(
    /\[([^\]]+?)\]\((https?:\/\/[^)]+?)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:underline;opacity:0.85;">$1</a>'
  );
  // Bare URLs
  out = out.replace(
    /(?<![">])(https?:\/\/[^\s<"]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:underline;opacity:0.85;">$1</a>'
  );
  // Line breaks
  out = out.replace(/\n/g, "<br>");
  return out;
}

module.exports = { escapeHtml, parseMarkdown };
