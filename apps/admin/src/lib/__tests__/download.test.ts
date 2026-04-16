// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { downloadAsFile, makeConversationFilename, makeBulkFilename } from "../download";

describe("makeConversationFilename", () => {
  it("starts with 'conversation_'", () => {
    expect(makeConversationFilename("abcdef1234567890")).toMatch(/^conversation_/);
  });

  it("uses first 8 chars of session_id", () => {
    expect(makeConversationFilename("abcdef1234567890")).toContain("abcdef12");
  });

  it("ends with .md", () => {
    expect(makeConversationFilename("abcdef1234567890")).toMatch(/\.md$/);
  });

  it("contains the current date in YYYYMMDD format", () => {
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    expect(makeConversationFilename("abcdef1234567890")).toContain(date);
  });
});

describe("makeBulkFilename", () => {
  it("starts with 'conversations_'", () => {
    expect(makeBulkFilename()).toMatch(/^conversations_/);
  });

  it("ends with .md", () => {
    expect(makeBulkFilename()).toMatch(/\.md$/);
  });

  it("contains the current date in YYYYMMDD format", () => {
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    expect(makeBulkFilename()).toContain(date);
  });
});

describe("downloadAsFile", () => {
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let createObjectURL: ReturnType<typeof vi.fn>;
  let clickMock: ReturnType<typeof vi.fn>;
  let createdElement: HTMLAnchorElement | null = null;

  beforeEach(() => {
    revokeObjectURL = vi.fn();
    createObjectURL = vi.fn(() => "blob:mock-url");
    clickMock = vi.fn();

    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        const anchor = {
          href: "",
          download: "",
          click: clickMock,
        } as unknown as HTMLAnchorElement;
        createdElement = anchor;
        return anchor;
      }
      return document.createElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    createdElement = null;
  });

  it("creates an object URL from the content", () => {
    downloadAsFile("# Hello", "test.md");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
  });

  it("sets the download filename on the anchor", () => {
    downloadAsFile("# Hello", "test.md");
    expect(createdElement?.download).toBe("test.md");
  });

  it("sets the href to the object URL", () => {
    downloadAsFile("# Hello", "test.md");
    expect(createdElement?.href).toBe("blob:mock-url");
  });

  it("calls click() on the anchor", () => {
    downloadAsFile("# Hello", "test.md");
    expect(clickMock).toHaveBeenCalledOnce();
  });

  it("revokes the object URL after click", () => {
    downloadAsFile("# Hello", "test.md");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});
