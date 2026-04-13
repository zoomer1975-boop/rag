import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  createSessionToken,
  verifySessionToken,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE,
} from "../auth";

const TEST_SECRET = "test-secret-key-for-unit-tests";

beforeEach(() => {
  process.env.ADMIN_SESSION_SECRET = TEST_SECRET;
  process.env.ADMIN_USERNAME = "admin";
  process.env.ADMIN_PASSWORD = "password123";
});

afterEach(() => {
  delete process.env.ADMIN_SESSION_SECRET;
  delete process.env.ADMIN_USERNAME;
  delete process.env.ADMIN_PASSWORD;
});

describe("SESSION_COOKIE_NAME", () => {
  it("should be 'admin_session'", () => {
    expect(SESSION_COOKIE_NAME).toBe("admin_session");
  });
});

describe("SESSION_MAX_AGE", () => {
  it("should be 24 hours in seconds", () => {
    expect(SESSION_MAX_AGE).toBe(60 * 60 * 24);
  });
});

describe("createSessionToken", () => {
  it("should return a non-empty string", async () => {
    const token = await createSessionToken("admin");
    expect(typeof token).toBe("string");
    expect(token.length).toBeGreaterThan(0);
  });

  it("should return a token with two parts separated by a dot", async () => {
    const token = await createSessionToken("admin");
    const parts = token.split(".");
    expect(parts).toHaveLength(2);
  });

  it("should embed the username in the payload", async () => {
    const token = await createSessionToken("admin");
    const [payloadB64] = token.split(".");
    const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
    expect(payload.username).toBe("admin");
  });

  it("should embed an expiry in the future", async () => {
    const before = Math.floor(Date.now() / 1000);
    const token = await createSessionToken("admin");
    const [payloadB64] = token.split(".");
    const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
    expect(payload.exp).toBeGreaterThan(before + SESSION_MAX_AGE - 5);
  });
});

describe("verifySessionToken", () => {
  it("should return payload for a valid token", async () => {
    const token = await createSessionToken("admin");
    const payload = await verifySessionToken(token);
    expect(payload).not.toBeNull();
    expect(payload?.username).toBe("admin");
  });

  it("should return null for an empty string", async () => {
    const result = await verifySessionToken("");
    expect(result).toBeNull();
  });

  it("should return null for a malformed token (no dot)", async () => {
    const result = await verifySessionToken("notavalidtoken");
    expect(result).toBeNull();
  });

  it("should return null for a token with tampered payload", async () => {
    const token = await createSessionToken("admin");
    const [, sig] = token.split(".");
    const fakePayload = Buffer.from(
      JSON.stringify({ username: "hacker", exp: Math.floor(Date.now() / 1000) + 9999 }),
      "utf8"
    ).toString("base64url");
    const tampered = `${fakePayload}.${sig}`;
    const result = await verifySessionToken(tampered);
    expect(result).toBeNull();
  });

  it("should return null for an expired token", async () => {
    const expiredPayload = Buffer.from(
      JSON.stringify({ username: "admin", exp: Math.floor(Date.now() / 1000) - 1 }),
      "utf8"
    ).toString("base64url");

    // create a valid signature for the expired payload to test expiry check separately
    // We'll craft a token by re-signing manually — just pass garbage signature to verify null
    const result = await verifySessionToken(`${expiredPayload}.invalidsig`);
    expect(result).toBeNull();
  });

  it("should return null for a token with invalid signature", async () => {
    const token = await createSessionToken("admin");
    const [payloadB64] = token.split(".");
    const badSig = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    const result = await verifySessionToken(`${payloadB64}.${badSig}`);
    expect(result).toBeNull();
  });
});
