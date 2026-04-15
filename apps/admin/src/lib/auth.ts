export const SESSION_COOKIE_NAME = "admin_session";
export const SESSION_MAX_AGE = 60 * 60 * 24; // 24 hours

interface SessionPayload {
  username: string;
  is_superadmin?: boolean;
  sub_admin_id?: number;
  tenant_ids?: number[];
  exp: number;
}

function getSecret(): string {
  const sessionSecret = process.env.ADMIN_SESSION_SECRET;
  if (sessionSecret) {
    if (sessionSecret.length < 32) {
      throw new Error("ADMIN_SESSION_SECRET은 최소 32자 이상이어야 합니다.");
    }
    return sessionSecret;
  }

  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    throw new Error("ADMIN_SESSION_SECRET (또는 ADMIN_PASSWORD) 환경변수가 설정되지 않았습니다.");
  }
  return adminPassword;
}

async function getHmacKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

export async function createSessionToken(
  username: string,
  is_superadmin: boolean = true,
  sub_admin_id?: number,
  tenant_ids?: number[]
): Promise<string> {
  const payload: SessionPayload = {
    username,
    is_superadmin,
    sub_admin_id,
    tenant_ids,
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE,
  };
  const payloadB64 = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");

  const key = await getHmacKey(getSecret());
  const sigBuf = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadB64)
  );
  const sig = Buffer.from(sigBuf).toString("base64url");

  return `${payloadB64}.${sig}`;
}

export async function verifySessionToken(token: string): Promise<SessionPayload | null> {
  if (!token) return null;

  const dotIdx = token.indexOf(".");
  if (dotIdx === -1) return null;

  const payloadB64 = token.slice(0, dotIdx);
  const sig = token.slice(dotIdx + 1);

  try {
    const key = await getHmacKey(getSecret());
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      Buffer.from(sig, "base64url"),
      new TextEncoder().encode(payloadB64)
    );
    if (!valid) return null;

    const payload: SessionPayload = JSON.parse(
      Buffer.from(payloadB64, "base64url").toString("utf8")
    );

    if (payload.exp < Math.floor(Date.now() / 1000)) return null;

    return payload;
  } catch {
    return null;
  }
}
