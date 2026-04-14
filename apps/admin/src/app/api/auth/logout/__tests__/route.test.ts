import { describe, it, expect } from "vitest";
import { POST } from "../route";

describe("POST /api/auth/logout", () => {
  it("returns 200", async () => {
    const req = new Request("http://localhost/rag/admin/api/auth/logout", {
      method: "POST",
    });
    const res = await POST(req);
    expect(res.status).toBe(200);
  });

  it("clears the admin_session cookie with Path=/ to match how it was set on login", async () => {
    const req = new Request("http://localhost/rag/admin/api/auth/logout", {
      method: "POST",
    });
    const res = await POST(req);
    const cookie = res.headers.get("set-cookie");
    expect(cookie).toContain("admin_session=");
    expect(cookie).toMatch(/Max-Age=0/i);
    // Path must match the login route's Path=/ so the cookie is actually cleared.
    // Using Path=/rag/admin would only clear a cookie scoped to that path,
    // leaving the Path=/ cookie intact and causing auto-login after logout.
    expect(cookie).toContain("Path=/;");
    expect(cookie).not.toContain("Path=/rag/admin");
  });
});
