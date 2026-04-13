import { SESSION_COOKIE_NAME } from "@/lib/auth";

export async function POST() {
  const cookieValue = [
    `${SESSION_COOKIE_NAME}=`,
    "Max-Age=0",
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
