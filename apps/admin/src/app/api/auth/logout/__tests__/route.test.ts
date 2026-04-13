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

  it("clears the admin_session cookie by setting maxAge=0", async () => {
    const req = new Request("http://localhost/rag/admin/api/auth/logout", {
      method: "POST",
    });
    const res = await POST(req);
    const cookie = res.headers.get("set-cookie");
    expect(cookie).toContain("admin_session=");
    expect(cookie).toMatch(/Max-Age=0/i);
    expect(cookie).toContain("Path=/rag/admin");
  });
});
