// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import CreateTenantForm from "../CreateTenantForm";

vi.mock("@/lib/api", () => ({
  adminFetch: vi.fn(),
}));

import { adminFetch } from "@/lib/api";
const mockAdminFetch = vi.mocked(adminFetch);

describe("CreateTenantForm", () => {
  const onCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows error message when adminFetch throws", async () => {
    mockAdminFetch.mockRejectedValueOnce(new Error("테넌트 생성 실패: 409 Conflict"));

    render(<CreateTenantForm onCreated={onCreated} />);

    // Click '+ 테넌트 추가' to open the form
    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));

    // Fill in the name
    await userEvent.type(screen.getByPlaceholderText("테넌트 이름"), "test-tenant");

    // Submit
    await userEvent.click(screen.getByRole("button", { name: /생성/ }));

    // Error should be visible
    await waitFor(() => {
      expect(screen.getByText("테넌트 생성 실패: 409 Conflict")).toBeInTheDocument();
    });

    // onCreated should NOT have been called
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("re-enables submit button after failed submission (loading resets to false)", async () => {
    mockAdminFetch.mockRejectedValueOnce(new Error("서버 오류"));

    render(<CreateTenantForm onCreated={onCreated} />);

    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));
    await userEvent.type(screen.getByPlaceholderText("테넌트 이름"), "test-tenant");
    await userEvent.click(screen.getByRole("button", { name: /생성/ }));

    // Button must become enabled again so the user can retry
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /생성/ })).not.toBeDisabled();
    });
  });

  it("re-enables submit button after successful submission is followed by another open", async () => {
    const mockTenant = { id: 1, name: "t1", api_key: "k1", is_active: true, lang_policy: "auto", default_lang: "ko", allowed_langs: "ko", allowed_domains: "", widget_config: { primary_color: "#000", greeting: "", position: "right", title: "", placeholder: "" }, system_prompt: null };
    mockAdminFetch.mockResolvedValueOnce(mockTenant);

    render(<CreateTenantForm onCreated={onCreated} />);

    // First submission (success)
    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));
    await userEvent.type(screen.getByPlaceholderText("테넌트 이름"), "t1");
    await userEvent.click(screen.getByRole("button", { name: /생성/ }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());

    // Open form again — button must be enabled immediately
    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));
    expect(screen.getByRole("button", { name: /생성/ })).not.toBeDisabled();
  });

  it("calls onCreated and resets form when adminFetch succeeds", async () => {
    const mockTenant = { id: "1", name: "test-tenant", api_key: "key-123", is_active: true, domains: [] };
    mockAdminFetch.mockResolvedValueOnce(mockTenant);

    render(<CreateTenantForm onCreated={onCreated} />);

    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));
    await userEvent.type(screen.getByPlaceholderText("테넌트 이름"), "test-tenant");
    await userEvent.click(screen.getByRole("button", { name: /생성/ }));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(mockTenant);
    });

    // Form should be closed (back to '+ 테넌트 추가' button)
    expect(screen.getByRole("button", { name: /테넌트 추가/ })).toBeInTheDocument();
  });

  it("does not submit when name is empty", async () => {
    render(<CreateTenantForm onCreated={onCreated} />);

    await userEvent.click(screen.getByRole("button", { name: /테넌트 추가/ }));
    await userEvent.click(screen.getByRole("button", { name: /생성/ }));

    expect(mockAdminFetch).not.toHaveBeenCalled();
  });
});
