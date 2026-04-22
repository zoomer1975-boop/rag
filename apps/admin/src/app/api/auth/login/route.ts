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

function buildCookieParts(token: string): string[] {
  const isSecure =
    process.env.NODE_ENV === "production" &&
    process.env.COOKIE_SECURE !== "false";
  return [
    `${SESSION_COOKIE_NAME}=${token}`,
    `Max-Age=${SESSION_MAX_AGE}`,
    "Path=/",
    "HttpOnly",
    ...(isSecure ? ["Secure"] : []),
    "SameSite=Strict",
  ];
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
  const apiBaseUrl = process.env.INTERNAL_API_URL
    ? `${process.env.INTERNAL_API_URL}/api/v1`
    : "http://api:8000/api/v1";

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
  // H-6: nginx 가 설정한 X-Real-IP 만 신뢰하여 전달합니다.
  // 클라이언트가 조작할 수 있는 X-Forwarded-For 는 전달하지 않습니다.
  const realIp = req.headers.get("x-real-ip") ?? "127.0.0.1";

  try {
    const response = await fetch(`${apiBaseUrl}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Real-IP": realIp,
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

      const cookieParts = buildCookieParts(token);

      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Set-Cookie": cookieParts.join("; "),
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

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Set-Cookie": buildCookieParts(token).join("; "),
      },
    });
  }
}
