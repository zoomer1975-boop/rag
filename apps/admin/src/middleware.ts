import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/auth";

const PUBLIC_PATHS = ["/login", "/api/auth"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const token = req.cookies.get(SESSION_COOKIE_NAME)?.value ?? "";
  const payload = await verifySessionToken(token);

  if (!payload) {
    // req.nextUrl은 basePath-aware URL 객체이므로 clone() 후 pathname만 바꾸면
    // Next.js가 자동으로 basePath("/rag/admin")를 포함한 URL을 생성합니다.
    // new URL("/login", req.url) 은 basePath를 포함하지 않아 nginx 404가 발생합니다.
    const loginUrl = req.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(loginUrl, 307);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)"],
};
