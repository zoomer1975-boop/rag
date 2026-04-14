// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

import LoginPage from "../page";

describe("LoginPage – 로그인 및 세션 리다이렉트", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    Object.defineProperty(window, "location", {
      value: { assign: vi.fn(), replace: vi.fn(), href: "" },
      writable: true,
      configurable: true,
    });

    global.fetch = vi.fn();
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  it("로그인 성공 시 replace로 /rag/admin/ 으로 이동한다 (히스토리에서 로그인 페이지 제거)", async () => {
    // First fetch: checkSession returns null (not logged in)
    // Second fetch: login succeeds
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(new Response(JSON.stringify(null), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText("아이디"), "admin");
    await userEvent.type(screen.getByLabelText("비밀번호"), "password");
    await userEvent.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      const replaceMock = window.location.replace as ReturnType<typeof vi.fn>;
      expect(replaceMock).toHaveBeenCalledWith("/rag/admin/");
    });
  });

  it("로그인 실패 시 에러 메시지를 표시하고 이동하지 않는다", async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(new Response(JSON.stringify(null), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: "아이디 또는 비밀번호가 올바르지 않습니다." }),
          { status: 401 }
        )
      );

    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText("아이디"), "admin");
    await userEvent.type(screen.getByLabelText("비밀번호"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      expect(
        screen.getByText("아이디 또는 비밀번호가 올바르지 않습니다.")
      ).toBeInTheDocument();
    });

    const replaceMock = window.location.replace as ReturnType<typeof vi.fn>;
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("이미 로그인된 상태에서 렌더링 시 replace로 /rag/admin/ 으로 이동한다", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ username: "admin", is_superadmin: true, exp: 9999999999 }),
        { status: 200 }
      )
    );

    render(<LoginPage />);

    await waitFor(() => {
      const replaceMock = window.location.replace as ReturnType<typeof vi.fn>;
      expect(replaceMock).toHaveBeenCalledWith("/rag/admin/");
    });
  });

  it("BFCache 복원 시 pageshow 이벤트로 세션 확인 후 replace로 이동한다", async () => {
    // Initial render: not logged in
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify(null), { status: 200 })
    );

    render(<LoginPage />);

    // Wait for initial session check to complete
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    // Simulate BFCache restoration: session is now valid
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ username: "admin", is_superadmin: true, exp: 9999999999 }),
        { status: 200 }
      )
    );

    const pageshowEvent = new Event("pageshow") as PageTransitionEvent;
    Object.defineProperty(pageshowEvent, "persisted", { value: true });
    window.dispatchEvent(pageshowEvent);

    await waitFor(() => {
      const replaceMock = window.location.replace as ReturnType<typeof vi.fn>;
      expect(replaceMock).toHaveBeenCalledWith("/rag/admin/");
    });
  });
});
