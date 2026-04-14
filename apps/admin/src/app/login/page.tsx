"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? process.env.NEXT_PUBLIC_API_URL.replace(/\/api\/v1$/, "")
  : "";

function LoginForm() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/";

  // 이미 로그인된 상태면 관리자 메인으로 리다이렉트
  useEffect(() => {
    const checkSession = async () => {
      try {
        const res = await fetch("/rag/admin/api/auth/me");
        if (res.ok) {
          const payload = await res.json();
          if (payload) {
            window.location.assign("/rag/admin/");
          }
        }
      } catch {
        // 세션 확인 실패 시 로그인 폼 그대로 유지
      }
    };
    checkSession();
  }, []);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/rag/admin/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (res.ok) {
        const safeUrl =
          callbackUrl.startsWith("/") && !callbackUrl.startsWith("//")
            ? callbackUrl
            : "/";
        // Hard navigation with explicit basePath prefix.
        // router.push is a soft navigation and may not re-evaluate middleware
        // with the new session cookie. window.location.assign forces a full
        // browser request so the cookie is sent and the server can validate it.
        // basePath ("/rag/admin") must be prepended manually because
        // window.location is not basePath-aware (unlike next/router).
        const destination = "/rag/admin" + safeUrl;
        window.location.assign(destination);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.error ?? "로그인에 실패했습니다.");
      }
    } catch {
      setError("서버에 연결할 수 없습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.card}>
        <h1 className={styles.title}>RAG Admin</h1>
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="username">
              아이디
            </label>
            <input
              id="username"
              className={styles.input}
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              비밀번호
            </label>
            <input
              id="password"
              className={styles.input}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <button className={styles.btn} type="submit" disabled={loading}>
            {loading ? "로그인 중…" : "로그인"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
