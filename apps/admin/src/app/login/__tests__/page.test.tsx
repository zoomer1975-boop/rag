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

describe("LoginPage – 로그인 후 리다이렉트", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    // jsdom에서 window.location.assign을 mock
    Object.defineProperty(window, "location", {
      value: { assign: vi.fn(), href: "" },
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

  it("로그인 성공 시 /rag/admin 으로 hard navigate 한다 (basePath 포함)", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    render(<LoginPage />);

    await userEvent.type(screen.getByLabelText("아이디"), "admin");
    await userEvent.type(screen.getByLabelText("비밀번호"), "password");
    await userEvent.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      // window.location.href 또는 assign 이 /rag/admin 으로 설정되어야 함
      const href = (window.location as { href: string }).href;
      const assignMock = (window.location.assign as ReturnType<typeof vi.fn>);
      const navigatedTo = assignMock.mock.calls[0]?.[0] ?? href;
      expect(navigatedTo).toBe("/rag/admin");
    });
  });

  it("로그인 실패 시 에러 메시지를 표시하고 이동하지 않는다", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
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

    const assignMock = (window.location.assign as ReturnType<typeof vi.fn>);
    expect(assignMock).not.toHaveBeenCalled();
  });
});
