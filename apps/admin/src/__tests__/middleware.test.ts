import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { middleware, config } from "../middleware";
import { createSessionToken } from "@/lib/auth";
import { NextRequest } from "next/server";

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

function makeReq(pathname: string, cookie?: string) {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  return new NextRequest(`http://localhost${pathname}`, { headers });
}

describe("middleware config.matcher", () => {
  it("should be defined", () => {
    expect(config.matcher).toBeDefined();
  });
});

describe("middleware - unauthenticated", () => {
  it("redirects / to /login when no cookie", async () => {
    const req = makeReq("/");
    const res = await middleware(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
  });

  it("redirects /dashboard to /login when no cookie", async () => {
    const req = makeReq("/dashboard");
    const res = await middleware(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/login");
  });

  it("redirects with callbackUrl query param", async () => {
    const req = makeReq("/dashboard");
    const res = await middleware(req);
    const location = res.headers.get("location") ?? "";
    expect(location).toContain("callbackUrl=");
  });
});

describe("middleware - /login passthrough", () => {
  it("does not redirect /login", async () => {
    const req = makeReq("/login");
    const res = await middleware(req);
    // next() returns undefined or 200, not a redirect
    expect(res.status).not.toBe(307);
  });
});

describe("middleware - authenticated", () => {
  it("allows request when valid session cookie present", async () => {
    const token = await createSessionToken("admin");
    const req = makeReq("/", `admin_session=${token}`);
    const res = await middleware(req);
    expect(res.status).not.toBe(307);
  });

  it("redirects to /login when cookie has invalid token", async () => {
    const req = makeReq("/", "admin_session=totally-invalid-token");
    const res = await middleware(req);
    expect(res.status).toBe(307);
  });
});
