import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { POST } from "../route";

beforeEach(() => {
  process.env.ADMIN_USERNAME = "admin";
  process.env.ADMIN_PASSWORD = "secret123";
  process.env.ADMIN_SESSION_SECRET = "test-secret";
});

afterEach(() => {
  delete process.env.ADMIN_USERNAME;
  delete process.env.ADMIN_PASSWORD;
  delete process.env.ADMIN_SESSION_SECRET;
});

function makeRequest(body: unknown) {
  return new Request("http://localhost/rag/admin/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/auth/login", () => {
  it("returns 200 and sets httpOnly cookie for correct credentials", async () => {
    const req = makeRequest({ username: "admin", password: "secret123" });
    const res = await POST(req);
    expect(res.status).toBe(200);
    const cookie = res.headers.get("set-cookie");
    expect(cookie).toContain("admin_session=");
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("Path=/;");
  });

  it("returns 401 for wrong password", async () => {
    const req = makeRequest({ username: "admin", password: "wrong" });
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("returns 401 for wrong username", async () => {
    const req = makeRequest({ username: "hacker", password: "secret123" });
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("returns 401 for missing fields", async () => {
    const req = makeRequest({});
    const res = await POST(req);
    expect(res.status).toBe(401);
  });

  it("returns 500 when env vars not configured", async () => {
    delete process.env.ADMIN_USERNAME;
    delete process.env.ADMIN_PASSWORD;
    const req = makeRequest({ username: "admin", password: "secret123" });
    const res = await POST(req);
    expect(res.status).toBe(500);
  });

  it("does not leak credential details in error response", async () => {
    const req = makeRequest({ username: "admin", password: "wrong" });
    const res = await POST(req);
    const body = await res.json();
    expect(JSON.stringify(body)).not.toContain("secret123");
  });
});
