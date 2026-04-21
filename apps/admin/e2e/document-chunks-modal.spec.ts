/**
 * E2E tests for the Document Content (Chunks) Modal feature
 *
 * Tests the "내용" (Content) button on the Documents panel that opens
 * a modal showing document chunks with search functionality.
 */
import { test, expect, Page } from "@playwright/test";
import path from "path";

const SCREENSHOTS = path.resolve(__dirname, "screenshots");
const BASE_URL = "http://localhost/rag/admin";

async function login(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState("networkidle");

  // Fill login form
  await page.locator('input[type="text"], input[name="username"]').fill("admin");
  await page.locator('input[type="password"]').fill("stat214!@");
  await page.locator('button[type="submit"]').click();

  // Wait for redirect to dashboard
  await page.waitForURL(/\/rag\/admin\/?(?!login)/, { timeout: 10_000 });
  await page.waitForLoadState("networkidle");
}

async function navigateToDocuments(page: Page) {
  // Look for the Documents tab/link in the dashboard nav
  const docsNav = page.locator('button, a, [role="tab"]').filter({ hasText: /문서|documents/i });
  if (await docsNav.count() > 0) {
    await docsNav.first().click();
    await page.waitForLoadState("networkidle");
  }
  // Verify we can see the documents section
  await expect(page.locator("text=문서 관리")).toBeVisible({ timeout: 10_000 });
}

test.describe("Document Chunks Modal", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("login and reach document management section", async ({ page }) => {
    // Take screenshot of dashboard after login
    await page.screenshot({ path: path.join(SCREENSHOTS, "01-dashboard-after-login.png"), fullPage: false });

    // Navigate to documents section
    await navigateToDocuments(page);

    await page.screenshot({ path: path.join(SCREENSHOTS, "02-documents-panel.png"), fullPage: false });

    // Verify documents panel heading is visible
    await expect(page.locator("text=문서 관리")).toBeVisible();
  });

  test("completed document shows enabled 내용 button", async ({ page }) => {
    await navigateToDocuments(page);

    // Wait for document list to load
    await page.waitForSelector("ul li", { timeout: 10_000 });

    // Find rows with 완료 (completed) status
    const completedRows = page.locator("li").filter({ hasText: "완료" });
    const count = await completedRows.count();
    expect(count).toBeGreaterThan(0);

    // The "내용" button should not be disabled for completed docs
    const viewBtn = completedRows.first().locator("button", { hasText: "내용" });
    await expect(viewBtn).toBeVisible();
    await expect(viewBtn).toBeEnabled();

    await page.screenshot({ path: path.join(SCREENSHOTS, "03-document-list-with-completed.png"), fullPage: false });
  });

  test("clicking 내용 opens modal with document title and chunks", async ({ page }) => {
    await navigateToDocuments(page);

    // Wait for document list
    await page.waitForSelector("ul li", { timeout: 10_000 });

    // Click 내용 button on first completed document
    const completedRows = page.locator("li").filter({ hasText: "완료" });
    const viewBtn = completedRows.first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    // Modal should appear — wait for the overlay and dialog
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Modal must contain h2 with the document title
    const modalTitle = modal.locator("h2");
    await expect(modalTitle).toBeVisible();
    const titleText = await modalTitle.textContent();
    expect(titleText?.trim().length).toBeGreaterThan(0);

    // Chunks list should load — at least one li inside the ol
    const chunkItems = modal.locator("ol li");
    await expect(chunkItems.first()).toBeVisible({ timeout: 8_000 });
    const chunkCount = await chunkItems.count();
    expect(chunkCount).toBeGreaterThan(0);

    await page.screenshot({ path: path.join(SCREENSHOTS, "04-modal-open-with-chunks.png"), fullPage: false });

    console.log(`Modal title: "${titleText?.trim()}", chunks displayed: ${chunkCount}`);
  });

  test("chunks display chunk index badge and content text", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Wait for chunk items
    const firstChunk = modal.locator("ol li").first();
    await expect(firstChunk).toBeVisible({ timeout: 8_000 });

    // Each chunk should have a badge like "#1"
    const badge = firstChunk.locator("span").first();
    await expect(badge).toBeVisible();
    const badgeText = await badge.textContent();
    expect(badgeText).toMatch(/^#\d+$/);

    // Each chunk should have a paragraph with content
    const para = firstChunk.locator("p");
    await expect(para).toBeVisible();
    const contentText = await para.textContent();
    expect(contentText?.trim().length).toBeGreaterThan(0);
  });

  test("search functionality filters chunks and highlights matches", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Wait for chunks to load
    await expect(modal.locator("ol li").first()).toBeVisible({ timeout: 8_000 });

    const totalBefore = await modal.locator("ol li").count();

    // Get first chunk content to use as search keyword
    const firstChunkText = await modal.locator("ol li p").first().textContent() ?? "";
    // Use the first 10 chars of the first chunk as search term
    const keyword = firstChunkText.trim().slice(0, 10).trim();

    if (keyword.length < 2) {
      test.skip(); // Skip if content is too short to search
      return;
    }

    // Type into search input
    const searchInput = modal.locator('input[type="search"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill(keyword);

    // After search, result count indicator should appear
    await expect(modal.locator("text=청크")).toBeVisible({ timeout: 5_000 });

    // Filtered chunks should contain <mark> highlights
    const marks = modal.locator("mark");
    await expect(marks.first()).toBeVisible({ timeout: 5_000 });
    const markText = await marks.first().textContent();
    expect(markText?.toLowerCase()).toContain(keyword.toLowerCase().slice(0, 3));

    await page.screenshot({ path: path.join(SCREENSHOTS, "05-modal-search-results.png"), fullPage: false });

    // Clear search via × button
    const clearBtn = modal.locator("button[aria-label='검색어 지우기']");
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();

    // After clearing, all chunks should be visible again
    await expect(modal.locator("ol li")).toHaveCount(totalBefore, { timeout: 5_000 });

    await page.screenshot({ path: path.join(SCREENSHOTS, "06-modal-search-cleared.png"), fullPage: false });
  });

  test("searching for non-existent term shows no-results message", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });
    await expect(modal.locator("ol li").first()).toBeVisible({ timeout: 8_000 });

    const searchInput = modal.locator('input[type="search"]');
    await searchInput.fill("xyzzy_nonexistent_term_12345");

    // Should show the empty state message
    await expect(
      modal.locator("text=일치하는 청크가 없습니다")
    ).toBeVisible({ timeout: 5_000 });

    await page.screenshot({ path: path.join(SCREENSHOTS, "07-modal-no-results.png"), fullPage: false });
  });

  test("modal closes on ESC key press", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Press ESC to close
    await page.keyboard.press("Escape");
    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    await page.screenshot({ path: path.join(SCREENSHOTS, "08-modal-closed-after-esc.png"), fullPage: false });
  });

  test("modal closes when clicking the × button", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Click the close button (aria-label="닫기")
    await modal.locator("button[aria-label='닫기']").click();
    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });

  test("modal closes when clicking the backdrop overlay", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });

    // Click outside the modal dialog (on the overlay)
    // The overlay is [role="presentation"] — click at top-left corner of viewport
    await page.mouse.click(10, 10);
    await expect(modal).not.toBeVisible({ timeout: 5_000 });
  });

  test("load more pagination works when document has many chunks", async ({ page }) => {
    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });
    await expect(modal.locator("ol li").first()).toBeVisible({ timeout: 8_000 });

    // "더 보기" button only appears when total > 50 chunks
    const loadMoreBtn = modal.locator("button", { hasText: "더 보기" });
    if (await loadMoreBtn.isVisible()) {
      const countBefore = await modal.locator("ol li").count();
      await loadMoreBtn.click();

      // Wait for more items to load
      await page.waitForFunction(
        (before) => document.querySelectorAll('[role="dialog"] ol li').length > before,
        countBefore,
        { timeout: 8_000 }
      );

      const countAfter = await modal.locator("ol li").count();
      expect(countAfter).toBeGreaterThan(countBefore);

      await page.screenshot({ path: path.join(SCREENSHOTS, "09-modal-load-more.png"), fullPage: false });
    } else {
      // Document has <= 50 chunks, no load-more needed — that is expected behavior
      console.log("Document has <= 50 chunks; load-more button not shown (expected).");
      await page.screenshot({ path: path.join(SCREENSHOTS, "09-modal-all-chunks-loaded.png"), fullPage: false });
    }
  });

  test("no console errors during modal open and search", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`[pageerror] ${err.message}`);
    });

    await navigateToDocuments(page);
    await page.waitForSelector("ul li", { timeout: 10_000 });

    const viewBtn = page.locator("li").filter({ hasText: "완료" }).first().locator("button", { hasText: "내용" });
    await viewBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 8_000 });
    await expect(modal.locator("ol li").first()).toBeVisible({ timeout: 8_000 });

    // Perform a search
    const searchInput = modal.locator('input[type="search"]');
    await searchInput.fill("the");
    await page.waitForTimeout(300);

    await searchInput.fill("");
    await page.waitForTimeout(300);

    // Close modal
    await page.keyboard.press("Escape");

    // Filter out known non-critical browser noise
    const realErrors = consoleErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("net::ERR") &&
        !e.includes("ERR_ABORTED")
    );

    if (realErrors.length > 0) {
      console.error("Console errors found:", realErrors);
    }
    expect(realErrors).toHaveLength(0);
  });
});
