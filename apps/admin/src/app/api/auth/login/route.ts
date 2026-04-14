import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { createSessionToken, SESSION_COOKIE_NAME, SESSION_MAX_AGE } from "@/lib/auth";

function timingSafeStringEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) {
    // Dummy comparison to avoid length-based timing difference
    timingSafeEqual(bufA, bufA);
    return false;
  }
  return timingSafeEqual(bufA, bufB);
}

interface AuthLoginResponse {
  ok: boolean;
  is_superadmin: boolean;
  sub_admin_id?: number;
  tenant_ids?: number[];
}

export async function POST(req: Request) {
  const adminUsername = process.env.ADMIN_USERNAME;
  const adminPassword = process.env.ADMIN_PASSWORD;
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "/rag/api/v1";

  if (!adminUsername || !adminPassword) {
    return NextResponse.json(
      { error: "서버 인증 설정이 되어 있지 않습니다." },
      { status: 500 }
    );
  }

  let body: { username?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "잘못된 요청입니다." }, { status: 400 });
  }

  const inputUser = body.username ?? "";
  const inputPass = body.password ?? "";

  // 1. 백엔드 /auth/login 호출
  try {
    const response = await fetch(`${apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forwarded-For": req.headers.get("x-forwarded-for") ||
                           req.headers.get("x-real-ip") ||
                           "127.0.0.1",
      },
      body: JSON.stringify({
        username: inputUser,
        password: inputPass,
      }),
    });

    if (response.ok) {
      const authResult: AuthLoginResponse = await response.json();
      const token = await createSessionToken(
        inputUser,
        authResult.is_superadmin,
        authResult.sub_admin_id,
        authResult.tenant_ids
      );

      const cookieValue = [
        `${SESSION_COOKIE_NAME}=${token}`,
        `Max-Age=${SESSION_MAX_AGE}`,
        "Path=/rag/admin",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
      ].join("; ");

      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Set-Cookie": cookieValue,
        },
      });
    }

    // 백엔드에서 인증 실패
    return NextResponse.json(
      { error: "아이디 또는 비밀번호가 올바르지 않습니다." },
      { status: 401 }
    );
  } catch (error) {
    // 백엔드 연결 실패 — fallback: 로컬 env 인증
    const userMatch = timingSafeStringEqual(inputUser, adminUsername);
    const passMatch = timingSafeStringEqual(inputPass, adminPassword);

    if (!userMatch || !passMatch) {
      return NextResponse.json(
        { error: "아이디 또는 비밀번호가 올바르지 않습니다." },
        { status: 401 }
      );
    }

    const token = await createSessionToken(inputUser, true);
    const cookieValue = [
      `${SESSION_COOKIE_NAME}=${token}`,
      `Max-Age=${SESSION_MAX_AGE}`,
      "Path=/rag/admin",
      "HttpOnly",
      "Secure",
      "SameSite=Lax",
    ].join("; ");

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": cookieValue,
      },
    });
  }
}
