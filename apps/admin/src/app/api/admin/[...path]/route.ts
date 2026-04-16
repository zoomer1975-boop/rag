/**
 * 관리자 API 프록시
 *
 * 클라이언트 → Next.js 프록시 → FastAPI
 *
 * ADMIN_API_TOKEN은 서버 사이드(런타임)에서만 읽으므로
 * NEXT_PUBLIC_* 빌드 시점 제약을 피할 수 있습니다.
 */

import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { verifySessionToken, SESSION_COOKIE_NAME } from "@/lib/auth";

// Docker 내부 API 주소 (런타임 env, NEXT_PUBLIC_ 불필요)
// nginx가 /rag 접두사를 제거하므로 Docker 내부 직접 호출 시 /api/v1만 사용
const INTERNAL_API_BASE =
  process.env.INTERNAL_API_URL
    ? `${process.env.INTERNAL_API_URL}/api/v1`
    : "http://api:8000/api/v1";

const ADMIN_API_TOKEN = process.env.ADMIN_API_TOKEN ?? "";

async function authenticate(): Promise<boolean> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value ?? "";
  const session = await verifySessionToken(token);
  return session !== null;
}

async function proxy(req: NextRequest, pathSegments: string[]): Promise<NextResponse> {
  if (!(await authenticate())) {
    return NextResponse.json({ error: "인증이 필요합니다." }, { status: 401 });
  }

  const path = pathSegments.join("/");
  const searchParams = req.nextUrl.searchParams.toString();
  const targetUrl = `${INTERNAL_API_BASE}/${path}${searchParams ? `?${searchParams}` : ""}`;

  const contentType = req.headers.get("content-type") ?? "";
  const forwardHeaders: Record<string, string> = {
    "X-Admin-Token": ADMIN_API_TOKEN,
  };
  if (contentType && !contentType.includes("multipart/form-data")) {
    forwardHeaders["Content-Type"] = contentType;
  }

  const init: RequestInit = { method: req.method, headers: forwardHeaders };

  if (req.method !== "GET" && req.method !== "HEAD") {
    if (contentType.includes("multipart/form-data")) {
      init.body = await req.formData();
    } else {
      const text = await req.text();
      if (text) init.body = text;
    }
  }

  try {
    const upstream = await fetch(targetUrl, init);
    const upstreamContentType = upstream.headers.get("content-type") ?? "application/json";

    // SSE 스트리밍 응답은 버퍼링 없이 그대로 전달
    if (upstreamContentType.includes("text/event-stream")) {
      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
        },
      });
    }

    const body = await upstream.arrayBuffer();
    return new NextResponse(body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstreamContentType,
      },
    });
  } catch (err) {
    console.error("[admin-proxy] upstream error", err);
    return NextResponse.json({ error: "API 서버에 연결할 수 없습니다." }, { status: 502 });
  }
}

type Params = Promise<{ path: string[] }>;

export async function GET(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, (await params).path);
}
export async function PUT(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, (await params).path);
}
export async function DELETE(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, (await params).path);
}
export async function PATCH(req: NextRequest, { params }: { params: Params }) {
  return proxy(req, (await params).path);
}
