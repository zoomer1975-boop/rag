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

// 주의: vitest의 raw NextRequest는 next.config.ts의 basePath를 인식하지 못합니다.
// 프로덕션에서 Next.js 런타임이 basePath("/rag/admin")를 req.nextUrl.pathname에서
// 자동으로 제거하므로, 테스트에서는 제거된 경로를 직접 전달합니다.
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
    // 프로덕션에서는 Next.js 런타임이 basePath를 포함해 /rag/admin/login으로 리다이렉트합니다.
    // 테스트 환경의 raw NextRequest는 basePath를 처리하지 않으므로 /login 포함 여부만 검증합니다.
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

  it("does not redirect /api/auth paths", async () => {
    const req = makeReq("/api/auth/login");
    const res = await middleware(req);
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
