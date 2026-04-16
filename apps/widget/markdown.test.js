"use strict";

const { escapeHtml, parseMarkdown } = require("./markdown");

// ─── escapeHtml ───────────────────────────────────────────────────────────────

describe("escapeHtml", () => {
  test("escapes & < > \"", () => {
    expect(escapeHtml('a & b < c > d "e"')).toBe(
      "a &amp; b &lt; c &gt; d &quot;e&quot;"
    );
  });

  test("passes plain text unchanged", () => {
    expect(escapeHtml("hello world")).toBe("hello world");
  });
});

// ─── parseMarkdown — existing features ───────────────────────────────────────

describe("parseMarkdown — existing features", () => {
  test("renders **bold**", () => {
    expect(parseMarkdown("**bold**")).toBe("<strong>bold</strong>");
  });

  test("renders __bold__", () => {
    expect(parseMarkdown("__bold__")).toBe("<strong>bold</strong>");
  });

  test("renders *italic*", () => {
    expect(parseMarkdown("*italic*")).toBe("<em>italic</em>");
  });

  test("renders `inline code`", () => {
    expect(parseMarkdown("`code`")).toBe("<code>code</code>");
  });

  test("renders [text](url) as anchor", () => {
    const out = parseMarkdown("[OpenAI](https://openai.com)");
    expect(out).toContain('<a href="https://openai.com"');
    expect(out).toContain("OpenAI");
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener noreferrer"');
  });

  test("renders bare https URL as anchor", () => {
    const out = parseMarkdown("visit https://example.com now");
    expect(out).toContain('<a href="https://example.com"');
  });

  test("converts newlines to <br>", () => {
    expect(parseMarkdown("line1\nline2")).toBe("line1<br>line2");
  });

  test("escapes HTML in input", () => {
    expect(parseMarkdown("<script>")).toBe("&lt;script&gt;");
  });
});

// ─── parseMarkdown — IMAGE support (RED: these tests MUST fail initially) ────

describe("parseMarkdown — image support", () => {
  test("renders ![alt](url) as <img> tag", () => {
    const out = parseMarkdown("![고양이](https://example.com/cat.png)");
    expect(out).toContain('<img');
    expect(out).toContain('src="https://example.com/cat.png"');
    expect(out).toContain('alt="고양이"');
  });

  test("img tag has max-width and border-radius styles", () => {
    const out = parseMarkdown("![](https://example.com/img.jpg)");
    expect(out).toContain("max-width:100%");
    expect(out).toContain("border-radius");
  });

  test("img is NOT wrapped in an anchor tag", () => {
    const out = parseMarkdown("![alt](https://example.com/img.jpg)");
    // Should not produce an <a href=...><img...></a> nesting
    expect(out).not.toMatch(/<a[^>]*>.*<img/s);
  });

  test("image before link text does not corrupt link", () => {
    const input =
      "![logo](https://example.com/logo.png) see [docs](https://docs.example.com)";
    const out = parseMarkdown(input);
    expect(out).toContain('<img');
    expect(out).toContain('<a href="https://docs.example.com"');
  });

  test("non-http image URLs are NOT rendered as img", () => {
    // javascript: or data: URIs must not become <img> tags
    const out = parseMarkdown("![x](javascript:alert(1))");
    expect(out).not.toContain("<img");
  });

  test("bare URL after image is still rendered as anchor", () => {
    const input = "![img](https://example.com/a.png) https://example.com";
    const out = parseMarkdown(input);
    expect(out).toContain('<img');
    expect(out).toContain('<a href="https://example.com"');
  });
});
